from __future__ import annotations

import csv
import string
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from admin_dashboard.views import _ensure_portal_user_for_master_rep
from campaign_management.master_models import MasterCampaign, MasterFieldRep
from doctor_viewer.models import Doctor
from user_management.models import User


MASTER_DB_ALIAS = getattr(settings, "MASTER_DB_ALIAS", "master")


class Command(BaseCommand):
    help = (
        "Import doctors from a CSV and attach them to field reps for a given brand "
        "or brand campaign. Validates the full file before creating any doctors."
    )

    HEADER_ALIASES = {
        "rep_email": [
            "Field-rep email",
            "Field Rep Mail",
            "Field Rep Email",
            "Rep Email",
        ],
        "rep_field_id": [
            "brand-supplied-field-rep-id",
            "Brand Supplied Field Rep ID",
            "Field ID",
            "Field Rep ID",
        ],
        "rep_phone": [
            "Field Rep Number",
            "Field-rep number",
            "Field Rep Phone",
            "Field Rep Mobile Number",
        ],
        "doctor_name": [
            "DOCTOR NAME",
            "Doctor Name",
        ],
        "doctor_phone": [
            "DR'sWHATSAPPMOBILENUMBER",
            "DR's WHATSAPP MOBILE NUMBER",
            "Doctor Number",
            "Doctor WhatsApp Number",
            "Doctor Mobile Number",
        ],
    }

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Absolute or relative path to the CSV file")

        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument(
            "--brand-id",
            dest="brand_id",
            help="Master brand_id to scope field reps",
        )
        target.add_argument(
            "--brand-campaign-id",
            dest="brand_campaign_id",
            help="Brand Campaign ID (UUID with or without dashes) used to derive brand_id",
        )

        parser.add_argument(
            "--source",
            default="prefill",
            choices=["manual", "prefill"],
            help="Doctor.source value to write for imported rows (default: prefill)",
        )
        parser.add_argument(
            "--delimiter",
            default=",",
            help="CSV delimiter (default: ,)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report what would be created without writing doctors",
        )

    @staticmethod
    def _normalize_phone(value: str | None) -> str:
        return "".join(ch for ch in (value or "") if ch.isdigit())

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        return (value or "").strip()

    @staticmethod
    def _normalize_campaign_id(value: str | None) -> str | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        compact = raw.replace("-", "").lower()
        if len(compact) == 32 and all(ch in string.hexdigits for ch in compact):
            return compact
        return None

    def _resolve_header(self, fieldnames, logical_name: str) -> str | None:
        normalized = {(name or "").strip().lower(): name for name in (fieldnames or [])}
        for candidate in self.HEADER_ALIASES[logical_name]:
            actual = normalized.get(candidate.lower())
            if actual:
                return actual
        return None

    def _derive_brand_context(self, *, brand_id: str | None, brand_campaign_id: str | None) -> tuple[str, str | None]:
        if brand_id:
            return str(brand_id).strip(), None

        master_campaign_id = self._normalize_campaign_id(brand_campaign_id)
        if not master_campaign_id:
            raise CommandError("Invalid --brand-campaign-id. Expected a UUID with or without dashes.")

        campaign = (
            MasterCampaign.objects.using(MASTER_DB_ALIAS)
            .filter(id=master_campaign_id)
            .only("id", "brand_id")
            .first()
        )
        if not campaign or not getattr(campaign, "brand_id", None):
            raise CommandError(f'No master campaign found for brand campaign id "{brand_campaign_id}".')

        return str(campaign.brand_id), master_campaign_id

    def _build_rep_lookups(self, *, brand_id: str, master_campaign_id: str | None):
        qs = (
            MasterFieldRep.objects.using(MASTER_DB_ALIAS)
            .select_related("user")
            .filter(brand_id=str(brand_id), is_active=True)
        )
        if master_campaign_id:
            qs = qs.filter(campaign_links__campaign_id=master_campaign_id).distinct()

        reps = list(qs)
        if not reps:
            scope = f'brand "{brand_id}"'
            if master_campaign_id:
                scope += f' and campaign "{master_campaign_id}"'
            raise CommandError(f"No active field reps found for {scope}.")

        by_email_and_field_id = {}
        by_email_and_phone = {}

        for rep in reps:
            email = (getattr(getattr(rep, "user", None), "email", "") or "").strip().lower()
            field_id = (getattr(rep, "brand_supplied_field_rep_id", "") or "").strip()
            phone = self._normalize_phone(getattr(rep, "phone_number", ""))

            if email and field_id:
                by_email_and_field_id[(email, field_id)] = rep
            if email and phone:
                by_email_and_phone[(email, phone)] = rep

        return reps, by_email_and_field_id, by_email_and_phone

    def _load_rows(self, *, csv_path: Path, delimiter: str):
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=delimiter)
                fieldnames = reader.fieldnames or []
                rows = list(reader)
        except FileNotFoundError as exc:
            raise CommandError(f"CSV file not found: {csv_path}") from exc
        except OSError as exc:
            raise CommandError(f"Unable to read CSV file {csv_path}: {exc}") from exc

        if not fieldnames:
            raise CommandError("CSV file is empty or missing a header row.")

        headers = {
            "rep_email": self._resolve_header(fieldnames, "rep_email"),
            "rep_field_id": self._resolve_header(fieldnames, "rep_field_id"),
            "rep_phone": self._resolve_header(fieldnames, "rep_phone"),
            "doctor_name": self._resolve_header(fieldnames, "doctor_name"),
            "doctor_phone": self._resolve_header(fieldnames, "doctor_phone"),
        }

        missing = [key for key in ("rep_email", "doctor_name", "doctor_phone") if not headers[key]]
        if missing:
            raise CommandError(
                "Missing required CSV columns: "
                + ", ".join(missing)
                + ". Supported headers are defined in the command."
            )
        if not headers["rep_field_id"] and not headers["rep_phone"]:
            raise CommandError(
                "CSV must contain either a brand-supplied field rep id column or a field rep phone column."
            )

        return headers, rows

    def _validate_rows(
        self,
        *,
        rows,
        headers,
        rep_by_email_and_field_id,
        rep_by_email_and_phone,
    ):
        cleaned_rows = []
        errors = []
        seen = set()

        for row_number, row in enumerate(rows, start=2):
            if not any(self._normalize_text(value) for value in row.values()):
                continue

            rep_email = self._normalize_text(row.get(headers["rep_email"])).lower()
            rep_field_id = self._normalize_text(row.get(headers["rep_field_id"])) if headers["rep_field_id"] else ""
            rep_phone = self._normalize_phone(row.get(headers["rep_phone"])) if headers["rep_phone"] else ""
            doctor_name = self._normalize_text(row.get(headers["doctor_name"]))
            doctor_phone = self._normalize_phone(row.get(headers["doctor_phone"]))

            row_errors = []

            try:
                validate_email(rep_email)
            except ValidationError:
                row_errors.append("Field rep email is invalid")

            if not rep_field_id and not rep_phone:
                row_errors.append("Field rep identifier is missing")
            if not doctor_name:
                row_errors.append("Doctor name is required")
            if len(doctor_phone) < 8:
                row_errors.append("Doctor phone number is invalid")

            master_rep = None
            if not row_errors:
                if rep_field_id:
                    master_rep = rep_by_email_and_field_id.get((rep_email, rep_field_id))
                if not master_rep and rep_phone:
                    master_rep = rep_by_email_and_phone.get((rep_email, rep_phone))
                if not master_rep:
                    row_errors.append("Field rep not found for the provided brand / campaign scope")

            portal_user = None
            if master_rep:
                portal_user = User.objects.filter(email__iexact=rep_email).first()
                duplicate_key = (master_rep.pk, doctor_phone)
                if duplicate_key in seen:
                    row_errors.append("Duplicate doctor found in uploaded CSV for the same field rep")
                elif portal_user and Doctor.objects.filter(rep=portal_user, phone=doctor_phone).exists():
                    row_errors.append("Doctor already exists for specific field rep")
                else:
                    seen.add(duplicate_key)

            if row_errors:
                errors.append(f"Row {row_number}: {'; '.join(row_errors)}")
                continue

            cleaned_rows.append(
                {
                    "master_rep": master_rep,
                    "rep_email": rep_email,
                    "doctor_name": doctor_name,
                    "doctor_phone": doctor_phone,
                }
            )

        return cleaned_rows, errors

    def _save_rows(self, *, rows, source: str) -> int:
        created = 0
        portal_user_cache = {}

        with transaction.atomic():
            for row in rows:
                master_rep = row["master_rep"]
                portal_user = portal_user_cache.get(master_rep.pk)
                if portal_user is None:
                    portal_user = _ensure_portal_user_for_master_rep(master_rep)
                    portal_user_cache[master_rep.pk] = portal_user

                Doctor.objects.create(
                    rep=portal_user,
                    name=row["doctor_name"],
                    phone=row["doctor_phone"],
                    source=source,
                )
                created += 1

        return created

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"]).expanduser()
        delimiter = options["delimiter"]
        source = options["source"]
        dry_run = bool(options["dry_run"])

        brand_id, master_campaign_id = self._derive_brand_context(
            brand_id=options.get("brand_id"),
            brand_campaign_id=options.get("brand_campaign_id"),
        )

        headers, rows = self._load_rows(csv_path=csv_path, delimiter=delimiter)
        _, rep_by_email_and_field_id, rep_by_email_and_phone = self._build_rep_lookups(
            brand_id=brand_id,
            master_campaign_id=master_campaign_id,
        )
        cleaned_rows, errors = self._validate_rows(
            rows=rows,
            headers=headers,
            rep_by_email_and_field_id=rep_by_email_and_field_id,
            rep_by_email_and_phone=rep_by_email_and_phone,
        )

        if errors:
            for error in errors:
                self.stdout.write(self.style.ERROR(error))
            raise CommandError(
                f"Import aborted. Found {len(errors)} validation error(s); no doctors were created."
            )

        if not cleaned_rows:
            self.stdout.write(self.style.WARNING("No doctor rows found to import."))
            return

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run successful. {len(cleaned_rows)} doctor row(s) validated for import."
                )
            )
            return

        created = self._save_rows(rows=cleaned_rows, source=source)
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {created} doctor row(s) for brand_id={brand_id}."
            )
        )
