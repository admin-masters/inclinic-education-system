from __future__ import annotations

import csv
import io
import json
import traceback
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.utils import timezone

from reporting_etl.inclinic_v2 import (
    SYSTEM_NAME,
    TARGET_CAMPAIGN_ID,
    clean_text,
    fetch_rows,
    normalize_campaign_id,
    source_database,
    stable_uuid,
    table_exists,
)
from reporting_etl.models import (
    InclinicCampaignCollateralV2,
    InclinicCampaignFieldRepAssignmentV2,
    InclinicCollateralTransactionV2,
    InclinicCollateralV2,
    InclinicDoctorV2,
    InclinicFieldRepIdentityV2,
    InclinicNonAuthoritativeAssignmentAuditV2,
    InclinicShareEventV2,
    MigrationExceptionV2,
    SourceMigrationBatchV2,
)
from reporting_etl.v2_switch import activate_v2_batch


@dataclass(frozen=True)
class SourceValidationSpec:
    label: str
    alias: str
    source_table: str
    destination_model: Any
    destination_table: str
    destination_pk_field: str
    critical_field_map: tuple[tuple[str, str], ...] = ()
    required: bool = True


SUCCESS_FIELDS = [
    "batch_id",
    "source_database",
    "source_table",
    "source_pk_column",
    "source_pk_value",
    "destination_table",
    "destination_pk_values",
    "status",
    "validation_status",
    "message",
]

FAILURE_FIELDS = [
    "batch_id",
    "source_database",
    "source_table",
    "source_pk_column",
    "source_pk_value",
    "destination_table",
    "failure_type",
    "failure_reason",
    "stack_trace",
]

RECON_FIELDS = [
    "source_table",
    "destination_table",
    "source_database",
    "total_source_records",
    "total_migrated_source_records",
    "missing_records",
    "field_mismatch_records",
    "destination_rows",
    "validation_status",
]

EXCEPTION_FIELDS = [
    "exception_id",
    "migration_batch_id",
    "source_table",
    "source_pk_column",
    "source_pk_value",
    "entity_type",
    "issue_code",
    "issue_details",
    "resolution_status",
]

DRY_RUN_COUNT_FIELDS = [
    "entity",
    "v1_database",
    "v1_table",
    "v1_count",
    "v2_database",
    "v2_table",
    "v2_count_after_dry_run",
    "v2_current_after_dry_run",
    "v2_excluded_after_dry_run",
    "note",
]


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat(sep=" ")
    return str(value).strip()


def _same_value(left: Any, right: Any) -> bool:
    left_text = _as_text(left)
    right_text = _as_text(right)
    if left_text == right_text:
        return True
    if left_text.lower() in {"true", "false"} or right_text.lower() in {"true", "false"}:
        return (left_text.lower() in {"true", "1"}) == (right_text.lower() in {"true", "1"})
    try:
        return float(left_text) == float(right_text)
    except Exception:
        return False


class Command(BaseCommand):
    help = (
        "Safely migrate InClinic V1 source tables into v2 lineage/reporting tables, "
        "then generate audit reports and optionally activate v2 reads after validation passes."
    )

    def add_arguments(self, parser):
        parser.add_argument("--batch-id", default="")
        parser.add_argument("--created-by", default="codex")
        parser.add_argument("--campaign-id", default=TARGET_CAMPAIGN_ID)
        parser.add_argument("--default-alias", default="default")
        parser.add_argument("--master-alias", default=getattr(settings, "MASTER_DB_ALIAS", "master"))
        parser.add_argument("--report-dir", default="")
        parser.add_argument("--skip-mismatch-csv", action="store_true")
        parser.add_argument("--mismatch-csv", default="")
        parser.add_argument("--skip-backfill", action="store_true", help="Only validate and report an already migrated batch.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Run the V1 to V2 migration and validation inside a rollback-only transaction. "
                "Reports are written, but V2 rows, exceptions, batch state, and activation markers are not persisted."
            ),
        )
        parser.add_argument("--activate-v2", action="store_true", help="Mark this batch active for v2 reads only after validation passes.")
        parser.add_argument(
            "--allow-open-exceptions",
            action="store_true",
            help="Allow activation even if MigrationExceptionV2 has open exceptions for this batch.",
        )
        parser.add_argument(
            "--ignore-open-exception-code",
            action="append",
            default=[],
            help=(
                "Treat this open MigrationExceptionV2 issue_code as non-blocking for validation. "
                "Can be passed multiple times. Ignored exceptions are still written to reports."
            ),
        )

    def handle(self, *args, **options):
        started = timezone.now()
        start_monotonic = monotonic()
        self.batch_id = clean_text(options["batch_id"]) or f"inclinic_v1_to_v2_{started:%Y%m%d%H%M%S}"
        self.default_alias = options["default_alias"]
        self.master_alias = options["master_alias"]
        self.campaign_id = clean_text(options["campaign_id"]) or TARGET_CAMPAIGN_ID
        self.campaign_id_norm = normalize_campaign_id(self.campaign_id)
        self.allow_open_exceptions = bool(options["allow_open_exceptions"])
        self.dry_run = bool(options["dry_run"])
        if self.dry_run and options["activate_v2"]:
            self.stdout.write(self.style.WARNING("[DRY RUN] Ignoring --activate-v2; dry runs never activate V2."))
            options["activate_v2"] = False
        self.ignored_open_exception_codes = {
            clean_text(code).upper()
            for code in options["ignore_open_exception_code"]
            if clean_text(code)
        }

        self.report_dir = self._report_dir(options["report_dir"])
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.success_csv_path = self.report_dir / "successful_transfers.csv"
        self.failure_csv_path = self.report_dir / "failed_transfers.csv"
        self.success_log_path = self.report_dir / "migration_success.log"
        self.failure_log_path = self.report_dir / "migration_failures.log"
        self.exceptions_csv_path = self.report_dir / "open_migration_exceptions.csv"
        self.reconciliation_csv_path = self.report_dir / "validation_reconciliation.csv"
        self.dry_run_counts_csv_path = self.report_dir / "dry_run_counts.csv"
        self.final_report_path = self.report_dir / "final_validation_report.txt"
        self.final_report_json_path = self.report_dir / "final_validation_report.json"

        self.stdout.write(f"[START] batch_id={self.batch_id}")
        self.stdout.write(f"[REPORT_DIR] {self.report_dir}")
        if self.dry_run:
            self.stdout.write("[DRY RUN] Database writes will be rolled back after validation/count reporting.")

        with self.success_log_path.open("w", encoding="utf-8") as success_log, self.failure_log_path.open(
            "w", encoding="utf-8"
        ) as failure_log:
            self._log(success_log, f"Migration started at {started.isoformat()}")
            self._log(success_log, f"batch_id={self.batch_id}")
            self._log(success_log, f"default_alias={self.default_alias} database={self._db_name(self.default_alias)}")
            self._log(success_log, f"master_alias={self.master_alias} database={self._db_name(self.master_alias)}")
            if self.dry_run:
                self._log(success_log, "Dry run enabled; default database writes will be rolled back.")

            try:
                dry_run_context = (
                    transaction.atomic(using=self.default_alias) if self.dry_run else nullcontext()
                )
                with dry_run_context:
                    self._validation_failed_intentionally = False
                    if not options["skip_backfill"]:
                        self._run_backfill(options, success_log)
                    else:
                        self._log(success_log, "Skipped backfill by request; running validation only.")

                    success_rows, failure_rows, recon_rows = self._validate_all(success_log, failure_log)
                    open_exception_count = MigrationExceptionV2.objects.filter(
                        migration_batch_id=self.batch_id,
                        system_name=SYSTEM_NAME,
                        resolution_status="open",
                    ).count()
                    blocking_open_exception_count = self._blocking_open_exception_count()
                    exception_rows = self._open_exception_rows()

                    validation_passed = not failure_rows and (
                        self.allow_open_exceptions or blocking_open_exception_count == 0
                    )
                    status = "PASS" if validation_passed else "FAIL"

                    dry_run_count_rows = self._dry_run_count_rows() if self.dry_run else []

                    self._write_csv(self.success_csv_path, SUCCESS_FIELDS, success_rows)
                    self._write_csv(self.failure_csv_path, FAILURE_FIELDS, failure_rows)
                    self._write_csv(self.exceptions_csv_path, EXCEPTION_FIELDS, exception_rows)
                    self._write_csv(self.reconciliation_csv_path, RECON_FIELDS, recon_rows)
                    if self.dry_run:
                        self._write_csv(self.dry_run_counts_csv_path, DRY_RUN_COUNT_FIELDS, dry_run_count_rows)

                    ended = timezone.now()
                    duration_seconds = round(monotonic() - start_monotonic, 3)
                    final_payload = {
                        "batch_id": self.batch_id,
                        "started_at": started.isoformat(),
                        "ended_at": ended.isoformat(),
                        "duration_seconds": duration_seconds,
                        "default_database": self._db_name(self.default_alias),
                        "master_database": self._db_name(self.master_alias),
                        "dry_run": self.dry_run,
                        "database_writes_persisted": not self.dry_run,
                        "total_success_rows": len(success_rows),
                        "total_failed_rows": len(failure_rows),
                        "open_migration_exceptions": open_exception_count,
                        "blocking_open_migration_exceptions": blocking_open_exception_count,
                        "ignored_open_exception_codes": sorted(self.ignored_open_exception_codes),
                        "validation_status": status,
                        "activated_v2": False,
                        "dry_run_counts": dry_run_count_rows,
                        "reports": {
                            "success_csv": str(self.success_csv_path),
                            "failure_csv": str(self.failure_csv_path),
                            "success_log": str(self.success_log_path),
                            "failure_log": str(self.failure_log_path),
                            "open_exceptions_csv": str(self.exceptions_csv_path),
                            "reconciliation_csv": str(self.reconciliation_csv_path),
                            "dry_run_counts_csv": str(self.dry_run_counts_csv_path) if self.dry_run else "",
                            "final_report_txt": str(self.final_report_path),
                            "final_report_json": str(self.final_report_json_path),
                        },
                    }

                    if validation_passed:
                        SourceMigrationBatchV2.objects.filter(migration_batch_id=self.batch_id).update(
                            completed_at=ended,
                            status="validated",
                        )
                        if options["activate_v2"]:
                            activate_v2_batch(self.batch_id)
                            final_payload["activated_v2"] = True
                            self._log(success_log, "V2 activation marker written successfully.")
                    else:
                        SourceMigrationBatchV2.objects.filter(migration_batch_id=self.batch_id).update(
                            completed_at=ended,
                            status="validation_failed",
                        )

                    self._write_final_report(final_payload, recon_rows)
                    self._log(success_log, f"Migration finished with validation_status={status}")

                    self.stdout.write(self.style.SUCCESS(f"[DONE] validation_status={status}"))
                    self.stdout.write(f"Success CSV: {self.success_csv_path}")
                    self.stdout.write(f"Failure CSV: {self.failure_csv_path}")
                    if self.dry_run:
                        self.stdout.write(f"Dry-run counts CSV: {self.dry_run_counts_csv_path}")
                    self.stdout.write(f"Validation report: {self.final_report_path}")

                    if self.dry_run:
                        transaction.set_rollback(True, using=self.default_alias)
                        self._log(success_log, "Dry run rollback requested; V2 rows and batch state were not persisted.")
                        self.stdout.write("[DRY RUN] Rolled back database writes. Reports were kept on disk.")
                    elif not validation_passed:
                        self._validation_failed_intentionally = True
                        raise CommandError(
                            "V1 to V2 migration validation failed. V2 was not activated. "
                            f"See {self.failure_csv_path} and {self.failure_log_path}."
                        )

            except CommandError:
                stack = traceback.format_exc()
                self._log(failure_log, "Migration command exited without activation.")
                self._log(failure_log, stack)
                if not getattr(self, "_validation_failed_intentionally", False):
                    SourceMigrationBatchV2.objects.filter(migration_batch_id=self.batch_id).update(
                        completed_at=timezone.now(),
                        status="failed",
                        notes="CommandError during migration execution.",
                    )
                raise
            except Exception as exc:
                stack = traceback.format_exc()
                self._log(failure_log, "Migration command failed.")
                self._log(failure_log, stack)
                SourceMigrationBatchV2.objects.filter(migration_batch_id=self.batch_id).update(
                    completed_at=timezone.now(),
                    status="failed",
                    notes=str(exc),
                )
                raise

    def _report_dir(self, explicit: str) -> Path:
        if explicit:
            return Path(explicit).expanduser().resolve()
        return (
            Path(settings.BASE_DIR)
            / "backend"
            / "reporting_etl"
            / "reports"
            / f"v1_to_v2_{self.batch_id}"
        )

    def _db_name(self, alias: str) -> str:
        return connections[alias].settings_dict.get("NAME") or alias

    def _log(self, handle, message: str) -> None:
        handle.write(f"[{timezone.now().isoformat()}] {message}\n")
        handle.flush()

    def _run_backfill(self, options: dict[str, Any], success_log) -> None:
        self.stdout.write("[BACKFILL] Starting v2 backfill engine...")
        backfill_stdout = io.StringIO()
        kwargs = {
            "batch_id": self.batch_id,
            "created_by": options["created_by"],
            "campaign_id": self.campaign_id,
            "default_alias": self.default_alias,
            "master_alias": self.master_alias,
            "skip_mismatch_csv": options["skip_mismatch_csv"],
            "stdout": backfill_stdout,
        }
        if options["mismatch_csv"]:
            kwargs["mismatch_csv"] = options["mismatch_csv"]

        call_command("backfill_inclinic_v2", **kwargs)
        output = backfill_stdout.getvalue()
        self._log(success_log, "Backfill command output:")
        self._log(success_log, output)
        self.stdout.write("[BACKFILL] Completed.")

    def _table_count(self, alias: str, table: str) -> int:
        if not table_exists(alias, table):
            return 0
        conn = connections[alias]
        qn = conn.ops.quote_name
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {qn(table)}")
            return int(cursor.fetchone()[0] or 0)

    def _dry_run_count_rows(self) -> list[dict[str, Any]]:
        master_fieldrep_table = getattr(settings, "MASTER_DB_FIELD_REP_TABLE", "campaign_fieldrep")
        rows: list[dict[str, Any]] = []

        field_rep_qs = InclinicFieldRepIdentityV2.objects.filter(
            migration_batch_id=self.batch_id,
            source_table=master_fieldrep_table,
        )
        field_rep_source_count = field_rep_qs.values("source_pk_value").distinct().count()
        field_rep_current_count = field_rep_qs.filter(is_current=True).values("source_pk_value").distinct().count()
        field_rep_excluded_count = field_rep_qs.filter(is_current=False).values("source_pk_value").distinct().count()
        field_rep_identity_rows = field_rep_qs.count()
        rows.append(
            {
                "entity": "field_reps",
                "v1_database": self._db_name(self.master_alias),
                "v1_table": master_fieldrep_table,
                "v1_count": self._table_count(self.master_alias, master_fieldrep_table),
                "v2_database": self._db_name(self.default_alias),
                "v2_table": "inclinic_field_rep_identity_v2",
                "v2_count_after_dry_run": field_rep_source_count,
                "v2_current_after_dry_run": field_rep_current_count,
                "v2_excluded_after_dry_run": field_rep_excluded_count,
                "note": f"V2 count is distinct migrated campaign_fieldrep source ids; identity_rows={field_rep_identity_rows}.",
            }
        )

        doctor_qs = InclinicDoctorV2.objects.filter(
            migration_batch_id=self.batch_id,
            source_table="doctor_viewer_doctor",
        )
        rows.append(
            {
                "entity": "doctors",
                "v1_database": self._db_name(self.default_alias),
                "v1_table": "doctor_viewer_doctor",
                "v1_count": self._table_count(self.default_alias, "doctor_viewer_doctor"),
                "v2_database": self._db_name(self.default_alias),
                "v2_table": "inclinic_doctor_v2",
                "v2_count_after_dry_run": doctor_qs.count(),
                "v2_current_after_dry_run": doctor_qs.filter(is_current=True).count(),
                "v2_excluded_after_dry_run": doctor_qs.filter(is_current=False).count(),
                "note": "V2 total preserves every V1 doctor row; current/excluded controls reporting use.",
            }
        )

        transaction_qs = InclinicCollateralTransactionV2.objects.filter(
            migration_batch_id=self.batch_id,
            source_table="sharing_management_collateraltransaction",
        )
        rows.append(
            {
                "entity": "transactions",
                "v1_database": self._db_name(self.default_alias),
                "v1_table": "sharing_management_collateraltransaction",
                "v1_count": self._table_count(self.default_alias, "sharing_management_collateraltransaction"),
                "v2_database": self._db_name(self.default_alias),
                "v2_table": "inclinic_collateral_transaction_v2",
                "v2_count_after_dry_run": transaction_qs.count(),
                "v2_current_after_dry_run": transaction_qs.filter(is_current=True).count(),
                "v2_excluded_after_dry_run": transaction_qs.filter(is_current=False).count(),
                "note": "V2 total preserves every V1 transaction row; current/excluded controls reporting use.",
            }
        )

        return rows

    def _source_specs(self) -> list[SourceValidationSpec]:
        master_fieldrep_table = getattr(settings, "MASTER_DB_FIELD_REP_TABLE", "campaign_fieldrep")
        master_assignment_table = getattr(settings, "MASTER_DB_CAMPAIGN_FIELD_REP_TABLE", "campaign_campaignfieldrep")
        master_auth_table = getattr(settings, "MASTER_AUTH_USER_TABLE", "auth_user")

        return [
            SourceValidationSpec(
                "master_field_reps",
                self.master_alias,
                master_fieldrep_table,
                InclinicFieldRepIdentityV2,
                "inclinic_field_rep_identity_v2",
                "inclinic_field_rep_identity_id",
                (("id", "campaign_fieldrep_id"), ("full_name", "campaign_fieldrep_full_name"), ("brand_supplied_field_rep_id", "brand_supplied_field_rep_id")),
            ),
            SourceValidationSpec(
                "local_users",
                self.default_alias,
                "user_management_user",
                InclinicFieldRepIdentityV2,
                "inclinic_field_rep_identity_v2",
                "inclinic_field_rep_identity_id",
                (("id", "user_management_user_id"), ("username", "user_management_username"), ("email", "user_management_email")),
            ),
            SourceValidationSpec(
                "master_auth_users",
                self.master_alias,
                master_auth_table,
                InclinicFieldRepIdentityV2,
                "inclinic_field_rep_identity_v2",
                "inclinic_field_rep_identity_id",
                (("id", "auth_user_id"), ("username", "auth_user_username"), ("email", "auth_user_email")),
            ),
            SourceValidationSpec(
                "master_campaign_field_rep_assignments",
                self.master_alias,
                master_assignment_table,
                InclinicCampaignFieldRepAssignmentV2,
                "inclinic_campaign_field_rep_assignment_v2",
                "assignment_uuid",
                (("id", "old_id"), ("field_rep_id", "old_field_rep_id"), ("campaign_id", "old_campaign_id")),
            ),
            SourceValidationSpec(
                "local_campaign_assignments_audit",
                self.default_alias,
                "campaign_management_campaignassignment",
                InclinicNonAuthoritativeAssignmentAuditV2,
                "inclinic_non_authoritative_assignment_audit_v2",
                "audit_uuid",
                (("id", "campaign_assignment_id"), ("campaign_id", "campaign_assignment_campaign_id"), ("field_rep_id", "campaign_assignment_field_rep_id")),
            ),
            SourceValidationSpec(
                "admin_fieldrep_campaigns_audit",
                self.default_alias,
                "admin_dashboard_fieldrepcampaign",
                InclinicNonAuthoritativeAssignmentAuditV2,
                "inclinic_non_authoritative_assignment_audit_v2",
                "audit_uuid",
                (("id", "admin_fieldrepcampaign_id"), ("campaign_id", "admin_fieldrepcampaign_campaign_id"), ("field_rep_id", "admin_fieldrepcampaign_field_rep_id")),
            ),
            SourceValidationSpec(
                "doctors",
                self.default_alias,
                "doctor_viewer_doctor",
                InclinicDoctorV2,
                "inclinic_doctor_v2",
                "inclinic_doctor_uuid",
                (("id", "old_id"), ("name", "old_name"), ("phone", "old_phone"), ("rep_id", "old_rep_id")),
            ),
            SourceValidationSpec(
                "share_logs",
                self.default_alias,
                "sharing_management_sharelog",
                InclinicShareEventV2,
                "inclinic_share_event_v2",
                "share_event_uuid",
                (("id", "old_id"), ("doctor_identifier", "old_doctor_identifier"), ("field_rep_id", "old_field_rep_id"), ("brand_campaign_id", "old_brand_campaign_id")),
            ),
            SourceValidationSpec(
                "collateral_transactions",
                self.default_alias,
                "sharing_management_collateraltransaction",
                InclinicCollateralTransactionV2,
                "inclinic_collateral_transaction_v2",
                "transaction_uuid",
                (("id", "old_id"), ("transaction_id", "old_transaction_id"), ("field_rep_id", "old_field_rep_id"), ("doctor_number", "old_doctor_number"), ("collateral_id", "old_collateral_id")),
            ),
            SourceValidationSpec(
                "collaterals",
                self.default_alias,
                "collateral_management_collateral",
                InclinicCollateralV2,
                "inclinic_collateral_v2",
                "collateral_uuid",
                (("id", "old_id"), ("title", "old_title"), ("type", "old_type"), ("campaign_id", "old_campaign_id")),
            ),
            SourceValidationSpec(
                "campaign_collaterals",
                self.default_alias,
                "collateral_management_campaigncollateral",
                InclinicCampaignCollateralV2,
                "inclinic_campaign_collateral_v2",
                "campaign_collateral_uuid",
                (("id", "old_id"), ("campaign_id", "old_campaign_id"), ("collateral_id", "old_collateral_id")),
            ),
        ]

    def _validate_all(self, success_log, failure_log) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        success_rows: list[dict[str, Any]] = []
        failure_rows: list[dict[str, Any]] = []
        recon_rows: list[dict[str, Any]] = []

        for spec in self._source_specs():
            self.stdout.write(f"[VALIDATE] {spec.source_table} -> {spec.destination_table}")
            self._log(success_log, f"Validating {spec.source_table} -> {spec.destination_table}")
            source_db = source_database(spec.alias)

            if not table_exists(spec.alias, spec.source_table):
                failure_rows.append(
                    self._failure_row(
                        source_db,
                        spec.source_table,
                        "",
                        spec.destination_table,
                        "SOURCE_TABLE_MISSING",
                        f"Required source table {spec.source_table} was not found in alias {spec.alias}.",
                    )
                )
                recon_rows.append(self._recon_row(spec, source_db, 0, 0, 1, 0, 0, "FAIL"))
                continue

            source_rows = fetch_rows(spec.alias, spec.source_table)
            source_by_pk = {clean_text(row.get("id")): row for row in source_rows if clean_text(row.get("id"))}
            destination_qs = spec.destination_model.objects.filter(
                migration_batch_id=self.batch_id,
                source_table=spec.source_table,
            )

            destination_by_source: dict[str, list[Any]] = {}
            for dest in destination_qs:
                destination_by_source.setdefault(clean_text(dest.source_pk_value), []).append(dest)

            missing = 0
            mismatches = 0
            migrated_sources = 0
            for source_pk, source_row in source_by_pk.items():
                destination_rows = destination_by_source.get(source_pk, [])
                if not destination_rows:
                    missing += 1
                    failure_rows.append(
                        self._failure_row(
                            source_db,
                            spec.source_table,
                            source_pk,
                            spec.destination_table,
                            "DESTINATION_RECORD_MISSING",
                            "No v2 destination row found for this source primary key.",
                        )
                    )
                    continue

                field_errors = self._validate_destination_rows(spec, source_row, destination_rows)
                if field_errors:
                    mismatches += 1
                    failure_rows.append(
                        self._failure_row(
                            source_db,
                            spec.source_table,
                            source_pk,
                            spec.destination_table,
                            "CRITICAL_FIELD_MISMATCH",
                            "; ".join(field_errors),
                        )
                    )
                    continue

                migrated_sources += 1
                success_rows.append(
                    {
                        "batch_id": self.batch_id,
                        "source_database": source_db,
                        "source_table": spec.source_table,
                        "source_pk_column": "id",
                        "source_pk_value": source_pk,
                        "destination_table": spec.destination_table,
                        "destination_pk_values": ",".join(
                            clean_text(getattr(row, spec.destination_pk_field)) for row in destination_rows
                        ),
                        "status": "migrated",
                        "validation_status": "matched",
                        "message": f"{len(destination_rows)} destination row(s) verified.",
                    }
                )

            status = "PASS" if missing == 0 and mismatches == 0 else "FAIL"
            recon_rows.append(
                self._recon_row(
                    spec,
                    source_db,
                    len(source_by_pk),
                    migrated_sources,
                    missing,
                    mismatches,
                    destination_qs.count(),
                    status,
                )
            )
            self._log(
                success_log if status == "PASS" else failure_log,
                f"{spec.source_table}: source={len(source_by_pk)} migrated={migrated_sources} missing={missing} mismatches={mismatches} status={status}",
            )

        return success_rows, failure_rows, recon_rows

    def _validate_destination_rows(self, spec: SourceValidationSpec, source_row: dict[str, Any], destination_rows: list[Any]) -> list[str]:
        errors: list[str] = []
        raw_payload_ok = False

        for dest in destination_rows:
            try:
                raw_payload = json.loads(dest.raw_payload_json or "{}")
            except json.JSONDecodeError:
                raw_payload = {}
            if clean_text(raw_payload.get("id")) == clean_text(source_row.get("id")):
                raw_payload_ok = True

        if not raw_payload_ok:
            errors.append("raw_payload_json does not contain the source row id")

        for source_field, dest_field in spec.critical_field_map:
            source_value = source_row.get(source_field)
            if any(_same_value(source_value, getattr(dest, dest_field, None)) for dest in destination_rows):
                continue
            errors.append(
                f"{source_field}->{dest_field} mismatch source={_as_text(source_value)!r} "
                f"dest={[ _as_text(getattr(dest, dest_field, None)) for dest in destination_rows ]!r}"
            )

        return errors

    def _failure_row(
        self,
        source_db: str,
        source_table: str,
        source_pk_value: Any,
        destination_table: str,
        failure_type: str,
        failure_reason: str,
        stack_trace: str = "",
    ) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "source_database": source_db,
            "source_table": source_table,
            "source_pk_column": "id",
            "source_pk_value": clean_text(source_pk_value),
            "destination_table": destination_table,
            "failure_type": failure_type,
            "failure_reason": failure_reason,
            "stack_trace": stack_trace,
        }

    def _recon_row(
        self,
        spec: SourceValidationSpec,
        source_db: str,
        total_source: int,
        migrated: int,
        missing: int,
        mismatches: int,
        destination_rows: int,
        status: str,
    ) -> dict[str, Any]:
        return {
            "source_table": spec.source_table,
            "destination_table": spec.destination_table,
            "source_database": source_db,
            "total_source_records": total_source,
            "total_migrated_source_records": migrated,
            "missing_records": missing,
            "field_mismatch_records": mismatches,
            "destination_rows": destination_rows,
            "validation_status": status,
        }

    def _write_csv(self, path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    def _open_exception_rows(self) -> list[dict[str, Any]]:
        return list(
            MigrationExceptionV2.objects.filter(
                migration_batch_id=self.batch_id,
                system_name=SYSTEM_NAME,
                resolution_status="open",
            )
            .order_by("issue_code", "source_table", "source_pk_value")
            .values(*EXCEPTION_FIELDS)
        )

    def _blocking_open_exception_count(self) -> int:
        queryset = MigrationExceptionV2.objects.filter(
            migration_batch_id=self.batch_id,
            system_name=SYSTEM_NAME,
            resolution_status="open",
        )
        if self.ignored_open_exception_codes:
            queryset = queryset.exclude(issue_code__in=self.ignored_open_exception_codes)
        return queryset.count()

    def _write_final_report(self, payload: dict[str, Any], recon_rows: list[dict[str, Any]]) -> None:
        payload["reconciliation"] = recon_rows
        self.final_report_json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

        lines = [
            "InClinic V1 to V2 Migration Validation Report",
            "=" * 52,
            f"Batch ID: {payload['batch_id']}",
            f"Started: {payload['started_at']}",
            f"Ended: {payload['ended_at']}",
            f"Duration seconds: {payload['duration_seconds']}",
            f"Default DB: {payload['default_database']}",
            f"Master DB: {payload['master_database']}",
            f"Dry run: {payload.get('dry_run', False)}",
            f"Database writes persisted: {payload.get('database_writes_persisted', True)}",
            f"Successful source records: {payload['total_success_rows']}",
            f"Failed source records: {payload['total_failed_rows']}",
            f"Open migration exceptions: {payload['open_migration_exceptions']}",
            f"Blocking open migration exceptions: {payload['blocking_open_migration_exceptions']}",
            f"Ignored open exception codes: {', '.join(payload['ignored_open_exception_codes']) or 'None'}",
            f"Validation status: {payload['validation_status']}",
            f"Activated V2: {payload['activated_v2']}",
            "",
            "Record Count Reconciliation",
            "-" * 52,
        ]
        for row in recon_rows:
            lines.append(
                f"{row['source_table']} -> {row['destination_table']}: "
                f"source={row['total_source_records']} migrated={row['total_migrated_source_records']} "
                f"missing={row['missing_records']} mismatches={row['field_mismatch_records']} "
                f"destination_rows={row['destination_rows']} status={row['validation_status']}"
            )
        dry_run_counts = payload.get("dry_run_counts") or []
        if dry_run_counts:
            lines.extend(["", "Dry Run Counts", "-" * 52])
            for row in dry_run_counts:
                lines.append(
                    f"{row['entity']}: "
                    f"V1 {row['v1_database']}.{row['v1_table']}={row['v1_count']} | "
                    f"V2 {row['v2_database']}.{row['v2_table']}={row['v2_count_after_dry_run']} "
                    f"(current={row['v2_current_after_dry_run']}, excluded={row['v2_excluded_after_dry_run']})"
                )
                if row.get("note"):
                    lines.append(f"  Note: {row['note']}")
        self.final_report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
