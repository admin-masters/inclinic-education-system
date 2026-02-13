"""
Usage:  python manage.py run_etl
Cron :  0 */3 * * *  /path/venv/bin/python /app/manage.py run_etl   # every 3 h
"""
import importlib
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import connections, transaction
from django.utils import timezone

from reporting_etl.models import EtlState

MODEL_PATHS = [
    "user_management.models.User",
    "campaign_management.models.Campaign",
    "collateral_management.models.Collateral",
    "shortlink_management.models.ShortLink",
    "sharing_management.models.ShareLog",
    "doctor_viewer.models.Doctor",
    "doctor_viewer.models.DoctorEngagement",
]

DEFAULT_BATCH_SIZE = 1000
IN_CHUNK = 500  # for IN(...) deletes


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _safe_mysql_ts(ts):
    """
    MySQL DATETIME can't represent year 1; protect against datetime.min-like values.
    Also make tz-aware -> naive for MySQL param binding safety.
    """
    if not ts:
        return None
    if ts.year < 1000:
        ts = timezone.make_aware(datetime(1000, 1, 1))
    if timezone.is_aware(ts):
        return timezone.make_naive(ts, timezone.get_current_timezone())
    return ts


class Command(BaseCommand):
    help = "Incrementally copy updated rows from default DB → reporting DB (raw SQL copy; UUID-safe)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--full-refresh",
            action="store_true",
            help="TRUNCATE reporting tables and resync everything from scratch.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            help="Insert batch size (default: 1000).",
        )

    def handle(self, *args, **options):
        batch_size = int(options["batch_size"] or DEFAULT_BATCH_SIZE)

        if options.get("full_refresh"):
            self.full_refresh()

        self.stdout.write(self.style.SUCCESS("Starting ETL …"))
        for path in MODEL_PATHS:
            self.clone_model(path, batch_size=batch_size, force_full=options.get("full_refresh", False))
        self.stdout.write(self.style.SUCCESS("ETL finished."))

    def full_refresh(self):
        """
        Optional one-time cleanup if reporting DB has drift (old IDs / duplicates).
        Safe if reporting DB is purely derived.
        """
        self.stdout.write(self.style.WARNING("FULL REFRESH: truncating reporting tables + resetting EtlState"))

        rep = connections["reporting"]
        qn = rep.ops.quote_name

        with rep.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            for path in reversed(MODEL_PATHS):
                module_path, model_name = path.rsplit(".", 1)
                model = getattr(importlib.import_module(module_path), model_name)
                cur.execute(f"TRUNCATE TABLE {qn(model._meta.db_table)}")
            cur.execute("SET FOREIGN_KEY_CHECKS=1")

        EtlState.objects.all().delete()

    def clone_model(self, dotted_path: str, *, batch_size: int = 1000, force_full: bool = False):
        module_path, model_name = dotted_path.rsplit(".", 1)
        model = getattr(importlib.import_module(module_path), model_name)

        state, _ = EtlState.objects.get_or_create(model_name=model_name)
        last_ts = state.last_synced
        now_ts = timezone.now()

        src = connections["default"]
        dst = connections["reporting"]
        qn_src = src.ops.quote_name
        qn_dst = dst.ops.quote_name

        table = model._meta.db_table
        pk_col = model._meta.pk.column

        # Columns present in BOTH (tolerates minor schema drift)
        with src.cursor() as c:
            src_cols = [col.name for col in src.introspection.get_table_description(c, table)]
        with dst.cursor() as c:
            dst_cols = [col.name for col in dst.introspection.get_table_description(c, table)]

        cols = [c for c in src_cols if c in dst_cols]
        if not cols:
            self.stdout.write(self.style.WARNING(f"  ! {model_name}: no common columns for {table}, skipping"))
            return
        if pk_col not in cols:
            self.stdout.write(self.style.WARNING(f"  ! {model_name}: pk column {pk_col} missing in {table}, skipping"))
            return

        # Pick incremental column if it exists
        inc_col = None
        for cand in (
            "updated_at",
            "modified_at",
            "updated_on",
            "last_updated",
            "date_modified",
            "created_at",
            "date_created",
        ):
            if cand in cols:
                inc_col = cand
                break

        where_sql = ""
        params = []
        if (not force_full) and inc_col:
            ts_param = _safe_mysql_ts(last_ts)
            if ts_param:
                where_sql = f" WHERE {qn_src(inc_col)} > %s"
                params.append(ts_param)

        select_sql = f"SELECT {', '.join(qn_src(c) for c in cols)} FROM {qn_src(table)}{where_sql}"

        # RAW FETCH: avoids Django UUID conversion completely
        with src.cursor() as cur:
            cur.execute(select_sql, params)
            rows = cur.fetchall()

        if not rows:
            return

        self.stdout.write(f"  → cloning {len(rows)} {model_name} rows …")

        # Pre-clean unique conflicts (single-column unique=True fields)
        unique_cols = []
        for f in model._meta.fields:
            if getattr(f, "unique", False) and not getattr(f, "primary_key", False):
                if f.column in cols:
                    unique_cols.append(f.column)

        placeholders = ", ".join(["%s"] * len(cols))
        cols_sql = ", ".join(qn_dst(c) for c in cols)
        insert_sql = f"INSERT INTO {qn_dst(table)} ({cols_sql}) VALUES ({placeholders})"

        pk_idx = cols.index(pk_col)
        pks = [r[pk_idx] for r in rows]

        with transaction.atomic(using="reporting"):
            with dst.cursor() as cur:
                # 1) delete by unique columns to avoid 1062 collisions (e.g., username)
                for ucol in unique_cols:
                    uidx = cols.index(ucol)
                    uvals = [r[uidx] for r in rows if r[uidx] not in (None, "")]
                    if not uvals:
                        continue
                    # de-dupe
                    seen = set()
                    uuniq = []
                    for v in uvals:
                        if v in seen:
                            continue
                        seen.add(v)
                        uuniq.append(v)

                    for chunk in _chunks(uuniq, IN_CHUNK):
                        ph = ", ".join(["%s"] * len(chunk))
                        cur.execute(
                            f"DELETE FROM {qn_dst(table)} WHERE {qn_dst(ucol)} IN ({ph})",
                            chunk,
                        )

                # 2) delete by PK (classic upsert-by-pk via delete+insert)
                for chunk in _chunks(pks, IN_CHUNK):
                    ph = ", ".join(["%s"] * len(chunk))
                    cur.execute(
                        f"DELETE FROM {qn_dst(table)} WHERE {qn_dst(pk_col)} IN ({ph})",
                        chunk,
                    )

                # 3) insert rows in batches
                for chunk in _chunks(rows, batch_size):
                    cur.executemany(insert_sql, chunk)

        # update state only if successful
        state.last_synced = now_ts
        state.save(update_fields=["last_synced"])
