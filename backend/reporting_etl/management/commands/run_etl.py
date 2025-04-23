"""
Usage:  python manage.py run_etl          # one‑off
Cron :  0 */3 * * *  /path/venv/bin/python /app/manage.py run_etl   # every 3 h
Celery: see tasks.py below
"""
import importlib, itertools
from django.core.management.base import BaseCommand
from django.db import transaction, connections
from django.utils import timezone

from reporting_etl.models import EtlState

# List the models you want to replicate
MODEL_PATHS = [
    'campaign_management.models.Campaign',
    'collateral_management.models.Collateral',
    'shortlink_management.models.ShortLink',
    'sharing_management.models.ShareLog',
    'doctor_viewer.models.DoctorEngagement',
]

class Command(BaseCommand):
    help = "Incrementally copy updated rows from default DB → reporting DB"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting ETL …"))
        for path in MODEL_PATHS:
            self.clone_model(path)
        self.stdout.write(self.style.SUCCESS("ETL finished."))

    # ------------------------------------------------------------
    def clone_model(self, dotted_path: str):
        module_path, model_name = dotted_path.rsplit('.', 1)
        model = getattr(importlib.import_module(module_path), model_name)

        state, _ = EtlState.objects.get_or_create(model_name=model_name)
        last_ts  = state.last_synced
        now_ts   = timezone.now()

        # rows changed since last sync
        qs = model.objects.using('default').filter(updated_at__gt=last_ts)

        if not qs.exists():
            return

        self.stdout.write(f"  → cloning {qs.count()} {model_name} rows …")

        objs_to_insert = []
        for obj in qs:
            # Clone field values (excluding PK to allow upsert)
            data = {f.name: getattr(obj, f.name) for f in obj._meta.fields if f.name != 'id'}
            data['id'] = obj.id          # keep same PK
            objs_to_insert.append(model(**data))

        with transaction.atomic(using='reporting'):
            # delete any PKs we're about to insert (acts like UPSERT)
            pks = [o.id for o in objs_to_insert]
            model.objects.using('reporting').filter(id__in=pks).delete()
            model.objects.using('reporting').bulk_create(objs_to_insert, batch_size=1000)

        # update ETL state
        state.last_synced = now_ts
        state.save(update_fields=['last_synced'])