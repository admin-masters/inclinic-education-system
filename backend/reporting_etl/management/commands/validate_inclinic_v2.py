from __future__ import annotations

from django.core.management.base import BaseCommand

from reporting_etl.inclinic_v2 import TARGET_CAMPAIGN_ID, normalize_campaign_id, stable_uuid
from reporting_etl.models import (
    InclinicAssignedDoctorRosterV2,
    InclinicCampaignFieldRepAssignmentV2,
    InclinicCollateralTransactionV2,
    InclinicDoctorActivityEventV2,
    InclinicLegacyDoctorRepAliasV2,
    MigrationExceptionV2,
)


class Command(BaseCommand):
    help = "Validate InClinic v2 source-system mappings for a campaign."

    def add_arguments(self, parser):
        parser.add_argument("--campaign-id", default=TARGET_CAMPAIGN_ID)
        parser.add_argument("--batch-id", default="")

    def handle(self, *args, **options):
        campaign_id = options["campaign_id"]
        campaign_norm = normalize_campaign_id(campaign_id)
        campaign_uuid = stable_uuid("campaign", campaign_norm)
        batch_id = options["batch_id"].strip()

        assignment_qs = InclinicCampaignFieldRepAssignmentV2.objects.filter(
            legacy_campaign_id_normalized=campaign_norm
        )
        tx_qs = InclinicCollateralTransactionV2.objects.filter(campaign_uuid=campaign_uuid)
        roster_qs = InclinicAssignedDoctorRosterV2.objects.filter(campaign_uuid=campaign_uuid)
        activity_qs = InclinicDoctorActivityEventV2.objects.filter(campaign_uuid=campaign_uuid)
        alias_qs = InclinicLegacyDoctorRepAliasV2.objects.filter(campaign_uuid=campaign_uuid)
        exception_qs = MigrationExceptionV2.objects.filter(system_name="inclinic")
        if batch_id:
            assignment_qs = assignment_qs.filter(migration_batch_id=batch_id)
            tx_qs = tx_qs.filter(migration_batch_id=batch_id)
            roster_qs = roster_qs.filter(migration_batch_id=batch_id)
            activity_qs = activity_qs.filter(migration_batch_id=batch_id)
            alias_qs = alias_qs.filter(migration_batch_id=batch_id)
            exception_qs = exception_qs.filter(migration_batch_id=batch_id)

        assignment_pairs = {
            (row.legacy_campaign_id_normalized, row.campaign_fieldrep_id)
            for row in assignment_qs.only("legacy_campaign_id_normalized", "campaign_fieldrep_id")
        }
        tx_pair_matches = sum(
            1
            for tx in tx_qs.only("legacy_campaign_id", "campaign_fieldrep_id")
            if (normalize_campaign_id(tx.legacy_campaign_id), tx.campaign_fieldrep_id) in assignment_pairs
        )

        self.stdout.write("InClinic v2 validation")
        self.stdout.write(f"campaign_id: {campaign_id}")
        if batch_id:
            self.stdout.write(f"batch_id: {batch_id}")
        self.stdout.write(f"campaign assignments: {assignment_qs.count()}")
        self.stdout.write(f"collateral transactions: {tx_qs.count()}")
        self.stdout.write(f"transactions with campaign+field_rep assignment pair: {tx_pair_matches}")
        self.stdout.write(
            "transactions resolved by campaign_fieldrep.id: "
            f"{tx_qs.exclude(resolved_field_rep_uuid__isnull=True).exclude(resolved_field_rep_uuid='').count()}"
        )
        self.stdout.write(f"legacy doctor alias bridge rows: {alias_qs.count()}")
        self.stdout.write(f"assigned doctor roster rows: {roster_qs.count()}")
        self.stdout.write(
            "assigned doctor unique phones: "
            f"{roster_qs.values('field_rep_uuid', 'doctor_phone_normalized').distinct().count()}"
        )
        self.stdout.write(f"doctor activity event rows: {activity_qs.count()}")
        self.stdout.write(f"open exceptions: {exception_qs.filter(resolution_status='open').count()}")

        examples = [
            ("5763", "Baswaraj Shivling Biradar", "115", "116"),
            ("4614", "Rakhi Singh", "64", "91"),
            ("2731", "Nipan Deka", "174", "71"),
        ]
        self.stdout.write("")
        self.stdout.write("Required example checks")
        for brand_id, name, campaign_fieldrep_id, legacy_rep_id in examples:
            field_rep_uuid = stable_uuid("field_rep", campaign_fieldrep_id)
            tx_count = tx_qs.filter(campaign_fieldrep_id=campaign_fieldrep_id).count()
            assigned_count = (
                roster_qs.filter(
                    brand_supplied_field_rep_id=brand_id,
                    field_rep_uuid=field_rep_uuid,
                )
                .values("doctor_phone_normalized")
                .distinct()
                .count()
            )
            alias_exists = alias_qs.filter(
                brand_supplied_field_rep_id=brand_id,
                campaign_fieldrep_id=campaign_fieldrep_id,
                legacy_value=legacy_rep_id,
            ).exists()
            self.stdout.write(
                f"{brand_id} / {name}: activity_field_rep_id={campaign_fieldrep_id}, "
                f"legacy_doctor_rep_id={legacy_rep_id}, transactions={tx_count}, "
                f"assigned_unique_doctors={assigned_count}, alias_loaded={alias_exists}"
            )
