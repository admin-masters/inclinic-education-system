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
    "doctor_viewer.models.Doctor",
    "sharing_management.models.ShareLog",
    "doctor_viewer.models.DoctorEngagement",
]

DEFAULT_BATCH_SIZE = 1000


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


def _to_db_value(v):
    if isinstance(v, datetime) and timezone.is_aware(v):
        return timezone.make_naive(v, timezone.get_current_timezone())
    return v


def _show_columns(conn, table: str) -> dict:
    """
    Return MySQL SHOW COLUMNS metadata keyed by column name.
    Each value: {type, null_ok, default, key, extra}
    """
    qn = conn.ops.quote_name
    out = {}
    with conn.cursor() as cur:
        cur.execute(f"SHOW COLUMNS FROM {qn(table)}")
        for field, col_type, null, key, default, extra in cur.fetchall():
            out[str(field)] = {
                "type": (col_type or "").lower(),
                "null_ok": (str(null).upper() == "YES"),
                "default": default,
                "key": key,
                "extra": (extra or "").lower(),
            }
    return out


def _get_fk_map(conn, table: str) -> dict:
    """
    Map: column_name -> (referenced_table, referenced_column)
    Uses information_schema; if not permitted, returns {}.
    """
    db_name = conn.settings_dict.get("NAME")
    if not db_name:
        return {}

    sql = """
        SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
          AND REFERENCED_TABLE_NAME IS NOT NULL
    """
    out = {}
    try:
        with conn.cursor() as cur:
            cur.execute(sql, [db_name, table])
            for col, ref_tbl, ref_col in cur.fetchall():
                out[str(col)] = (str(ref_tbl), str(ref_col))
    except Exception:
        return {}
    return out


def _min_fk_value(conn, ref_table: str, ref_column: str):
    """
    Return MIN(ref_column) from ref_table, or None if not available.
    """
    qn = conn.ops.quote_name
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT MIN({qn(ref_column)}) FROM {qn(ref_table)}")
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:
        return None


def _is_int_type(mysql_type: str) -> bool:
    t = (mysql_type or "").lower()
    return "int" in t and "point" not in t


def _is_numeric_type(mysql_type: str) -> bool:
    t = (mysql_type or "").lower()
    return any(x in t for x in ("int", "decimal", "numeric", "float", "double"))


def _is_datetime_type(mysql_type: str) -> bool:
    t = (mysql_type or "").lower()
    return any(x in t for x in ("datetime", "timestamp"))


def _is_date_type(mysql_type: str) -> bool:
    t = (mysql_type or "").lower()
    return t.startswith("date") and "datetime" not in t


def _default_value_for(col: str, info: dict, *, now_naive):
    """
    Choose a safe non-null value for a NOT NULL column when source has NULL.
    Priority:
      1) Column default (if literal)
      2) Type-based fallback (0, '', safe date)
    """
    mysql_type = (info.get("type") or "").lower()
    default = info.get("default", None)

    # If there is a default (and it's not NULL), try to use it.
    if default is not None:
        d = default
        if isinstance(d, str):
            up = d.upper()
            if "CURRENT_TIMESTAMP" in up:
                return now_naive
        if _is_int_type(mysql_type):
            try:
                return int(d)
            except Exception:
                return 0
        if _is_numeric_type(mysql_type):
            try:
                return float(d)
            except Exception:
                return 0
        return d

    # Type-based fallbacks
    if _is_int_type(mysql_type) or _is_numeric_type(mysql_type):
        return 0
    if _is_datetime_type(mysql_type):
        # safe + reasonable
        return now_naive if now_naive.year >= 1000 else datetime(1000, 1, 1)
    if _is_date_type(mysql_type):
        return datetime(1000, 1, 1).date()
    return ""


class Command(BaseCommand):
    help = "Incrementally copy updated rows from default DB → reporting DB (raw SQL; UUID-safe; NOT-NULL safe)."

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

        # Columns metadata
        try:
            src_info = _show_columns(src, table)
            dst_info = _show_columns(dst, table)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"  ! {model_name}: unable to read columns for {table}: {e}"))
            return

        src_cols = list(src_info.keys())
        dst_cols = list(dst_info.keys())

        # intersection columns
        common_cols = [c for c in src_cols if c in dst_cols]
        if not common_cols:
            self.stdout.write(self.style.WARNING(f"  ! {model_name}: no common columns for {table}, skipping"))
            return
        if pk_col not in common_cols:
            self.stdout.write(self.style.WARNING(f"  ! {model_name}: pk column {pk_col} missing in {table}, skipping"))
            return

        # destination-only required columns (NOT NULL, no default, not auto-inc)
        required_dst_only = []
        for c in dst_cols:
            if c in common_cols:
                continue
            info = dst_info.get(c, {})
            if info.get("null_ok", True):
                continue
            if info.get("default", None) is not None:
                continue
            if "auto_increment" in (info.get("extra") or ""):
                continue
            required_dst_only.append(c)

        insert_cols = list(common_cols) + required_dst_only

        # incremental column
        inc_col = None
        for cand in (
            "updated_at",
            "modified_at",
            "modified_on",
            "updated_on",
            "last_updated",
            "date_modified",
            "created_at",
            "date_created",
        ):
            if cand in common_cols:
                inc_col = cand
                break

        where_sql = ""
        params = []
        if (not force_full) and inc_col:
            ts_param = _safe_mysql_ts(last_ts)
            if ts_param:
                where_sql = f" WHERE {qn_src(inc_col)} > %s"
                params.append(ts_param)

        select_sql = f"SELECT {', '.join(qn_src(c) for c in common_cols)} FROM {qn_src(table)}{where_sql}"

        with src.cursor() as cur:
            cur.execute(select_sql, params)
            rows = cur.fetchall()

        if not rows:
            return

        self.stdout.write(f"  → cloning {len(rows)} {model_name} rows …")

        # FK fallbacks for NOT NULL FK columns
        fk_map = _get_fk_map(dst, table)  # col -> (ref_table, ref_col)
        fk_fallbacks = {}
        for c in insert_cols:
            if c in fk_map:
                ref_tbl, ref_col = fk_map[c]
                fk_fallbacks[c] = _min_fk_value(dst, ref_tbl, ref_col)

        now_naive = _to_db_value(now_ts)

        # ShareLog: map field_rep_email -> reporting user id (best effort)
        email_to_user_id = {}
        sharelog_fieldrep_idx = None
        sharelog_email_idx = None
        fr_idx_common = None
        em_idx_common = None

        if model_name == "ShareLog" and "field_rep_id" in insert_cols:
            sharelog_fieldrep_idx = insert_cols.index("field_rep_id")
            if "field_rep_email" in insert_cols:
                sharelog_email_idx = insert_cols.index("field_rep_email")

            if "field_rep_id" in common_cols:
                fr_idx_common = common_cols.index("field_rep_id")
            if "field_rep_email" in common_cols:
                em_idx_common = common_cols.index("field_rep_email")

            # Only build map if we can read email from source rows
            if em_idx_common is not None:
                emails = []
                for r in rows:
                    if fr_idx_common is not None and r[fr_idx_common] is not None:
                        continue
                    em = r[em_idx_common]
                    if em:
                        emails.append(str(em).strip().lower())

                emails = list({e for e in emails if e})
                if emails:
                    try:
                        user_model = getattr(importlib.import_module("user_management.models"), "User")
                        user_table = user_model._meta.db_table
                        with dst.cursor() as cur:
                            for chunk in _chunks(emails, 500):
                                ph = ", ".join(["%s"] * len(chunk))
                                cur.execute(
                                    f"SELECT id, email FROM {qn_dst(user_table)} WHERE LOWER(email) IN ({ph})",
                                    chunk,
                                )
                                for uid, em in cur.fetchall():
                                    if em:
                                        email_to_user_id[str(em).strip().lower()] = uid
                    except Exception:
                        email_to_user_id = {}

        fixed_rows = []
        patched_counts = {}

        for r in rows:
            row = list(r)

            # append dst-only required columns
            for c in required_dst_only:
                info = dst_info.get(c, {})
                row.append(_default_value_for(c, info, now_naive=now_naive))

            # Patch NULLs for NOT NULL columns
            for idx, col in enumerate(insert_cols):
                info = dst_info.get(col, {})
                if info.get("null_ok", True):
                    continue
                if row[idx] is not None:
                    continue

                fk_fb = fk_fallbacks.get(col, None)
                if fk_fb not in (None, ""):
                    row[idx] = fk_fb
                else:
                    row[idx] = _default_value_for(col, info, now_naive=now_naive)

                patched_counts[col] = patched_counts.get(col, 0) + 1

            # ShareLog: if field_rep_id still empty, try mapping by email
            if model_name == "ShareLog" and sharelog_fieldrep_idx is not None:
                if row[sharelog_fieldrep_idx] in (None, ""):
                    mapped = None
                    if sharelog_email_idx is not None and row[sharelog_email_idx]:
                        em = str(row[sharelog_email_idx]).strip().lower()
                        mapped = email_to_user_id.get(em)
                    if mapped is not None:
                        row[sharelog_fieldrep_idx] = mapped
                    else:
                        # final fallback if still NULL (should not happen)
                        info = dst_info.get("field_rep_id", {})
                        if not info.get("null_ok", True) and row[sharelog_fieldrep_idx] is None:
                            row[sharelog_fieldrep_idx] = _default_value_for("field_rep_id", info, now_naive=now_naive)

            fixed_rows.append(tuple(_to_db_value(v) for v in row))

        if patched_counts:
            self.stdout.write(f"    patched NULLs for NOT NULL cols: {patched_counts}")

        cols_sql = ", ".join(qn_dst(c) for c in insert_cols)
        placeholders = ", ".join(["%s"] * len(insert_cols))

        # UPSERT: update all non-PK columns
        update_cols = [c for c in insert_cols if c != pk_col]
        if update_cols:
            update_sql = ", ".join(f"{qn_dst(c)}=VALUES({qn_dst(c)})" for c in update_cols)
            upsert_sql = (
                f"INSERT INTO {qn_dst(table)} ({cols_sql}) VALUES ({placeholders}) "
                f"ON DUPLICATE KEY UPDATE {update_sql}"
            )
        else:
            upsert_sql = f"INSERT INTO {qn_dst(table)} ({cols_sql}) VALUES ({placeholders})"

        with transaction.atomic(using="reporting"):
            with dst.cursor() as dst_cur:
                for batch in _chunks(fixed_rows, batch_size):
                    dst_cur.executemany(upsert_sql, batch)

        state.last_synced = now_ts
        state.save(update_fields=["last_synced"])
