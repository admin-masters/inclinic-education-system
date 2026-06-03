from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, connections
from django.utils import timezone

from reporting_etl.inclinic_v2 import clean_text, load_source_csv, table_exists


DEFAULT_CSV_DIR = "/Users/inditech-tech/Desktop/InclinicLocalMasterNewCsvs"
METADATA_PREFIX = "_"

TABLE_PRIORITY = {
    "auth_user": 10,
    "user_management_user": 10,
    "campaign_campaign": 20,
    "campaign_management_campaign": 20,
    "campaign_fieldrep": 30,
    "collateral_management_collateral": 30,
    "campaign_campaignfieldrep": 40,
    "campaign_management_campaignassignment": 40,
    "admin_dashboard_fieldrepcampaign": 40,
    "collateral_management_campaigncollateral": 40,
    "doctor_viewer_doctor": 50,
    "prefilled_doctor": 50,
    "sharing_management_fieldrepresentative": 50,
    "sharing_management_sharelog": 60,
    "sharing_management_collateraltransaction": 70,
}


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    nullable: bool
    default: Any
    extra: str
    data_type: str


class Command(BaseCommand):
    help = "Insert missing raw source CSV rows into local sample DB tables without updating existing rows."

    def add_arguments(self, parser):
        parser.add_argument("--csv-dir", default=DEFAULT_CSV_DIR)
        parser.add_argument("--default-alias", default="default")
        parser.add_argument("--master-alias", default=getattr(settings, "MASTER_DB_ALIAS", "master"))
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--report-path", default="")
        parser.add_argument(
            "--ensure-missing-master-brands",
            action="store_true",
            help="Create placeholder campaign_brand rows for brand_id values referenced by master CSVs.",
        )

    def handle(self, *args, **options):
        self.csv_dir = Path(options["csv_dir"])
        self.default_alias = options["default_alias"]
        self.master_alias = options["master_alias"]
        self.dry_run = options["dry_run"]
        self.report_lines: list[str] = []

        if not self.csv_dir.exists():
            raise CommandError(f"CSV directory not found: {self.csv_dir}")

        files = sorted(self.csv_dir.glob("raw_server*.csv"), key=self.sort_key)
        if not files:
            raise CommandError(f"No raw_server*.csv files found in: {self.csv_dir}")

        self.report(f"CSV sample ingest started: {timezone.now().isoformat()}")
        self.report(f"csv_dir: {self.csv_dir}")
        self.report(f"dry_run: {self.dry_run}")

        totals = {"files": 0, "rows": 0, "inserted": 0, "existing": 0, "skipped": 0, "errors": 0}
        if options["ensure_missing_master_brands"]:
            inserted, existing = self.ensure_missing_master_brands(files)
            totals["inserted"] += inserted
            totals["existing"] += existing

        for path in files:
            result = self.ingest_file(path)
            for key, value in result.items():
                totals[key] = totals.get(key, 0) + value

        self.report("")
        self.report("Totals")
        for key in ("files", "rows", "inserted", "existing", "skipped", "errors"):
            self.report(f"{key}: {totals[key]}")

        report_path = options["report_path"]
        if not report_path:
            report_path = f"backend/reporting_etl/reports/source_csv_sample_ingest_{timezone.now():%Y%m%d%H%M%S}.txt"
        report_file = Path(report_path)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text("\n".join(self.report_lines) + "\n", encoding="utf-8")

        self.stdout.write(self.style.SUCCESS("CSV sample ingest completed."))
        self.stdout.write(f"Report: {report_file}")
        self.stdout.write(f"Inserted: {totals['inserted']}, existing: {totals['existing']}, skipped: {totals['skipped']}, errors: {totals['errors']}")

    def ensure_missing_master_brands(self, files: list[Path]) -> tuple[int, int]:
        if not table_exists(self.master_alias, "campaign_brand"):
            self.report("")
            self.report("campaign_brand parent ensure skipped: master.campaign_brand table does not exist")
            return 0, 0

        brand_ids: set[str] = set()
        for path in files:
            alias, table = self.resolve_file(path)
            if alias != self.master_alias or table not in {"campaign_campaign", "campaign_fieldrep"}:
                continue
            for row in load_source_csv(path):
                brand_id = clean_text(row.get("brand_id"))
                if brand_id:
                    brand_ids.add(brand_id)

        inserted = 0
        existing = 0
        for brand_id in sorted(brand_ids, key=lambda value: int(value) if value.isdigit() else value):
            if self.row_exists(self.master_alias, "campaign_brand", {"id": brand_id}):
                existing += 1
                continue
            if not self.dry_run:
                self.insert_row(
                    self.master_alias,
                    "campaign_brand",
                    {
                        "id": brand_id,
                        "company_name": f"Sample Brand {brand_id}",
                        "name": f"Sample Brand {brand_id}",
                    },
                )
            inserted += 1

        self.report("")
        self.report("master.campaign_brand parent ensure")
        self.report(f"  inserted={inserted}, existing={existing}")
        return inserted, existing

    def sort_key(self, path: Path):
        alias, table = self.resolve_file(path)
        alias_priority = 0 if alias == self.master_alias else 100
        return (alias_priority + TABLE_PRIORITY.get(table, 999), path.name)

    def resolve_file(self, path: Path) -> tuple[str, str]:
        name = path.name
        if name.startswith("raw_server1."):
            return self.master_alias, name.removeprefix("raw_server1.").removesuffix(".csv")
        if name.startswith("raw_server2."):
            return self.default_alias, name.removeprefix("raw_server2.").removesuffix(".csv")
        return self.default_alias, name.removesuffix(".csv")

    def ingest_file(self, path: Path) -> dict[str, int]:
        alias, table = self.resolve_file(path)
        result = {"files": 1, "rows": 0, "inserted": 0, "existing": 0, "skipped": 0, "errors": 0}
        rows = load_source_csv(path)
        result["rows"] = len(rows)

        if not table_exists(alias, table):
            result["skipped"] = len(rows)
            self.report("")
            self.report(f"{path.name} -> {alias}.{table}")
            self.report(f"  skipped: table does not exist ({len(rows)} rows)")
            return result

        columns = self.get_columns(alias, table)
        pk_columns = self.get_primary_key_columns(alias, table)
        real_column_names = {column.name for column in columns}
        writable_columns = columns
        csv_real_columns = [name for name in (rows[0].keys() if rows else []) if name in real_column_names and not name.startswith(METADATA_PREFIX)]

        self.report("")
        self.report(f"{path.name} -> {alias}.{table}")
        self.report(f"  source rows after dedupe/delete-filter: {len(rows)}")
        self.report(f"  usable CSV columns: {len(csv_real_columns)}")

        for row in rows:
            pk_values = {pk: row.get(pk) for pk in pk_columns}
            if not pk_columns or any(clean_text(value) == "" for value in pk_values.values()):
                result["skipped"] += 1
                continue

            if self.row_exists(alias, table, pk_values):
                result["existing"] += 1
                continue

            insert_data = self.build_insert_data(row, writable_columns)
            if not insert_data:
                result["skipped"] += 1
                continue

            if self.dry_run:
                result["inserted"] += 1
                continue

            try:
                self.insert_row(alias, table, insert_data)
                result["inserted"] += 1
            except Exception as exc:
                connections[alias].rollback()
                result["errors"] += 1
                self.report(f"  error pk={pk_values}: {exc}")

        self.report(
            "  inserted={inserted}, existing={existing}, skipped={skipped}, errors={errors}".format(
                **result
            )
        )
        return result

    def get_columns(self, alias: str, table: str) -> list[ColumnInfo]:
        db_name = connections[alias].settings_dict["NAME"]
        with connections[alias].cursor() as cursor:
            cursor.execute(
                """
                SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT, EXTRA, DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
                """,
                [db_name, table],
            )
            return [
                ColumnInfo(
                    name=row[0],
                    nullable=row[1] == "YES",
                    default=row[2],
                    extra=row[3] or "",
                    data_type=row[4] or "",
                )
                for row in cursor.fetchall()
            ]

    def get_primary_key_columns(self, alias: str, table: str) -> list[str]:
        with connections[alias].cursor() as cursor:
            cursor.execute(f"SHOW KEYS FROM {connections[alias].ops.quote_name(table)} WHERE Key_name = 'PRIMARY'")
            rows = cursor.fetchall()
        return [row[4] for row in sorted(rows, key=lambda item: item[3])] or ["id"]

    def row_exists(self, alias: str, table: str, pk_values: dict[str, Any]) -> bool:
        qn = connections[alias].ops.quote_name
        where = " AND ".join(f"{qn(column)} = %s" for column in pk_values)
        sql = f"SELECT 1 FROM {qn(table)} WHERE {where} LIMIT 1"
        with connections[alias].cursor() as cursor:
            cursor.execute(sql, list(pk_values.values()))
            return cursor.fetchone() is not None

    def build_insert_data(self, row: dict[str, Any], columns: list[ColumnInfo]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for column in columns:
            has_csv_value = column.name in row and not column.name.startswith(METADATA_PREFIX)
            if has_csv_value:
                value = row.get(column.name)
                value = self.prepare_value(value, column)
                if value is _OMIT:
                    continue
                data[column.name] = value
            elif self.needs_missing_required_value(column):
                data[column.name] = self.required_fallback(column)
        return data

    def prepare_value(self, value: Any, column: ColumnInfo):
        if value is None or value == "":
            if column.nullable:
                return None
            if column.default is not None:
                return _OMIT
            return self.required_fallback(column)
        return value

    def needs_missing_required_value(self, column: ColumnInfo) -> bool:
        if column.nullable or column.default is not None:
            return False
        return "auto_increment" not in column.extra.lower()

    def required_fallback(self, column: ColumnInfo):
        if column.name == "password":
            return "!sample-unusable-password"
        if column.name in {"security_answer_hash", "temp_password_hash"}:
            return b""
        if column.data_type in {"tinyint", "smallint", "int", "bigint", "decimal", "float", "double"}:
            return 0
        if column.data_type in {"date", "datetime", "timestamp"}:
            return timezone.now()
        return ""

    def insert_row(self, alias: str, table: str, data: dict[str, Any]):
        qn = connections[alias].ops.quote_name
        columns = list(data)
        placeholders = ", ".join(["%s"] * len(columns))
        quoted_columns = ", ".join(qn(column) for column in columns)
        sql = f"INSERT INTO {qn(table)} ({quoted_columns}) VALUES ({placeholders})"
        with connections[alias].cursor() as cursor:
            cursor.execute(sql, [data[column] for column in columns])

    def report(self, line: str):
        self.report_lines.append(line)
        self.stdout.write(line)


class _Omit:
    pass


_OMIT = _Omit()
