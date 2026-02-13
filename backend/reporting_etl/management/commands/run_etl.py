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

# Order matters: parents first (prevents FK insert failures)
MODEL_PATHS = [
    "user_management.models.User",
    "campaign_management.models.Campaign",
    "collateral_management.models.Collateral",
    "shortlink_management.models.ShortLink",
    "doctor_viewer.models.Doctor",
    "sharing_management.models.ShareLog",
    "doctor_viewer.models.DoctorEngagement",
]

DEFAULT_BATCH_SIZE = 1000
IN_CHUNK = 500  # for IN(...) selects/updates


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


def _make_conflict_value(orig, pk, max_len=None):
    """
    Create a deterministic "moved aside" value for unique-field conflicts.
    We do NOT delete rows (avoids FK constraint issues).
    """
    base = str(orig or "").strip()
    suffix = f"__old__{pk}"

    if not base:
        base = "old"

    if max_len is None:
        return base + suffix

    # If suffix alone doesn't fit, fallback to something pk-based.
    if max_len <= len(suffix):
        v = f"old{pk}"
        return v[-max_len:] if len(v) > max_len else v

    prefix_len = max_len - len(suffix)
    return base[:prefix_len] + suffix


class Command(BaseCommand):
    help = (
        "Incrementally copy updated rows from default DB → reporting DB.\n"
        "Uses raw SQL fetch (UUID-safe) + MySQL UPSERT (FK-safe) + unique-conflict mitigation."
    )

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
            help="Fetch/insert batch size (default: 1000).",
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

        # Count first (for logging)
        count_sql = f"SELECT COUNT(*) FROM {qn_src(table)}{where_sql}"
        with src.cursor() as cur:
            cur.execute(count_sql, params)
            total = int(cur.fetchone()[0] or 0)

        if total <= 0:
            return

        self.stdout.write(f"  → cloning {total} {model_name} rows …")

        # Build SELECT (raw fetch avoids UUID conversion issues)
        select_sql = (
            f"SELECT {', '.join(qn_src(c) for c in cols)} "
            f"FROM {qn_src(table)}{where_sql} "
            f"ORDER BY {qn_src(pk_col)}"
        )

        # Detect single-column unique fields (best-effort)
        col_to_field = {f.column: f for f in model._meta.fields}
        unique_cols = []
        for f in model._meta.fields:
            if getattr(f, "unique", False) and not getattr(f, "primary_key", False):
                if f.column in cols:
                    unique_cols.append(f.column)

        # Build UPSERT SQL (FK-safe: no deletes)
        placeholders = ", ".join(["%s"] * len(cols))
        cols_sql = ", ".join(qn_dst(c) for c in cols)

        update_cols = [c for c in cols if c != pk_col]
        if update_cols:
            update_sql = ", ".join(
                f"{qn_dst(c)}=VALUES({qn_dst(c)})" for c in update_cols
            )
        else:
            # No-op update to satisfy syntax
            update_sql = f"{qn_dst(pk_col)}={qn_dst(pk_col)}"

        upsert_sql = (
            f"INSERT INTO {qn_dst(table)} ({cols_sql}) "
            f"VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {update_sql}"
        )

        pk_idx = cols.index(pk_col)

        with transaction.atomic(using="reporting"):
            with src.cursor() as src_cur, dst.cursor() as dst_cur:
                src_cur.execute(select_sql, params)

                processed = 0
                while True:
                    batch = src_cur.fetchmany(batch_size)
                    if not batch:
                        break

                    processed += len(batch)

                    # --------------------------
                    # 1) Resolve UNIQUE conflicts (without deleting rows)
                    # --------------------------
                    # For each unique column, if reporting has same value on a different PK,
                    # rename the old row's unique value so we can insert the correct row.
                    for ucol in unique_cols:
                        uidx = cols.index(ucol)
                        field = col_to_field.get(ucol)
                        max_len = getattr(field, "max_length", None)
                        can_null = bool(getattr(field, "null", False))

                        # map unique_value -> incoming_pk (unique values should be unique in source)
                        incoming_map = {}
                        incoming_vals = []
                        for r in batch:
                            v = r[uidx]
                            if v in (None, ""):
                                continue
                            # keep first mapping
                            if v not in incoming_map:
                                incoming_map[v] = r[pk_idx]
                                incoming_vals.append(v)

                        if not incoming_vals:
                            continue

                        # find existing rows in reporting that have any of these unique values
                        for val_chunk in _chunks(incoming_vals, IN_CHUNK):
                            ph = ", ".join(["%s"] * len(val_chunk))
                            sel = (
                                f"SELECT {qn_dst(pk_col)}, {qn_dst(ucol)} "
                                f"FROM {qn_dst(table)} "
                                f"WHERE {qn_dst(ucol)} IN ({ph})"
                            )
                            dst_cur.execute(sel, val_chunk)
                            existing = dst_cur.fetchall()

                            updates = []
                            for row_pk, row_val in existing:
                                expected_pk = incoming_map.get(row_val)
                                if expected_pk is None:
                                    continue
                                if row_pk == expected_pk:
                                    continue  # same row, safe

                                # conflict: move aside old value on the old row
                                if isinstance(row_val, (bytes, bytearray)):
                                    # If a unique column is bytes (rare), we cannot safely "rename".
                                    # Best effort: NULL it if allowed; otherwise skip and let insert fail.
                                    if can_null:
                                        new_val = None
                                    else:
                                        continue
                                else:
                                    if isinstance(row_val, str):
                                        new_val = _make_conflict_value(row_val, row_pk, max_len=max_len)
                                    else:
                                        # numeric unique: NULL if possible, else set to row_pk (best effort)
                                        if can_null:
                                            new_val = None
                                        else:
                                            new_val = row_pk

                                updates.append((new_val, row_pk))

                            if updates:
                                upd = (
                                    f"UPDATE {qn_dst(table)} "
                                    f"SET {qn_dst(ucol)}=%s "
                                    f"WHERE {qn_dst(pk_col)}=%s"
                                )
                                dst_cur.executemany(upd, updates)

                    # --------------------------
                    # 2) UPSERT batch
                    # --------------------------
                    dst_cur.executemany(upsert_sql, batch)

        # update state only if successful
        state.last_synced = now_ts
        state.save(update_fields=["last_synced"])
