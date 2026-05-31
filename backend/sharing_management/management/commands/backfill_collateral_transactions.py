from django.core.management.base import BaseCommand
from django.db import transaction
from django.db import connection

from doctor_viewer.models import DoctorEngagement
from sharing_management.models import ShareLog
from sharing_management.services.transactions import (
    upsert_from_sharelog,
    mark_viewed,
    mark_pdf_progress,
    mark_video_event,
)


class Command(BaseCommand):
    help = "Backfill CollateralTransaction from existing ShareLog & engagement tables"

    def add_arguments(self, parser):
        parser.add_argument("--brand", dest="brand", default="")
        parser.add_argument("--share-id", dest="share_ids", action="append", type=int)
        parser.add_argument("--limit", dest="limit", type=int, default=0)

    def _table_columns(self, table_name):
        with connection.cursor() as cursor:
            if table_name not in connection.introspection.table_names(cursor):
                return set()
            return {
                column.name
                for column in connection.introspection.get_table_description(cursor, table_name)
            }

    def _hydrate_optional_sharelog_columns(self, share_log, columns):
        optional = [name for name in ("brand_campaign_id", "field_rep_email") if name in columns]
        for name in optional:
            share_log.__dict__.setdefault(name, "")
        if not optional:
            share_log.__dict__.setdefault("brand_campaign_id", "")
            share_log.__dict__.setdefault("field_rep_email", "")
            return

        table = ShareLog._meta.db_table
        qn = connection.ops.quote_name
        select_cols = ", ".join(qn(name) for name in optional)
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {select_cols} FROM {qn(table)} WHERE id = %s",
                [share_log.id],
            )
            row = cursor.fetchone()
        if row:
            for name, value in zip(optional, row):
                share_log.__dict__[name] = value or ""

    def _latest_engagement(self, share_log):
        short_link_id = getattr(share_log, "short_link_id", None)
        if not short_link_id:
            return None
        return (
            DoctorEngagement.objects.filter(short_link_id=short_link_id)
            .order_by("-updated_at", "-id")
            .first()
        )

    def _backfill_sharelog(self, share_log, brand, columns):
        self._hydrate_optional_sharelog_columns(share_log, columns)

        brand_campaign_id = brand or share_log.__dict__.get("brand_campaign_id", "")
        upsert_from_sharelog(
            share_log,
            brand_campaign_id=brand_campaign_id,
            sent_at=getattr(share_log, "share_timestamp", None),
        )

        engagement = self._latest_engagement(share_log)
        if not engagement:
            return

        when = getattr(engagement, "updated_at", None)
        mark_viewed(share_log, when=when)
        mark_pdf_progress(
            share_log,
            last_page=getattr(engagement, "last_page_scrolled", 0) or 0,
            completed=bool(getattr(engagement, "pdf_completed", False)),
            dv_engagement_id=getattr(engagement, "id", None),
            total_pages=0,
            when=when,
        )

        pct = int(getattr(engagement, "video_watch_percentage", 0) or 0)
        if pct > 0:
            mark_video_event(
                share_log,
                percentage=pct,
                event_id=0,
                when=when,
            )

    @transaction.atomic
    def handle(self, *args, **opts):
        brand = str(opts["brand"] or "").strip()
        share_ids = opts.get("share_ids") or []
        if isinstance(share_ids, int):
            share_ids = [share_ids]
        columns = self._table_columns(ShareLog._meta.db_table)
        safe_fields = [
            "id",
            "short_link",
            "collateral",
            "doctor_identifier",
            "share_channel",
            "share_timestamp",
            "field_rep_id",
        ]
        safe_fields.extend(name for name in ("brand_campaign_id", "field_rep_email") if name in columns)

        queryset = ShareLog.objects.only(*safe_fields).order_by("id")
        if share_ids:
            queryset = queryset.filter(id__in=share_ids)
        if opts.get("limit"):
            queryset = queryset[: opts["limit"]]

        count = 0
        for share_log in queryset:
            self._backfill_sharelog(share_log, brand, columns)
            count += 1

        self.stdout.write(self.style.SUCCESS(f"Backfill done: {count} share log(s) processed"))
