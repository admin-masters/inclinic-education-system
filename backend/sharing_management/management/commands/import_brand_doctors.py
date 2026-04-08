from __future__ import annotations

import csv
import string
from collections import defaultdict
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q

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
        parser.add_argument(
            "--report-path",
            dest="report_path",
            help="Optional path for the execution report CSV. Defaults next to the source CSV.",
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

    def _collect_rep_identifiers(self, *, rows, headers) -> tuple[set[str], set[str], set[str]]:
        emails = set()
        field_ids = set()
        phones = set()

        for row in rows:
            rep_email = self._normalize_text(row.get(headers["rep_email"])).lower()
            rep_field_id = self._normalize_text(row.get(headers["rep_field_id"])) if headers["rep_field_id"] else ""
            rep_phone = self._normalize_phone(row.get(headers["rep_phone"])) if headers["rep_phone"] else ""

            if rep_email:
                emails.add(rep_email)
            if rep_field_id:
                field_ids.add(rep_field_id)
            if rep_phone:
                phones.add(rep_phone)

        return emails, field_ids, phones

    @staticmethod
    def _new_rep_lookup_bucket() -> dict[str, defaultdict]:
        return {
            "email_and_field_id": defaultdict(list),
            "email_and_phone": defaultdict(list),
            "field_id_only": defaultdict(list),
            "phone_only": defaultdict(list),
            "email_only": defaultdict(list),
        }

    def _index_reps(self, reps) -> dict[str, defaultdict]:
        buckets = self._new_rep_lookup_bucket()

        for rep in reps:
            email = (getattr(getattr(rep, "user", None), "email", "") or "").strip().lower()
            field_id = (getattr(rep, "brand_supplied_field_rep_id", "") or "").strip()
            phone = self._normalize_phone(getattr(rep, "phone_number", ""))

            if email and field_id:
                buckets["email_and_field_id"][(email, field_id)].append(rep)
            if email and phone:
                buckets["email_and_phone"][(email, phone)].append(rep)
            if field_id:
                buckets["field_id_only"][field_id].append(rep)
            if phone:
                buckets["phone_only"][phone].append(rep)
            if email:
                buckets["email_only"][email].append(rep)

        return buckets

    def _build_rep_lookups(
        self,
        *,
        brand_id: str,
        master_campaign_id: str | None,
        rep_emails: set[str],
        rep_field_ids: set[str],
        rep_phones: set[str],
    ):
        base_qs = MasterFieldRep.objects.using(MASTER_DB_ALIAS).select_related("user").filter(is_active=True)

        identifier_filter = Q()
        if rep_emails:
            identifier_filter |= Q(user__email__in=sorted(rep_emails))
        if rep_field_ids:
            identifier_filter |= Q(brand_supplied_field_rep_id__in=sorted(rep_field_ids))
        if identifier_filter:
            base_qs = base_qs.filter(identifier_filter)

        scoped_qs = base_qs.filter(brand_id=str(brand_id))
        if master_campaign_id:
            scoped_qs = scoped_qs.filter(campaign_links__campaign_id=master_campaign_id).distinct()

        scoped_reps = list(scoped_qs.distinct())
        global_reps = list(base_qs.distinct())

        if not global_reps:
            scope = f'brand "{brand_id}"'
            if master_campaign_id:
                scope += f' and campaign "{master_campaign_id}"'
            raise CommandError(f"No master field reps found for the CSV identifiers within {scope}.")

        return {
            "scoped": self._index_reps(scoped_reps),
            "global": self._index_reps(global_reps),
            "scoped_count": len(scoped_reps),
            "global_count": len(global_reps),
        }

    @staticmethod
    def _unique_candidate(candidates):
        if len(candidates) == 1:
            return candidates[0], None
        if len(candidates) > 1:
            return None, "multiple_matches"
        return None, None

    def _resolve_master_rep(self, *, rep_email: str, rep_field_id: str, rep_phone: str, lookups):
        attempts = []

        if rep_email and rep_field_id:
            attempts.append(
                ("scoped email+field_id", lookups["scoped"]["email_and_field_id"].get((rep_email, rep_field_id), []))
            )
        if rep_email and rep_phone:
            attempts.append(
                ("scoped email+phone", lookups["scoped"]["email_and_phone"].get((rep_email, rep_phone), []))
            )
        if rep_email and rep_field_id:
            attempts.append(
                ("global master email+field_id", lookups["global"]["email_and_field_id"].get((rep_email, rep_field_id), []))
            )
        if rep_email and rep_phone:
            attempts.append(
                ("global master email+phone", lookups["global"]["email_and_phone"].get((rep_email, rep_phone), []))
            )
        if rep_field_id:
            attempts.append(("scoped field_id", lookups["scoped"]["field_id_only"].get(rep_field_id, [])))
        if rep_phone:
            attempts.append(("scoped phone", lookups["scoped"]["phone_only"].get(rep_phone, [])))
        if rep_field_id:
            attempts.append(("global master field_id", lookups["global"]["field_id_only"].get(rep_field_id, [])))
        if rep_phone:
            attempts.append(("global master phone", lookups["global"]["phone_only"].get(rep_phone, [])))
        if rep_email:
            attempts.append(("scoped email", lookups["scoped"]["email_only"].get(rep_email, [])))
        if rep_email:
            attempts.append(("global master email", lookups["global"]["email_only"].get(rep_email, [])))

        ambiguous_sources = []
        for label, candidates in attempts:
            rep, status = self._unique_candidate(candidates)
            if rep:
                return rep, label, None
            if status == "multiple_matches":
                ambiguous_sources.append(label)

        if ambiguous_sources:
            return None, "", "Multiple master field reps matched the provided identifiers"
        return None, "", "Field rep not found in master DB"

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

    def _initial_report_row(
        self,
        *,
        row_number: int,
        rep_email: str,
        rep_field_id: str,
        rep_phone: str,
        doctor_name: str,
        doctor_phone: str,
    ) -> dict:
        return {
            "row_number": row_number,
            "field_rep_email": rep_email,
            "field_rep_id": rep_field_id,
            "field_rep_phone": rep_phone,
            "doctor_name": doctor_name,
            "doctor_phone": doctor_phone,
            "status": "",
            "message": "",
            "master_field_rep_id": "",
            "master_brand_id": "",
            "master_match_source": "",
            "portal_user_id": "",
            "doctor_id": "",
        }

    def _evaluate_rows(
        self,
        *,
        rows,
        headers,
        lookups,
    ):
        ready_rows = []
        report_rows = []
        seen = set()

        for row_number, row in enumerate(rows, start=2):
            if not any(self._normalize_text(value) for value in row.values()):
                continue

            rep_email = self._normalize_text(row.get(headers["rep_email"])).lower()
            rep_field_id = self._normalize_text(row.get(headers["rep_field_id"])) if headers["rep_field_id"] else ""
            rep_phone = self._normalize_phone(row.get(headers["rep_phone"])) if headers["rep_phone"] else ""
            doctor_name = self._normalize_text(row.get(headers["doctor_name"]))
            doctor_phone = self._normalize_phone(row.get(headers["doctor_phone"]))

            report_row = self._initial_report_row(
                row_number=row_number,
                rep_email=rep_email,
                rep_field_id=rep_field_id,
                rep_phone=rep_phone,
                doctor_name=doctor_name,
                doctor_phone=doctor_phone,
            )
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
            match_source = ""
            if not row_errors:
                master_rep, match_source, lookup_error = self._resolve_master_rep(
                    rep_email=rep_email,
                    rep_field_id=rep_field_id,
                    rep_phone=rep_phone,
                    lookups=lookups,
                )
                if not master_rep:
                    row_errors.append(lookup_error or "Field rep not found in master DB")
                else:
                    report_row["master_field_rep_id"] = str(master_rep.pk)
                    report_row["master_brand_id"] = str(getattr(master_rep, "brand_id", "") or "")
                    report_row["master_match_source"] = match_source

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
                if portal_user:
                    report_row["portal_user_id"] = str(portal_user.pk)

            if row_errors:
                report_row["status"] = "skipped"
                report_row["message"] = "; ".join(row_errors)
                report_rows.append(report_row)
                continue

            report_row["status"] = "ready"
            report_row["message"] = "Validated successfully"
            ready_rows.append(
                {
                    "report_row": report_row,
                    "master_rep": master_rep,
                    "rep_email": rep_email,
                    "match_source": match_source,
                    "doctor_name": doctor_name,
                    "doctor_phone": doctor_phone,
                }
            )
            report_rows.append(report_row)

        return ready_rows, report_rows

    def _save_rows(self, *, rows, source: str, dry_run: bool) -> tuple[int, int]:
        created = 0
        skipped = 0
        portal_user_cache = {}

        for row in rows:
            report_row = row["report_row"]
            label = (
                f"row={report_row['row_number']} rep_email={row['rep_email']} "
                f"doctor={row['doctor_name']} ({row['doctor_phone']})"
            )
            if row.get("match_source"):
                label = f"{label} match={row['match_source']}"

            if dry_run:
                report_row["status"] = "dry_run"
                report_row["message"] = "Validated successfully; doctor not created because --dry-run was used"
                self.stdout.write(self.style.WARNING(f"[DRY RUN] {label}"))
                skipped += 1
                continue

            try:
                with transaction.atomic():
                    master_rep = row["master_rep"]
                    portal_user = portal_user_cache.get(master_rep.pk)
                    if portal_user is None:
                        portal_user = _ensure_portal_user_for_master_rep(master_rep)
                        portal_user_cache[master_rep.pk] = portal_user
                    report_row["portal_user_id"] = str(portal_user.pk)

                    existing = Doctor.objects.filter(rep=portal_user, phone=row["doctor_phone"]).first()
                    if existing:
                        report_row["status"] = "skipped"
                        report_row["doctor_id"] = str(existing.pk)
                        report_row["message"] = "Doctor already exists for specific field rep"
                        self.stdout.write(self.style.WARNING(f"[SKIP] {label} reason={report_row['message']}"))
                        skipped += 1
                        continue

                    doctor = Doctor.objects.create(
                        rep=portal_user,
                        name=row["doctor_name"],
                        phone=row["doctor_phone"],
                        source=source,
                    )
                    report_row["status"] = "created"
                    report_row["doctor_id"] = str(doctor.pk)
                    report_row["message"] = "Doctor created successfully"
                    self.stdout.write(self.style.SUCCESS(f"[CREATED] {label} doctor_id={doctor.pk}"))
                    created += 1
            except Exception as exc:
                report_row["status"] = "error"
                report_row["message"] = str(exc)
                self.stdout.write(self.style.ERROR(f"[ERROR] {label} reason={exc}"))
                skipped += 1

        return created, skipped

    def _default_report_path(self, *, csv_path: Path, dry_run: bool) -> Path:
        suffix = "_doctor_import_dry_run_report.csv" if dry_run else "_doctor_import_report.csv"
        return csv_path.with_name(f"{csv_path.stem}{suffix}")

    def _write_report(self, *, report_rows: list[dict], report_path: Path) -> None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "row_number",
                    "field_rep_email",
                    "field_rep_id",
                    "field_rep_phone",
                    "doctor_name",
                    "doctor_phone",
                    "status",
                    "message",
                    "master_field_rep_id",
                    "master_brand_id",
                    "master_match_source",
                    "portal_user_id",
                    "doctor_id",
                ],
            )
            writer.writeheader()
            writer.writerows(report_rows)

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"]).expanduser()
        delimiter = options["delimiter"]
        source = options["source"]
        dry_run = bool(options["dry_run"])
        report_path = Path(options["report_path"]).expanduser() if options.get("report_path") else None

        brand_id, master_campaign_id = self._derive_brand_context(
            brand_id=options.get("brand_id"),
            brand_campaign_id=options.get("brand_campaign_id"),
        )

        headers, rows = self._load_rows(csv_path=csv_path, delimiter=delimiter)
        rep_emails, rep_field_ids, rep_phones = self._collect_rep_identifiers(rows=rows, headers=headers)
        lookups = self._build_rep_lookups(
            brand_id=brand_id,
            master_campaign_id=master_campaign_id,
            rep_emails=rep_emails,
            rep_field_ids=rep_field_ids,
            rep_phones=rep_phones,
        )
        ready_rows, report_rows = self._evaluate_rows(
            rows=rows,
            headers=headers,
            lookups=lookups,
        )
        final_report_path = report_path or self._default_report_path(csv_path=csv_path, dry_run=dry_run)

        self.stdout.write(
            f"Starting doctor import: file={csv_path} brand_id={brand_id}"
            + (f" master_campaign_id={master_campaign_id}" if master_campaign_id else "")
        )
        self.stdout.write(
            "Master field rep lookup: "
            f"scoped_matches={lookups['scoped_count']} "
            f"global_master_matches={lookups['global_count']} "
            f"csv_rep_emails={len(rep_emails)}"
        )

        for report_row in report_rows:
            if report_row["status"] == "skipped":
                match_segment = (
                    f"match={report_row['master_match_source']} "
                    if report_row["master_match_source"]
                    else ""
                )
                self.stdout.write(
                    self.style.WARNING(
                        f"[SKIP] row={report_row['row_number']} "
                        f"rep_email={report_row['field_rep_email']} "
                        f"doctor={report_row['doctor_name']} ({report_row['doctor_phone']}) "
                        f"{match_segment}"
                        f"reason={report_row['message']}"
                    )
                )

        if not report_rows:
            self.stdout.write(self.style.WARNING("No doctor rows found in the CSV."))
            return

        created, skipped_during_save = self._save_rows(rows=ready_rows, source=source, dry_run=dry_run)
        skipped_total = sum(1 for row in report_rows if row["status"] in {"skipped", "error", "dry_run"})
        if skipped_during_save and skipped_total < skipped_during_save:
            skipped_total = skipped_during_save

        self._write_report(report_rows=report_rows, report_path=final_report_path)

        self.stdout.write("")
        self.stdout.write(f"Report CSV: {final_report_path}")
        self.stdout.write(f"Total rows processed: {len(report_rows)}")
        self.stdout.write(f"Created: {created}")
        self.stdout.write(f"Not created / skipped: {skipped_total}")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run completed. Review the report CSV for details."))
        elif skipped_total:
            self.stdout.write(self.style.WARNING("Import completed with skipped rows. Review the report CSV for details."))
        else:
            self.stdout.write(self.style.SUCCESS("Import completed successfully with no skipped rows."))
