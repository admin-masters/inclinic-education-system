# reporting_etl/management/commands/run_etl.py
import importlib
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from reporting_etl.models import EtlState

MODEL_PATHS = [
    'user_management.models.User',
    'campaign_management.models.Campaign',
    'collateral_management.models.Collateral',
    'shortlink_management.models.ShortLink',
    'sharing_management.models.ShareLog',
    'doctor_viewer.models.Doctor',
    'doctor_viewer.models.DoctorEngagement',
]

# Optional: fully resync these each run (good for small tables, and fixes delete-sync issues)
FULL_SYNC_MODEL_NAMES = {"User"}  # add others if they are small enough


class Command(BaseCommand):
    help = "Incrementally copy updated rows from default DB → reporting DB"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting ETL …"))
        for path in MODEL_PATHS:
            self.clone_model(path)
        self.stdout.write(self.style.SUCCESS("ETL finished."))

    def clone_model(self, dotted_path: str):
        module_path, model_name = dotted_path.rsplit('.', 1)
        model = getattr(importlib.import_module(module_path), model_name)

        state, _ = EtlState.objects.get_or_create(model_name=model_name)
        last_ts = state.last_synced
        now_ts = timezone.now()

        # Choose rows
        if model_name in FULL_SYNC_MODEL_NAMES:
            qs = model.objects.using("default").all()
        else:
            if hasattr(model, "updated_at"):
                qs = model.objects.using("default").filter(updated_at__gt=last_ts)
            else:
                # Warning: this copies ALL rows every run for models w/o updated_at
                qs = model.objects.using("default").all()

        src_rows = list(qs)
        if not src_rows:
            return

        self.stdout.write(f"  → cloning {len(src_rows)} {model_name} rows …")

        # Build clones using concrete field attname (FKs become *_id)
        clones = []
        for obj in src_rows:
            data = {}
            for f in model._meta.fields:
                data[f.attname] = getattr(obj, f.attname)
            clones.append(model(**data))

        pks = [o.pk for o in clones if o.pk is not None]
        if not pks:
            return

        # Fields to update (bulk_update expects FIELD NAMES, not attnames)
        update_fields = [f.name for f in model._meta.fields if not f.primary_key]

        # Unique fields (for conflict cleanup)
        unique_fields = [f for f in model._meta.fields if getattr(f, "unique", False) and not f.primary_key]

        with transaction.atomic(using="reporting"):
            # 1) Delete rows in reporting that would violate UNIQUE constraints for incoming rows
            #    (example: username already exists on a different id)
            for f in unique_fields:
                att = f.attname  # e.g. "username" or "email" or "user_id"
                vals = []
                for o in clones:
                    v = getattr(o, att, None)
                    if v is None:
                        continue
                    vals.append(v)

                if not vals:
                    continue

                (
                    model.objects.using("reporting")
                    .filter(**{f"{att}__in": vals})
                    .exclude(pk__in=pks)
                    .delete()
                )

            # 2) Upsert by PK without delete+insert (prevents cascades & is safer)
            existing_ids = set(
                model.objects.using("reporting")
                .filter(pk__in=pks)
                .values_list("pk", flat=True)
            )

            to_update = [o for o in clones if o.pk in existing_ids]
            to_create = [o for o in clones if o.pk not in existing_ids]

            if to_update:
                model.objects.using("reporting").bulk_update(
                    to_update,
                    update_fields,
                    batch_size=1000,
                )

            if to_create:
                model.objects.using("reporting").bulk_create(
                    to_create,
                    batch_size=1000,
                )

            # 3) If FULL sync model: delete rows in reporting that no longer exist in default
            if model_name in FULL_SYNC_MODEL_NAMES:
                src_ids = set(pks)
                model.objects.using("reporting").exclude(pk__in=src_ids).delete()

        # Update ETL state only after success
        state.last_synced = now_ts
        state.save(update_fields=["last_synced"])
