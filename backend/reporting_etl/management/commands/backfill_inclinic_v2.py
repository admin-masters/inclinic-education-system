from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from reporting_etl.inclinic_v2 import (
    DUPLICATE_ASM_DOCTOR_OVERRIDES,
    FIELD_REP_CONFLICT_TRANSACTION_EXCLUSION_CAMPAIGN_IDS,
    LEGACY_DOCTOR_REP_ALIASES,
    SYSTEM_NAME,
    TARGET_CAMPAIGN_ID,
    WRONG_DOCTOR_NUMBER_EXCLUSIONS_BY_RAW_DIGITS,
    clean_text,
    common_fields,
    fetch_rows,
    first_by,
    group_by,
    load_source_csv,
    normalize_campaign_id,
    normalize_email,
    normalize_name,
    normalize_phone,
    parse_bool,
    parse_int,
    parse_mismatch_csv,
    source_database,
    stable_uuid,
    to_json,
    update_by_pk,
)
from reporting_etl.models import (
    InclinicAssignedDoctorRosterV2,
    InclinicCampaignCollateralV2,
    InclinicCampaignFieldRepAssignmentV2,
    InclinicCollateralTransactionV2,
    InclinicCollateralV2,
    InclinicDoctorActivityEventV2,
    InclinicDoctorV2,
    InclinicFieldRepIdentityV2,
    InclinicLegacyDoctorRepAliasV2,
    InclinicManualRepDoctorCorrectionStagingV2,
    InclinicNonAuthoritativeAssignmentAuditV2,
    InclinicShareEventV2,
    MigrationExceptionV2,
    SourceMigrationBatchV2,
)


DEFAULT_MISMATCH_CSV = "/Users/inditech-tech/Desktop/raw_server1.campaign_campaignfieldrep (1) - mismatch data.csv"


class Command(BaseCommand):
    help = "Backfill InClinic source-system v2 lineage tables without mutating legacy source rows."

    def add_arguments(self, parser):
        parser.add_argument("--batch-id", default="")
        parser.add_argument("--created-by", default="codex")
        parser.add_argument("--campaign-id", default=TARGET_CAMPAIGN_ID)
        parser.add_argument("--mismatch-csv", default=DEFAULT_MISMATCH_CSV)
        parser.add_argument("--default-alias", default="default")
        parser.add_argument("--master-alias", default=getattr(settings, "MASTER_DB_ALIAS", "master"))
        parser.add_argument("--skip-mismatch-csv", action="store_true")
        parser.add_argument("--fieldrep-csv", default="")
        parser.add_argument("--campaign-fieldrep-csv", default="")
        parser.add_argument("--doctor-csv", default="")
        parser.add_argument("--collateral-transaction-csv", default="")

    def handle(self, *args, **options):
        warnings.filterwarnings(
            "ignore",
            message=r"DateTimeField .* received a naive datetime.*",
            category=RuntimeWarning,
        )
        self.default_alias = options["default_alias"]
        self.master_alias = options["master_alias"]
        self.campaign_id = clean_text(options["campaign_id"]) or TARGET_CAMPAIGN_ID
        self.campaign_id_norm = normalize_campaign_id(self.campaign_id)
        self.batch_id = clean_text(options["batch_id"]) or f"inclinic_v2_{timezone.now():%Y%m%d%H%M%S}"
        self.counts: dict[str, int] = {}

        input_files = []
        if not options["skip_mismatch_csv"]:
            input_files.append(options["mismatch_csv"])
        for option_name in ("fieldrep_csv", "campaign_fieldrep_csv", "doctor_csv", "collateral_transaction_csv"):
            if options[option_name]:
                input_files.append(options[option_name])

        self.source_csv_paths = {
            "field_reps": options["fieldrep_csv"],
            "master_assignments": options["campaign_fieldrep_csv"],
            "doctors": options["doctor_csv"],
            "transactions": options["collateral_transaction_csv"],
        }

        SourceMigrationBatchV2.objects.update_or_create(
            migration_batch_id=self.batch_id,
            defaults={
                "system_name": SYSTEM_NAME,
                "database_name": source_database(self.default_alias),
                "started_at": timezone.now(),
                "completed_at": None,
                "status": "running",
                "input_file_names": to_json(input_files),
                "created_by": options["created_by"],
                "notes": "InClinic v2 source-system lineage backfill",
            },
        )

        with transaction.atomic():
            self.load_sources()
            self.backfill_field_rep_identity()
            self.backfill_campaign_assignments()
            self.backfill_non_authoritative_assignment_audit()
            self.load_legacy_alias_bridge()
            self.backfill_doctors()
            self.backfill_collaterals()
            self.backfill_campaign_collaterals()
            self.backfill_share_events()
            self.backfill_collateral_transactions()
            if not options["skip_mismatch_csv"]:
                self.parse_and_backfill_assigned_roster(Path(options["mismatch_csv"]))
            self.backfill_activity_events()

            SourceMigrationBatchV2.objects.filter(migration_batch_id=self.batch_id).update(
                completed_at=timezone.now(),
                status="completed",
            )

        self.stdout.write(self.style.SUCCESS("InClinic v2 backfill completed."))
        for key in sorted(self.counts):
            self.stdout.write(f"{key}: {self.counts[key]}")

    def inc(self, key: str, amount: int = 1):
        self.counts[key] = self.counts.get(key, 0) + amount

    def load_sources(self):
        self.master_fieldrep_table = getattr(settings, "MASTER_DB_FIELD_REP_TABLE", "campaign_fieldrep")
        self.master_assignment_table = getattr(settings, "MASTER_DB_CAMPAIGN_FIELD_REP_TABLE", "campaign_campaignfieldrep")
        self.master_auth_table = getattr(settings, "MASTER_AUTH_USER_TABLE", "auth_user")
        self.master_campaign_table = getattr(settings, "MASTER_CAMPAIGN_DB_TABLE", "campaign_campaign")

        self.field_reps = fetch_rows(self.master_alias, self.master_fieldrep_table)
        self.master_assignments = fetch_rows(self.master_alias, self.master_assignment_table)
        self.master_auth_users = fetch_rows(self.master_alias, self.master_auth_table)
        self.master_campaigns = fetch_rows(self.master_alias, self.master_campaign_table)

        self.local_users = fetch_rows(self.default_alias, "user_management_user")
        self.local_campaigns = fetch_rows(self.default_alias, "campaign_management_campaign")
        self.doctors = fetch_rows(self.default_alias, "doctor_viewer_doctor")
        self.share_logs = fetch_rows(self.default_alias, "sharing_management_sharelog")
        self.transactions = fetch_rows(self.default_alias, "sharing_management_collateraltransaction")
        self.collaterals = fetch_rows(self.default_alias, "collateral_management_collateral")
        self.campaign_collaterals = fetch_rows(self.default_alias, "collateral_management_campaigncollateral")
        self.campaign_assignments = fetch_rows(self.default_alias, "campaign_management_campaignassignment")
        self.admin_fieldrep_campaigns = fetch_rows(self.default_alias, "admin_dashboard_fieldrepcampaign")

        csv_field_reps = load_source_csv(self.source_csv_paths["field_reps"]) if self.source_csv_paths["field_reps"] else []
        csv_assignments = load_source_csv(self.source_csv_paths["master_assignments"]) if self.source_csv_paths["master_assignments"] else []
        csv_doctors = load_source_csv(self.source_csv_paths["doctors"]) if self.source_csv_paths["doctors"] else []
        csv_transactions = load_source_csv(self.source_csv_paths["transactions"]) if self.source_csv_paths["transactions"] else []

        if csv_field_reps:
            self.field_reps = csv_field_reps
            self.inc("source_overlay.field_reps")
        if csv_assignments:
            self.master_assignments = csv_assignments
            self.inc("source_overlay.master_assignments")
        if csv_doctors:
            self.doctors = csv_doctors
            self.inc("source_overlay.doctors")
        if csv_transactions:
            self.transactions = csv_transactions
            self.inc("source_overlay.transactions")

        self.fr_by_id = first_by(self.field_reps, "id")
        self.fr_by_brand = first_by(self.field_reps, "brand_supplied_field_rep_id")
        self.auth_by_id = first_by(self.master_auth_users, "id")
        self.auth_by_email = {normalize_email(row.get("email")): row for row in self.master_auth_users if normalize_email(row.get("email"))}
        self.fr_by_user_id = first_by(self.field_reps, "user_id")
        self.fr_by_auth_email = {}
        for fr in self.field_reps:
            auth = self.auth_by_id.get(clean_text(fr.get("user_id")))
            if auth and normalize_email(auth.get("email")):
                self.fr_by_auth_email[normalize_email(auth.get("email"))] = fr

        self.local_user_by_id = first_by(self.local_users, "id")
        self.local_campaign_by_id = first_by(self.local_campaigns, "id")
        self.doctor_resolution_rows = [
            dict(row, phone_normalized=normalize_phone(row.get("phone")))
            for row in self.doctors
            if not self.doctor_row_exclusion_reason(row)
        ]
        self.doctors_by_phone = group_by(self.doctor_resolution_rows, "phone_normalized")
        self.authoritative_pairs = {
            (normalize_campaign_id(row.get("campaign_id")), clean_text(row.get("field_rep_id")))
            for row in self.master_assignments
        }

    def raw_digits(self, value: Any) -> str:
        return re.sub(r"\D+", "", clean_text(value))

    def wrong_doctor_number_exclusion(self, phone: Any) -> dict[str, Any] | None:
        return WRONG_DOCTOR_NUMBER_EXCLUSIONS_BY_RAW_DIGITS.get(self.raw_digits(phone))

    def duplicate_asm_override(self, phone: Any) -> dict[str, Any] | None:
        return DUPLICATE_ASM_DOCTOR_OVERRIDES.get(normalize_phone(phone))

    def doctor_row_exclusion_reason(self, row: dict[str, Any]) -> str:
        wrong_number = self.wrong_doctor_number_exclusion(row.get("phone"))
        if wrong_number:
            return "manual_wrong_doctor_number_exclusion"

        override = self.duplicate_asm_override(row.get("phone"))
        if override and clean_text(row.get("id")) != clean_text(override.get("preferred_doctor_viewer_doctor_id")):
            return "manual_duplicate_asm_unexpected_doctor_row_exclusion"

        return ""

    def field_rep_conflict_transaction_exclusion_reason(
        self,
        row: dict[str, Any],
        consistency_status: str,
    ) -> str:
        if consistency_status != "conflict":
            return ""

        campaign_id_norm = normalize_campaign_id(row.get("brand_campaign_id"))
        if campaign_id_norm in FIELD_REP_CONFLICT_TRANSACTION_EXCLUSION_CAMPAIGN_IDS:
            return "manual_target_campaign_field_rep_conflict_transaction_exclusion"

        return ""

    def source_common(self, alias: str, table: str, row: dict[str, Any], basis: str, status: str = "verified"):
        return common_fields(
            alias=alias,
            table=table,
            row=row,
            batch_id=self.batch_id,
            verification_status=status,
            verification_basis=basis,
        )

    def field_rep_uuid(self, campaign_fieldrep_id: Any) -> str:
        return stable_uuid("field_rep", clean_text(campaign_fieldrep_id))

    def campaign_uuid(self, campaign_id: Any) -> str:
        return stable_uuid("campaign", normalize_campaign_id(campaign_id))

    def doctor_uuid(self, phone: Any) -> str | None:
        phone_norm = normalize_phone(phone)
        return stable_uuid("doctor", phone_norm) if phone_norm else None

    def collateral_uuid(self, collateral_id: Any) -> str | None:
        value = clean_text(collateral_id)
        return stable_uuid("collateral", value) if value else None

    def record_exception(self, *, database_alias: str, source_table: str, source_pk_value: Any, entity_type: str, issue_code: str, details: Any, raw_payload: Any, source_pk_column: str = "id"):
        MigrationExceptionV2.objects.create(
            migration_batch_id=self.batch_id,
            system_name=SYSTEM_NAME,
            database_name=source_database(database_alias),
            source_table=source_table,
            source_pk_column=source_pk_column,
            source_pk_value=clean_text(source_pk_value),
            entity_type=entity_type,
            issue_code=issue_code,
            issue_details=to_json(details),
            raw_payload_json=to_json(raw_payload),
            resolution_status="open",
        )
        self.inc(f"exceptions.{issue_code}")

    def field_rep_identity_defaults(self, fr: dict[str, Any]) -> dict[str, Any]:
        return {
            "field_rep_uuid": self.field_rep_uuid(fr.get("id")),
            "campaign_fieldrep_id": clean_text(fr.get("id")),
            "brand_supplied_field_rep_id": clean_text(fr.get("brand_supplied_field_rep_id")),
            "campaign_fieldrep_full_name": clean_text(fr.get("full_name")),
            "campaign_fieldrep_phone_number": clean_text(fr.get("phone_number")),
            "campaign_fieldrep_is_active": parse_bool(fr.get("is_active")),
            "campaign_fieldrep_password_hash": clean_text(fr.get("password_hash")),
            "campaign_fieldrep_created_at": fr.get("created_at"),
            "campaign_fieldrep_updated_at": fr.get("updated_at"),
            "campaign_fieldrep_brand_id": clean_text(fr.get("brand_id")),
            "campaign_fieldrep_user_id": clean_text(fr.get("user_id")),
            "campaign_fieldrep_state": clean_text(fr.get("state")),
        }

    def backfill_field_rep_identity(self):
        for fr in self.field_reps:
            base = {
                **self.source_common(self.master_alias, self.master_fieldrep_table, fr, "campaign_fieldrep"),
                **self.field_rep_identity_defaults(fr),
                "phone_normalized": normalize_phone(fr.get("phone_number")) or None,
            }
            for source_column, value in (
                ("id", fr.get("id")),
                ("brand_supplied_field_rep_id", fr.get("brand_supplied_field_rep_id")),
                ("user_id", fr.get("user_id")),
            ):
                value = clean_text(value)
                if not value:
                    continue
                pk = stable_uuid("field_rep_identity", self.master_fieldrep_table, source_column, value)
                defaults = {
                    **base,
                    "source_column": source_column,
                    "source_value": value,
                    "source_value_normalized": value.lower(),
                    "match_basis": "campaign_fieldrep",
                }
                update_by_pk(InclinicFieldRepIdentityV2, pk, defaults)
                self.inc("field_rep_identity.rows")

        for user in self.local_users:
            resolved_fr = None
            field_id = clean_text(user.get("field_id"))
            email = normalize_email(user.get("email"))
            if field_id:
                resolved_fr = self.fr_by_brand.get(field_id)
            if not resolved_fr and email:
                resolved_fr = self.fr_by_auth_email.get(email)
            base = {
                **self.source_common(self.default_alias, "user_management_user", user, "user_management_user", "resolved" if resolved_fr else "unresolved"),
                "user_management_user_id": clean_text(user.get("id")),
                "user_management_username": clean_text(user.get("username")),
                "user_management_first_name": clean_text(user.get("first_name")),
                "user_management_last_name": clean_text(user.get("last_name")),
                "user_management_email": clean_text(user.get("email")),
                "user_management_role": clean_text(user.get("role")),
                "user_management_field_id": field_id,
                "user_management_phone_number": clean_text(user.get("phone_number")),
                "user_management_active": parse_bool(user.get("active")),
                "user_management_is_active": parse_bool(user.get("is_active")),
                "user_management_date_joined": user.get("date_joined"),
                "email_normalized": email or None,
                "phone_normalized": normalize_phone(user.get("phone_number")) or None,
            }
            if resolved_fr:
                base.update(self.field_rep_identity_defaults(resolved_fr))
            for source_column, value in (("id", user.get("id")), ("field_id", field_id), ("email", email)):
                value = clean_text(value)
                if not value:
                    continue
                pk = stable_uuid("field_rep_identity", "user_management_user", source_column, value)
                update_by_pk(
                    InclinicFieldRepIdentityV2,
                    pk,
                    {
                        **base,
                        "source_column": source_column,
                        "source_value": value,
                        "source_value_normalized": normalize_email(value) if source_column == "email" else value.lower(),
                        "match_basis": "user_management_user_to_campaign_fieldrep" if resolved_fr else "user_management_user_unresolved",
                    },
                )
                self.inc("field_rep_identity.rows")

        for auth in self.master_auth_users:
            resolved_fr = self.fr_by_user_id.get(clean_text(auth.get("id")))
            base = {
                **self.source_common(self.master_alias, self.master_auth_table, auth, "auth_user", "resolved" if resolved_fr else "unresolved"),
                "auth_user_id": clean_text(auth.get("id")),
                "auth_user_username": clean_text(auth.get("username")),
                "auth_user_first_name": clean_text(auth.get("first_name")),
                "auth_user_last_name": clean_text(auth.get("last_name")),
                "auth_user_email": clean_text(auth.get("email")),
                "auth_user_is_active": parse_bool(auth.get("is_active")),
                "auth_user_date_joined": auth.get("date_joined"),
                "email_normalized": normalize_email(auth.get("email")) or None,
            }
            if resolved_fr:
                base.update(self.field_rep_identity_defaults(resolved_fr))
            for source_column, value in (("id", auth.get("id")), ("email", auth.get("email"))):
                value = clean_text(value)
                if not value:
                    continue
                pk = stable_uuid("field_rep_identity", self.master_auth_table, source_column, value)
                update_by_pk(
                    InclinicFieldRepIdentityV2,
                    pk,
                    {
                        **base,
                        "source_column": source_column,
                        "source_value": value,
                        "source_value_normalized": normalize_email(value) if source_column == "email" else value.lower(),
                        "match_basis": "auth_user_to_campaign_fieldrep" if resolved_fr else "auth_user_unresolved",
                    },
                )
                self.inc("field_rep_identity.rows")

    def backfill_campaign_assignments(self):
        for row in self.master_assignments:
            field_rep_id = clean_text(row.get("field_rep_id"))
            campaign_id = clean_text(row.get("campaign_id"))
            fr = self.fr_by_id.get(field_rep_id)
            if not fr:
                self.record_exception(
                    database_alias=self.master_alias,
                    source_table=self.master_assignment_table,
                    source_pk_value=row.get("id"),
                    entity_type="field_rep_assignment",
                    issue_code="ASSIGNMENT_FIELD_REP_NOT_FOUND",
                    details={"field_rep_id": field_rep_id, "campaign_id": campaign_id},
                    raw_payload=row,
                )
            pk = stable_uuid("campaign_field_rep_assignment", row.get("id") or campaign_id, field_rep_id)
            update_by_pk(
                InclinicCampaignFieldRepAssignmentV2,
                pk,
                {
                    **self.source_common(self.master_alias, self.master_assignment_table, row, "campaign_campaignfieldrep"),
                    "campaign_uuid": self.campaign_uuid(campaign_id),
                    "legacy_campaign_id": campaign_id,
                    "legacy_campaign_id_normalized": normalize_campaign_id(campaign_id),
                    "field_rep_uuid": self.field_rep_uuid(field_rep_id),
                    "campaign_fieldrep_id": field_rep_id,
                    "brand_supplied_field_rep_id": clean_text(fr.get("brand_supplied_field_rep_id")) if fr else "",
                    "assigned_at": row.get("created_at"),
                    "assigned_from": row.get("created_at"),
                    "assigned_to": None,
                    "assignment_status": "active",
                    "is_authoritative": True,
                    "old_state": clean_text(row.get("state")),
                    "old_id": clean_text(row.get("id")),
                    "old_field_rep_id": field_rep_id,
                    "old_created_at": row.get("created_at"),
                    "old_campaign_id": campaign_id,
                },
            )
            self.inc("campaign_assignment_v2.rows")

    def backfill_non_authoritative_assignment_audit(self):
        for row in self.campaign_assignments:
            local_campaign = self.local_campaign_by_id.get(clean_text(row.get("campaign_id")))
            campaign_id = clean_text(local_campaign.get("brand_campaign_id")) if local_campaign else clean_text(row.get("campaign_id"))
            local_user = self.local_user_by_id.get(clean_text(row.get("field_rep_id")))
            fr = None
            if local_user:
                fr = self.fr_by_brand.get(clean_text(local_user.get("field_id"))) or self.fr_by_auth_email.get(normalize_email(local_user.get("email")))
            field_rep_id = clean_text(fr.get("id")) if fr else ""
            pk = stable_uuid("non_authoritative_assignment", "campaign_management_campaignassignment", row.get("id"))
            update_by_pk(
                InclinicNonAuthoritativeAssignmentAuditV2,
                pk,
                {
                    **self.source_common(self.default_alias, "campaign_management_campaignassignment", row, "non_authoritative_assignment_audit", "audit_only"),
                    "resolved_campaign_uuid": self.campaign_uuid(campaign_id) if campaign_id else None,
                    "resolved_field_rep_uuid": self.field_rep_uuid(field_rep_id) if field_rep_id else None,
                    "matches_authoritative_campaign_campaignfieldrep": (normalize_campaign_id(campaign_id), field_rep_id) in self.authoritative_pairs,
                    "campaign_assignment_id": clean_text(row.get("id")),
                    "campaign_assignment_assigned_on": row.get("assigned_on"),
                    "campaign_assignment_campaign_id": clean_text(row.get("campaign_id")),
                    "campaign_assignment_field_rep_id": clean_text(row.get("field_rep_id")),
                },
            )
            self.inc("non_authoritative_assignment_audit.rows")

        for row in self.admin_fieldrep_campaigns:
            local_campaign = self.local_campaign_by_id.get(clean_text(row.get("campaign_id")))
            campaign_id = clean_text(local_campaign.get("brand_campaign_id")) if local_campaign else clean_text(row.get("campaign_id"))
            local_user = self.local_user_by_id.get(clean_text(row.get("field_rep_id")))
            fr = None
            if local_user:
                fr = self.fr_by_brand.get(clean_text(local_user.get("field_id"))) or self.fr_by_auth_email.get(normalize_email(local_user.get("email")))
            field_rep_id = clean_text(fr.get("id")) if fr else ""
            pk = stable_uuid("non_authoritative_assignment", "admin_dashboard_fieldrepcampaign", row.get("id"))
            update_by_pk(
                InclinicNonAuthoritativeAssignmentAuditV2,
                pk,
                {
                    **self.source_common(self.default_alias, "admin_dashboard_fieldrepcampaign", row, "non_authoritative_assignment_audit", "audit_only"),
                    "resolved_campaign_uuid": self.campaign_uuid(campaign_id) if campaign_id else None,
                    "resolved_field_rep_uuid": self.field_rep_uuid(field_rep_id) if field_rep_id else None,
                    "matches_authoritative_campaign_campaignfieldrep": (normalize_campaign_id(campaign_id), field_rep_id) in self.authoritative_pairs,
                    "admin_fieldrepcampaign_id": clean_text(row.get("id")),
                    "admin_fieldrepcampaign_assigned_at": row.get("assigned_at"),
                    "admin_fieldrepcampaign_campaign_id": clean_text(row.get("campaign_id")),
                    "admin_fieldrepcampaign_field_rep_id": clean_text(row.get("field_rep_id")),
                    "admin_fieldrepcampaign_uid": clean_text(row.get("uid")),
                },
            )
            self.inc("non_authoritative_assignment_audit.rows")

    def load_legacy_alias_bridge(self):
        row_stub = {"id": "InclinicMapping1/InclinicMapping2", "created_at": timezone.now()}
        for brand_id, rep_name, campaign_fieldrep_id, legacy_rep_id in LEGACY_DOCTOR_REP_ALIASES:
            pk = stable_uuid("legacy_doctor_rep_alias", self.campaign_id_norm, brand_id, campaign_fieldrep_id, legacy_rep_id)
            update_by_pk(
                InclinicLegacyDoctorRepAliasV2,
                pk,
                {
                    **self.source_common(self.default_alias, "doctor_viewer_doctor", row_stub, "development_confirmed_exception_bridge", "development_confirmed"),
                    "source_pk_value": f"{brand_id}:{campaign_fieldrep_id}:{legacy_rep_id}",
                    "campaign_uuid": self.campaign_uuid(self.campaign_id),
                    "legacy_campaign_id": self.campaign_id,
                    "brand_supplied_field_rep_id": brand_id,
                    "field_rep_name": rep_name,
                    "campaign_fieldrep_id": campaign_fieldrep_id,
                    "field_rep_uuid": self.field_rep_uuid(campaign_fieldrep_id),
                    "legacy_table": "doctor_viewer_doctor",
                    "legacy_column": "rep_id",
                    "legacy_value": legacy_rep_id,
                    "usage_scope": "assigned_doctor_denominator_only",
                    "mapping_source": "InclinicMapping1/InclinicMapping2",
                },
            )
            self.inc("legacy_alias.rows")

    def backfill_doctors(self):
        aliases_by_legacy = group_by(
            [
                {
                    "legacy_value": legacy,
                    "legacy_alias_uuid": stable_uuid("legacy_doctor_rep_alias", self.campaign_id_norm, brand, cfr_id, legacy),
                }
                for brand, _name, cfr_id, legacy in LEGACY_DOCTOR_REP_ALIASES
            ],
            "legacy_value",
        )
        for row in self.doctors:
            phone_norm = normalize_phone(row.get("phone"))
            legacy_rep_id = clean_text(row.get("rep_id"))
            alias = aliases_by_legacy.get(legacy_rep_id, [None])[0]
            exclusion_reason = self.doctor_row_exclusion_reason(row)
            pk = stable_uuid("inclinic_doctor", row.get("id"))
            update_by_pk(
                InclinicDoctorV2,
                pk,
                {
                    **self.source_common(
                        self.default_alias,
                        "doctor_viewer_doctor",
                        row,
                        exclusion_reason or "doctor_viewer_doctor",
                        "excluded" if exclusion_reason else "verified",
                    ),
                    "is_current": not bool(exclusion_reason),
                    "doctor_uuid": self.doctor_uuid(phone_norm),
                    "display_name": clean_text(row.get("name")),
                    "name_normalized": normalize_name(row.get("name")),
                    "phone_raw": clean_text(row.get("phone")),
                    "phone_normalized": phone_norm,
                    "legacy_doctor_viewer_rep_id": legacy_rep_id,
                    "legacy_rep_alias_uuid": alias.get("legacy_alias_uuid") if alias else None,
                    "legacy_rep_alias_matched": bool(alias),
                    "old_id": clean_text(row.get("id")),
                    "old_name": clean_text(row.get("name")),
                    "old_phone": clean_text(row.get("phone")),
                    "old_rep_id": legacy_rep_id,
                    "old_source": clean_text(row.get("source")),
                },
            )
            self.inc("doctor_v2.rows")

    def backfill_collaterals(self):
        for row in self.collaterals:
            campaign_id = ""
            local_campaign = self.local_campaign_by_id.get(clean_text(row.get("campaign_id")))
            if local_campaign:
                campaign_id = clean_text(local_campaign.get("brand_campaign_id"))
            pk = stable_uuid("collateral", row.get("id"))
            update_by_pk(
                InclinicCollateralV2,
                pk,
                {
                    **self.source_common(self.default_alias, "collateral_management_collateral", row, "collateral_management_collateral"),
                    "campaign_uuid": self.campaign_uuid(campaign_id) if campaign_id else None,
                    "content_type_normalized": clean_text(row.get("type")).lower() or None,
                    "status": "active" if parse_bool(row.get("is_active")) else "inactive",
                    "old_id": clean_text(row.get("id")),
                    "old_type": clean_text(row.get("type")),
                    "old_title": clean_text(row.get("title")),
                    "old_file": clean_text(row.get("file")),
                    "old_vimeo_url": clean_text(row.get("vimeo_url")),
                    "old_content_id": clean_text(row.get("content_id")),
                    "old_upload_date": row.get("upload_date"),
                    "old_is_active": parse_bool(row.get("is_active")),
                    "old_created_at": row.get("created_at"),
                    "old_updated_at": row.get("updated_at"),
                    "old_banner_1": clean_text(row.get("banner_1")),
                    "old_banner_2": clean_text(row.get("banner_2")),
                    "old_campaign_id": clean_text(row.get("campaign_id")),
                    "old_created_by_id": clean_text(row.get("created_by_id")),
                    "old_description": clean_text(row.get("description")),
                    "old_purpose": clean_text(row.get("purpose")),
                    "old_doctor_name": clean_text(row.get("doctor_name")),
                    "old_webinar_date": row.get("webinar_date"),
                    "old_webinar_description": clean_text(row.get("webinar_description")),
                    "old_webinar_title": clean_text(row.get("webinar_title")),
                    "old_webinar_url": clean_text(row.get("webinar_url")),
                },
            )
            self.inc("collateral_v2.rows")

    def backfill_campaign_collaterals(self):
        for row in self.campaign_collaterals:
            local_campaign = self.local_campaign_by_id.get(clean_text(row.get("campaign_id")))
            campaign_id = clean_text(local_campaign.get("brand_campaign_id")) if local_campaign else clean_text(row.get("campaign_id"))
            pk = stable_uuid("campaign_collateral", row.get("id"))
            update_by_pk(
                InclinicCampaignCollateralV2,
                pk,
                {
                    **self.source_common(self.default_alias, "collateral_management_campaigncollateral", row, "campaign_collateral"),
                    "campaign_uuid": self.campaign_uuid(campaign_id) if campaign_id else None,
                    "collateral_uuid": self.collateral_uuid(row.get("collateral_id")) or "",
                    "old_id": clean_text(row.get("id")),
                    "old_start_date": row.get("start_date"),
                    "old_end_date": row.get("end_date"),
                    "old_created_at": row.get("created_at"),
                    "old_updated_at": row.get("updated_at"),
                    "old_campaign_id": clean_text(row.get("campaign_id")),
                    "old_collateral_id": clean_text(row.get("collateral_id")),
                },
            )
            self.inc("campaign_collateral_v2.rows")

    def resolve_doctor_from_phone(self, phone: Any) -> tuple[str | None, str | None, list[dict[str, Any]]]:
        phone_norm = normalize_phone(phone)
        candidates = self.doctors_by_phone.get(phone_norm, [])
        if len(candidates) == 1:
            return stable_uuid("doctor", phone_norm), stable_uuid("inclinic_doctor", candidates[0].get("id")), candidates
        return (stable_uuid("doctor", phone_norm) if phone_norm else None), None, candidates

    def backfill_share_events(self):
        for row in self.share_logs:
            field_rep_id = clean_text(row.get("field_rep_id"))
            fr = self.fr_by_id.get(field_rep_id)
            exclusion = self.wrong_doctor_number_exclusion(row.get("doctor_identifier"))
            if exclusion:
                doctor_uuid, inclinic_doctor_uuid, candidates = None, None, []
            else:
                doctor_uuid, inclinic_doctor_uuid, candidates = self.resolve_doctor_from_phone(row.get("doctor_identifier"))

            if not exclusion and len(candidates) > 1:
                self.record_exception(
                    database_alias=self.default_alias,
                    source_table="sharing_management_sharelog",
                    source_pk_value=row.get("id"),
                    entity_type="share_event",
                    issue_code="SHARE_DOCTOR_PHONE_AMBIGUOUS",
                    details={"doctor_identifier": row.get("doctor_identifier"), "candidate_count": len(candidates)},
                    raw_payload=row,
                )
            field_rep_email = normalize_email(row.get("field_rep_email"))
            auth = self.auth_by_id.get(clean_text(fr.get("user_id"))) if fr else None
            email_matches = None
            if field_rep_email and auth:
                email_matches = field_rep_email == normalize_email(auth.get("email"))
            pk = stable_uuid("share_event", row.get("id"))
            update_by_pk(
                InclinicShareEventV2,
                pk,
                {
                    **self.source_common(
                        self.default_alias,
                        "sharing_management_sharelog",
                        row,
                        "manual_wrong_doctor_number_exclusion" if exclusion else "sharelog_field_rep_id_campaign_fieldrep_id",
                        "excluded" if exclusion else "verified" if fr else "unresolved",
                    ),
                    "is_current": not bool(exclusion),
                    "campaign_uuid": self.campaign_uuid(row.get("brand_campaign_id")) if row.get("brand_campaign_id") else None,
                    "legacy_campaign_id": clean_text(row.get("brand_campaign_id")),
                    "collateral_uuid": self.collateral_uuid(row.get("collateral_id")),
                    "doctor_uuid": doctor_uuid,
                    "inclinic_doctor_uuid": inclinic_doctor_uuid,
                    "doctor_phone_normalized": normalize_phone(row.get("doctor_identifier")) or None,
                    "shared_by_field_rep_uuid": self.field_rep_uuid(field_rep_id) if fr else None,
                    "campaign_fieldrep_id": field_rep_id,
                    "field_rep_email_normalized": field_rep_email or None,
                    "field_rep_email_matches_campaign_fieldrep": email_matches,
                    "share_channel_normalized": clean_text(row.get("share_channel")).lower() or None,
                    "shared_at": row.get("share_timestamp"),
                    "old_id": clean_text(row.get("id")),
                    "old_share_channel": clean_text(row.get("share_channel")),
                    "old_share_timestamp": row.get("share_timestamp"),
                    "old_message_text": clean_text(row.get("message_text")),
                    "old_created_at": row.get("created_at"),
                    "old_updated_at": row.get("updated_at"),
                    "old_short_link_id": clean_text(row.get("short_link_id")),
                    "old_collateral_id": clean_text(row.get("collateral_id")),
                    "old_doctor_identifier": clean_text(row.get("doctor_identifier")),
                    "old_brand_campaign_id": clean_text(row.get("brand_campaign_id")),
                    "old_field_rep_email": clean_text(row.get("field_rep_email")) or None,
                    "old_field_rep_id": field_rep_id,
                },
            )
            self.inc("share_event_v2.rows")

    def transaction_consistency(
        self,
        row: dict[str, Any],
        fr: dict[str, Any] | None,
        raw_brand_fr: dict[str, Any] | None,
    ) -> tuple[str, str, str | None, str, dict[str, Any] | None]:
        field_rep_id = clean_text(row.get("field_rep_id"))
        raw_field_rep_unique_id = clean_text(row.get("field_rep_unique_id"))
        if not fr:
            return "missing", "campaign_fieldrep_id_missing", None, raw_field_rep_unique_id, raw_brand_fr

        canonical_brand_id = clean_text(fr.get("brand_supplied_field_rep_id"))
        canonical_brand_fr = self.fr_by_brand.get(canonical_brand_id) if canonical_brand_id else None
        resolved_uuid = self.field_rep_uuid(field_rep_id)

        if not canonical_brand_id:
            return (
                "missing",
                "campaign_fieldrep_id_only_brand_supplied_missing",
                resolved_uuid,
                "",
                raw_brand_fr,
            )

        if not raw_field_rep_unique_id:
            return (
                "consistent",
                "campaign_fieldrep_id_resolved_brand_supplied_id_from_master",
                resolved_uuid,
                canonical_brand_id,
                canonical_brand_fr,
            )

        if raw_field_rep_unique_id == canonical_brand_id:
            return (
                "consistent",
                "campaign_fieldrep_id_and_brand_supplied_id",
                resolved_uuid,
                canonical_brand_id,
                raw_brand_fr or canonical_brand_fr,
            )

        if raw_field_rep_unique_id == field_rep_id:
            return (
                "consistent",
                "legacy_field_rep_unique_id_echoed_campaign_fieldrep_id",
                resolved_uuid,
                canonical_brand_id,
                canonical_brand_fr,
            )

        if raw_brand_fr and clean_text(raw_brand_fr.get("id")) == field_rep_id:
            return (
                "consistent",
                "campaign_fieldrep_id_and_brand_supplied_id",
                resolved_uuid,
                canonical_brand_id,
                raw_brand_fr,
            )

        return (
            "conflict",
            "campaign_fieldrep_id_preferred_over_conflicting_brand_supplied_id",
            resolved_uuid,
            canonical_brand_id,
            raw_brand_fr,
        )

    def backfill_collateral_transactions(self):
        for row in self.transactions:
            field_rep_id = clean_text(row.get("field_rep_id"))
            raw_field_rep_unique_id = clean_text(row.get("field_rep_unique_id"))
            fr = self.fr_by_id.get(field_rep_id)
            raw_brand_fr = self.fr_by_brand.get(raw_field_rep_unique_id) if raw_field_rep_unique_id else None
            status, basis, resolved_uuid, brand_supplied_field_rep_id, brand_fr = self.transaction_consistency(row, fr, raw_brand_fr)
            field_rep_conflict_exclusion = self.field_rep_conflict_transaction_exclusion_reason(row, status)
            if status == "conflict" and not field_rep_conflict_exclusion:
                self.record_exception(
                    database_alias=self.default_alias,
                    source_table="sharing_management_collateraltransaction",
                    source_pk_value=row.get("id"),
                    entity_type="collateral_transaction",
                    issue_code="TRANSACTION_FIELD_REP_ID_UNIQUE_ID_CONFLICT",
                    details={
                        "field_rep_id": field_rep_id,
                        "field_rep_unique_id": raw_field_rep_unique_id,
                        "field_rep_id_brand_supplied": clean_text(fr.get("brand_supplied_field_rep_id")) if fr else "",
                        "field_rep_unique_id_resolves_to_campaign_fieldrep_id": clean_text(raw_brand_fr.get("id")) if raw_brand_fr else "",
                        "resolved_brand_supplied_field_rep_id": brand_supplied_field_rep_id,
                    },
                    raw_payload=row,
                )
            if not fr:
                self.record_exception(
                    database_alias=self.default_alias,
                    source_table="sharing_management_collateraltransaction",
                    source_pk_value=row.get("id"),
                    entity_type="collateral_transaction",
                    issue_code="TRANSACTION_FIELD_REP_ID_NOT_FOUND",
                    details={"field_rep_id": field_rep_id},
                    raw_payload=row,
                )
            exclusion = (
                field_rep_conflict_exclusion
                or ("manual_wrong_doctor_number_exclusion" if self.wrong_doctor_number_exclusion(row.get("doctor_number")) else "")
            )
            if exclusion:
                doctor_uuid, inclinic_doctor_uuid, candidates = None, None, []
                activity_status = "excluded"
            else:
                doctor_uuid, inclinic_doctor_uuid, candidates = self.resolve_doctor_from_phone(row.get("doctor_number"))
                activity_status = "viewed" if parse_bool(row.get("has_viewed")) or row.get("viewed_at") or row.get("first_viewed_at") else "sent"
            pk = stable_uuid("collateral_transaction", row.get("id"))
            update_by_pk(
                InclinicCollateralTransactionV2,
                pk,
                {
                    **self.source_common(
                        self.default_alias,
                        "sharing_management_collateraltransaction",
                        row,
                        exclusion if exclusion else basis,
                        "excluded" if exclusion else "verified" if resolved_uuid else "unresolved",
                    ),
                    "is_current": not bool(exclusion),
                    "campaign_uuid": self.campaign_uuid(row.get("brand_campaign_id")) if row.get("brand_campaign_id") else None,
                    "legacy_campaign_id": clean_text(row.get("brand_campaign_id")),
                    "collateral_uuid": self.collateral_uuid(row.get("collateral_id")),
                    "doctor_uuid": doctor_uuid,
                    "inclinic_doctor_uuid": inclinic_doctor_uuid,
                    "doctor_phone_normalized": normalize_phone(row.get("doctor_number")) or None,
                    "field_rep_uuid_from_campaign_fieldrep_id": self.field_rep_uuid(field_rep_id) if fr else None,
                    "field_rep_uuid_from_brand_supplied_id": self.field_rep_uuid(brand_fr.get("id")) if brand_fr else None,
                    "resolved_field_rep_uuid": resolved_uuid,
                    "campaign_fieldrep_id": field_rep_id,
                    "brand_supplied_field_rep_id": brand_supplied_field_rep_id,
                    "field_rep_identifier_consistency_status": status,
                    "field_rep_resolution_basis": basis,
                    "activity_summary_status": activity_status,
                    "old_id": clean_text(row.get("id")),
                    "old_transaction_id": clean_text(row.get("transaction_id")),
                    "old_brand_campaign_id": clean_text(row.get("brand_campaign_id")),
                    "old_field_rep_id": field_rep_id,
                    "old_field_rep_unique_id": raw_field_rep_unique_id,
                    "old_doctor_name": clean_text(row.get("doctor_name")),
                    "old_doctor_number": clean_text(row.get("doctor_number")),
                    "old_doctor_unique_id": clean_text(row.get("doctor_unique_id")),
                    "old_collateral_id": clean_text(row.get("collateral_id")),
                    "old_transaction_date": row.get("transaction_date"),
                    "old_has_viewed": parse_bool(row.get("has_viewed")),
                    "old_downloaded_pdf": parse_bool(row.get("downloaded_pdf") if "downloaded_pdf" in row else row.get("has_downloaded_pdf")),
                    "old_pdf_completed": parse_bool(row.get("pdf_completed") if "pdf_completed" in row else row.get("has_viewed_last_page")),
                    "old_video_view_lt_50": parse_int(row.get("video_view_lt_50")),
                    "old_video_view_gt_50": parse_bool(row.get("video_view_gt_50")),
                    "old_video_completed": parse_bool(row.get("video_completed") if "video_completed" in row else row.get("video_view_100")),
                    "old_pdf_total_pages": parse_int(row.get("pdf_total_pages")),
                    "old_last_video_percentage": parse_int(row.get("last_video_percentage") or row.get("video_watch_percentage")),
                    "old_pdf_last_page": parse_int(row.get("pdf_last_page") or row.get("last_page_scrolled")),
                    "old_doctor_viewer_engagement_id": clean_text(row.get("doctor_viewer_engagement_id")),
                    "old_share_management_engagement_id": clean_text(row.get("share_management_engagement_id")),
                    "old_video_tracking_last_event_id": clean_text(row.get("video_tracking_last_event_id")),
                    "old_created_at": row.get("created_at"),
                    "old_updated_at": row.get("updated_at"),
                    "old_sent_at": row.get("sent_at"),
                    "old_viewed_at": row.get("viewed_at"),
                    "old_first_viewed_at": row.get("first_viewed_at"),
                    "old_viewed_last_page_at": row.get("viewed_last_page_at"),
                    "old_video_lt_50_at": row.get("video_lt_50_at"),
                    "old_video_gt_50_at": row.get("video_gt_50_at"),
                    "old_video_100_at": row.get("video_100_at"),
                    "old_last_viewed_at": row.get("last_viewed_at"),
                    "old_dv_engagement_id": clean_text(row.get("dv_engagement_id")),
                    "old_field_rep_email": clean_text(row.get("field_rep_email")) or None,
                    "old_share_channel": clean_text(row.get("share_channel")),
                    "old_sm_engagement_id": clean_text(row.get("sm_engagement_id")),
                    "old_video_watch_percentage": parse_int(row.get("video_watch_percentage")),
                },
            )
            self.inc("collateral_transaction_v2.rows")

    def parse_and_backfill_assigned_roster(self, path: Path):
        parsed, exceptions = parse_mismatch_csv(path)
        for exc in exceptions:
            self.record_exception(
                database_alias=self.default_alias,
                source_table=path.name,
                source_pk_column="row",
                source_pk_value=exc["source_pk_value"],
                entity_type=exc["entity_type"],
                issue_code=exc["issue_code"],
                details=exc["issue_details"],
                raw_payload=exc["raw_payload"],
            )

        alias_by_brand = {
            brand: {
                "legacy_alias_uuid": stable_uuid("legacy_doctor_rep_alias", self.campaign_id_norm, brand, cfr_id, legacy),
                "campaign_fieldrep_id": cfr_id,
                "legacy_value": legacy,
            }
            for brand, _name, cfr_id, legacy in LEGACY_DOCTOR_REP_ALIASES
        }
        for row in parsed:
            brand_id = row["brand_supplied_field_rep_id"]
            fr = self.fr_by_brand.get(brand_id)
            if not fr:
                self.record_exception(
                    database_alias=self.default_alias,
                    source_table=path.name,
                    source_pk_column="ID",
                    source_pk_value=brand_id,
                    entity_type="assigned_doctor",
                    issue_code="ROSTER_FIELD_REP_BRAND_ID_NOT_FOUND",
                    details=row,
                    raw_payload=row,
                )
                continue

            staging_pk = stable_uuid("manual_correction_staging", self.campaign_id_norm, brand_id, row["doctor_phone_normalized"])
            update_by_pk(
                InclinicManualRepDoctorCorrectionStagingV2,
                staging_pk,
                {
                    **common_fields(
                        alias=self.default_alias,
                        table=path.name,
                        row={"id": f"{row['row_number']}:{brand_id}:{row['doctor_phone_normalized']}", "created_at": timezone.now()},
                        batch_id=self.batch_id,
                        verification_status="parsed",
                        verification_basis="mismatch_spreadsheet_parser",
                    ),
                    "source_pk_column": "ID+doctor_phone",
                    "source_pk_value": f"{brand_id}:{row['doctor_phone_normalized']}",
                    "legacy_campaign_id": self.campaign_id,
                    "brand_supplied_field_rep_id": brand_id,
                    "field_rep_name_raw": row["field_rep_label"],
                    "doctor_name_raw": row["doctor_name_raw"],
                    "doctor_phone_raw": row["doctor_phone_raw"],
                    "doctor_name_normalized": row["doctor_name_normalized"],
                    "doctor_phone_normalized": row["doctor_phone_normalized"],
                    "parse_status": "parsed",
                    "parse_notes": "",
                    "raw_payload_json": to_json(row),
                },
            )
            self.inc("manual_staging.rows")

            alias = alias_by_brand.get(brand_id)
            candidates = self.doctors_by_phone.get(row["doctor_phone_normalized"], [])
            chosen = None
            match_basis = "brand_supplied_id_campaign_phone"
            match_status = "doctor_candidate"
            if alias:
                alias_candidates = [d for d in candidates if clean_text(d.get("rep_id")) == alias["legacy_value"]]
                if alias_candidates:
                    chosen = alias_candidates[0]
                    match_basis = "exception_bridge_rep_id_phone"
                    match_status = "matched"
                elif candidates:
                    chosen = candidates[0]
                    match_basis = "brand_supplied_id_campaign_phone"
                    match_status = "ambiguous" if len(candidates) > 1 else "doctor_candidate"
            elif candidates:
                chosen = candidates[0]
                match_status = "ambiguous" if len(candidates) > 1 else "doctor_candidate"

            roster_pk = stable_uuid("assigned_roster", self.campaign_id_norm, brand_id, row["doctor_phone_normalized"])
            update_by_pk(
                InclinicAssignedDoctorRosterV2,
                roster_pk,
                {
                    **common_fields(
                        alias=self.default_alias,
                        table=path.name,
                        row={"id": f"{brand_id}:{row['doctor_phone_normalized']}", "created_at": timezone.now()},
                        batch_id=self.batch_id,
                        verification_status="verified" if match_status == "matched" else match_status,
                        verification_basis=match_basis,
                    ),
                    "source_pk_column": "ID+doctor_phone",
                    "source_pk_value": f"{brand_id}:{row['doctor_phone_normalized']}",
                    "campaign_uuid": self.campaign_uuid(self.campaign_id),
                    "legacy_campaign_id": self.campaign_id,
                    "brand_supplied_field_rep_id": brand_id,
                    "campaign_fieldrep_id": clean_text(fr.get("id")),
                    "field_rep_uuid": self.field_rep_uuid(fr.get("id")),
                    "doctor_uuid": self.doctor_uuid(row["doctor_phone_normalized"]),
                    "inclinic_doctor_uuid": stable_uuid("inclinic_doctor", chosen.get("id")) if chosen else None,
                    "doctor_name_raw": row["doctor_name_raw"],
                    "doctor_name_normalized": row["doctor_name_normalized"],
                    "doctor_phone_raw": row["doctor_phone_raw"],
                    "doctor_phone_normalized": row["doctor_phone_normalized"],
                    "legacy_doctor_viewer_rep_id": clean_text(chosen.get("rep_id")) if chosen else (alias["legacy_value"] if alias else None),
                    "match_basis": match_basis,
                    "match_status": match_status,
                    "assignment_status": "active",
                    "raw_payload_json": to_json(row),
                },
            )
            self.inc("assigned_roster.rows")

    def backfill_activity_events(self):
        transactions = InclinicCollateralTransactionV2.objects.filter(
            migration_batch_id=self.batch_id,
            is_current=True,
        )
        for tx in transactions:
            event_specs = [
                ("sent", tx.old_sent_at, tx.old_sent_at is not None, "sent_at", ""),
                ("viewed", tx.old_viewed_at or tx.old_first_viewed_at, bool(tx.old_has_viewed or tx.old_viewed_at or tx.old_first_viewed_at), "has_viewed/viewed_at/first_viewed_at", ""),
                ("first_viewed", tx.old_first_viewed_at, tx.old_first_viewed_at is not None, "first_viewed_at", ""),
                ("last_viewed", tx.old_last_viewed_at, tx.old_last_viewed_at is not None, "last_viewed_at", ""),
                ("pdf_downloaded", tx.old_last_viewed_at or tx.old_viewed_at, bool(tx.old_downloaded_pdf), "downloaded_pdf", ""),
                ("pdf_completed", tx.old_viewed_last_page_at, bool(tx.old_pdf_completed), "pdf_completed", ""),
                ("video_lt_50", tx.old_video_lt_50_at, bool(tx.old_video_view_lt_50), "video_view_lt_50/video_lt_50_at", clean_text(tx.old_video_view_lt_50)),
                ("video_gt_50", tx.old_video_gt_50_at, bool(tx.old_video_view_gt_50), "video_view_gt_50/video_gt_50_at", ""),
                ("video_100", tx.old_video_100_at, bool(tx.old_video_completed), "video_completed/video_100_at", ""),
                ("video_watch_percentage", tx.old_last_viewed_at, bool(tx.old_video_watch_percentage), "video_watch_percentage", clean_text(tx.old_video_watch_percentage)),
            ]
            for activity_type, when, should_create, source_flag, value in event_specs:
                if not should_create:
                    continue
                pk = stable_uuid("doctor_activity_event", tx.transaction_uuid, activity_type, source_flag)
                update_by_pk(
                    InclinicDoctorActivityEventV2,
                    pk,
                    {
                        "source_system": SYSTEM_NAME,
                        "source_database": tx.source_database,
                        "source_table": "sharing_management_collateraltransaction",
                        "source_pk_column": "id",
                        "source_pk_value": tx.old_id or tx.source_pk_value,
                        "source_created_at": tx.old_created_at,
                        "source_updated_at": tx.old_updated_at,
                        "migration_batch_id": self.batch_id,
                        "migrated_at": timezone.now(),
                        "verification_status": tx.verification_status,
                        "verification_basis": tx.field_rep_resolution_basis,
                        "is_current": True,
                        "valid_from": when,
                        "valid_to": None,
                        "raw_payload_json": tx.raw_payload_json,
                        "transaction_uuid": tx.transaction_uuid,
                        "share_event_uuid": None,
                        "doctor_uuid": tx.doctor_uuid,
                        "inclinic_doctor_uuid": tx.inclinic_doctor_uuid,
                        "campaign_uuid": tx.campaign_uuid,
                        "collateral_uuid": tx.collateral_uuid,
                        "field_rep_uuid_for_activity": tx.resolved_field_rep_uuid,
                        "activity_type": activity_type,
                        "activity_at": when,
                        "activity_value": value,
                        "source_flag_column": source_flag,
                    },
                )
                self.inc("doctor_activity_event_v2.rows")
