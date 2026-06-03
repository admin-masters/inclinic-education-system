"""Reporting ETL and source-system v2 lineage models."""

from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


def uuid_hex() -> str:
    return uuid.uuid4().hex


class EtlState(models.Model):
    """
    Stores timestamp of last ETL run for each model.
    """
    model_name   = models.CharField(max_length=100, unique=True)
    last_synced  = models.DateTimeField(default=timezone.make_aware(timezone.datetime.min))

    class Meta:
        app_label = 'reporting_etl'

    def __str__(self):
        return f"{self.model_name} @ {self.last_synced:%Y-%m-%d %H:%M}"


class SourceMigrationBatchV2(models.Model):
    migration_batch_id = models.CharField(max_length=64, primary_key=True)
    system_name = models.CharField(max_length=40, default="inclinic")
    database_name = models.CharField(max_length=100)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=30, default="running")
    input_file_names = models.TextField(default="[]")
    created_by = models.CharField(max_length=120)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "source_migration_batch_v2"


class CommonSourceFields(models.Model):
    source_system = models.CharField(max_length=40, default="inclinic")
    source_database = models.CharField(max_length=100)
    source_table = models.CharField(max_length=120)
    source_pk_column = models.CharField(max_length=120)
    source_pk_value = models.CharField(max_length=255)
    source_created_at = models.DateTimeField(null=True, blank=True)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    migration_batch_id = models.CharField(max_length=64)
    migrated_at = models.DateTimeField(default=timezone.now)
    verification_status = models.CharField(max_length=30, default="pending")
    verification_basis = models.CharField(max_length=100, default="")
    is_current = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    raw_payload_json = models.TextField(default="{}")

    class Meta:
        abstract = True


class MigrationExceptionV2(models.Model):
    exception_id = models.BigAutoField(primary_key=True)
    migration_batch_id = models.CharField(max_length=64)
    system_name = models.CharField(max_length=40, default="inclinic")
    database_name = models.CharField(max_length=100)
    source_table = models.CharField(max_length=120)
    source_pk_column = models.CharField(max_length=120)
    source_pk_value = models.CharField(max_length=255)
    entity_type = models.CharField(max_length=40)
    issue_code = models.CharField(max_length=80)
    issue_details = models.TextField()
    raw_payload_json = models.TextField(default="{}")
    resolution_status = models.CharField(max_length=30, default="open")
    resolved_by = models.CharField(max_length=120, null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "migration_exception_v2"
        indexes = [
            models.Index(fields=["migration_batch_id", "issue_code"]),
            models.Index(fields=["source_table", "source_pk_value"]),
        ]


class InclinicFieldRepIdentityV2(CommonSourceFields):
    inclinic_field_rep_identity_id = models.CharField(max_length=64, primary_key=True, default=uuid_hex)
    field_rep_uuid = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    campaign_fieldrep_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    brand_supplied_field_rep_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    source_column = models.CharField(max_length=120)
    source_value = models.CharField(max_length=255)
    source_value_normalized = models.CharField(max_length=255, null=True, blank=True)
    email_normalized = models.EmailField(max_length=254, null=True, blank=True)
    phone_normalized = models.CharField(max_length=20, null=True, blank=True)
    match_basis = models.CharField(max_length=100)

    campaign_fieldrep_full_name = models.CharField(max_length=200, null=True, blank=True)
    campaign_fieldrep_phone_number = models.CharField(max_length=50, null=True, blank=True)
    campaign_fieldrep_is_active = models.BooleanField(null=True, blank=True)
    campaign_fieldrep_password_hash = models.CharField(max_length=128, null=True, blank=True)
    campaign_fieldrep_created_at = models.DateTimeField(null=True, blank=True)
    campaign_fieldrep_updated_at = models.DateTimeField(null=True, blank=True)
    campaign_fieldrep_brand_id = models.CharField(max_length=255, null=True, blank=True)
    campaign_fieldrep_user_id = models.CharField(max_length=255, null=True, blank=True)
    campaign_fieldrep_state = models.CharField(max_length=255, null=True, blank=True)

    user_management_user_id = models.CharField(max_length=255, null=True, blank=True)
    user_management_username = models.CharField(max_length=150, null=True, blank=True)
    user_management_first_name = models.CharField(max_length=150, null=True, blank=True)
    user_management_last_name = models.CharField(max_length=150, null=True, blank=True)
    user_management_email = models.EmailField(max_length=254, null=True, blank=True)
    user_management_role = models.CharField(max_length=20, null=True, blank=True)
    user_management_field_id = models.CharField(max_length=50, null=True, blank=True)
    user_management_phone_number = models.CharField(max_length=15, null=True, blank=True)
    user_management_active = models.BooleanField(null=True, blank=True)
    user_management_is_active = models.BooleanField(null=True, blank=True)
    user_management_date_joined = models.DateTimeField(null=True, blank=True)

    auth_user_id = models.CharField(max_length=255, null=True, blank=True)
    auth_user_username = models.CharField(max_length=150, null=True, blank=True)
    auth_user_first_name = models.CharField(max_length=150, null=True, blank=True)
    auth_user_last_name = models.CharField(max_length=150, null=True, blank=True)
    auth_user_email = models.EmailField(max_length=254, null=True, blank=True)
    auth_user_is_active = models.BooleanField(null=True, blank=True)
    auth_user_date_joined = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "inclinic_field_rep_identity_v2"
        indexes = [
            models.Index(fields=["source_table", "source_column", "source_value"]),
            models.Index(fields=["campaign_fieldrep_id", "brand_supplied_field_rep_id"]),
        ]


class InclinicCampaignFieldRepAssignmentV2(CommonSourceFields):
    assignment_uuid = models.CharField(max_length=64, primary_key=True, default=uuid_hex)
    campaign_uuid = models.CharField(max_length=64)
    legacy_campaign_id = models.CharField(max_length=255, db_index=True)
    legacy_campaign_id_normalized = models.CharField(max_length=255, db_index=True)
    field_rep_uuid = models.CharField(max_length=64, db_index=True)
    campaign_fieldrep_id = models.CharField(max_length=255, db_index=True)
    brand_supplied_field_rep_id = models.CharField(max_length=255, null=True, blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    assigned_from = models.DateTimeField(null=True, blank=True)
    assigned_to = models.DateTimeField(null=True, blank=True)
    assignment_status = models.CharField(max_length=30, default="active")
    is_authoritative = models.BooleanField(default=True)

    old_state = models.CharField(max_length=255, null=True, blank=True)
    old_id = models.CharField(max_length=255, null=True, blank=True)
    old_field_rep_id = models.CharField(max_length=255, null=True, blank=True)
    old_created_at = models.DateTimeField(null=True, blank=True)
    old_campaign_id = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "inclinic_campaign_field_rep_assignment_v2"
        indexes = [
            models.Index(fields=["legacy_campaign_id_normalized", "campaign_fieldrep_id"]),
            models.Index(fields=["campaign_uuid", "field_rep_uuid"]),
        ]


class InclinicNonAuthoritativeAssignmentAuditV2(CommonSourceFields):
    audit_uuid = models.CharField(max_length=64, primary_key=True, default=uuid_hex)
    resolved_campaign_uuid = models.CharField(max_length=64, null=True, blank=True)
    resolved_field_rep_uuid = models.CharField(max_length=64, null=True, blank=True)
    matches_authoritative_campaign_campaignfieldrep = models.BooleanField(default=False)

    campaign_assignment_id = models.CharField(max_length=255, null=True, blank=True)
    campaign_assignment_assigned_on = models.DateTimeField(null=True, blank=True)
    campaign_assignment_campaign_id = models.CharField(max_length=255, null=True, blank=True)
    campaign_assignment_field_rep_id = models.CharField(max_length=255, null=True, blank=True)

    admin_fieldrepcampaign_id = models.CharField(max_length=255, null=True, blank=True)
    admin_fieldrepcampaign_assigned_at = models.DateTimeField(null=True, blank=True)
    admin_fieldrepcampaign_campaign_id = models.CharField(max_length=255, null=True, blank=True)
    admin_fieldrepcampaign_field_rep_id = models.CharField(max_length=255, null=True, blank=True)
    admin_fieldrepcampaign_uid = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "inclinic_non_authoritative_assignment_audit_v2"
        indexes = [models.Index(fields=["source_table", "source_pk_value"])]


class InclinicLegacyDoctorRepAliasV2(CommonSourceFields):
    legacy_alias_uuid = models.CharField(max_length=64, primary_key=True, default=uuid_hex)
    campaign_uuid = models.CharField(max_length=64, db_index=True)
    legacy_campaign_id = models.CharField(max_length=255, db_index=True)
    brand_supplied_field_rep_id = models.CharField(max_length=255, db_index=True)
    field_rep_name = models.CharField(max_length=255)
    campaign_fieldrep_id = models.CharField(max_length=255, db_index=True)
    field_rep_uuid = models.CharField(max_length=64, db_index=True)
    legacy_table = models.CharField(max_length=120, default="doctor_viewer_doctor")
    legacy_column = models.CharField(max_length=120, default="rep_id")
    legacy_value = models.CharField(max_length=255, db_index=True)
    usage_scope = models.CharField(max_length=80, default="assigned_doctor_denominator_only")
    mapping_source = models.CharField(max_length=120, default="InclinicMapping1/InclinicMapping2")

    class Meta:
        db_table = "inclinic_legacy_doctor_rep_alias_v2"
        indexes = [
            models.Index(fields=["legacy_campaign_id", "brand_supplied_field_rep_id"]),
            models.Index(fields=["legacy_table", "legacy_column", "legacy_value"]),
        ]


class InclinicDoctorV2(CommonSourceFields):
    inclinic_doctor_uuid = models.CharField(max_length=64, primary_key=True, default=uuid_hex)
    doctor_uuid = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    display_name = models.CharField(max_length=255, null=True, blank=True)
    name_normalized = models.CharField(max_length=255, null=True, blank=True)
    phone_raw = models.CharField(max_length=50, null=True, blank=True)
    phone_normalized = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    legacy_doctor_viewer_rep_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    legacy_rep_alias_uuid = models.CharField(max_length=64, null=True, blank=True)
    legacy_rep_alias_matched = models.BooleanField(default=False)

    old_id = models.CharField(max_length=255, null=True, blank=True)
    old_name = models.CharField(max_length=100, null=True, blank=True)
    old_phone = models.CharField(max_length=15, null=True, blank=True)
    old_rep_id = models.CharField(max_length=255, null=True, blank=True)
    old_source = models.CharField(max_length=10, null=True, blank=True)

    class Meta:
        db_table = "inclinic_doctor_v2"
        indexes = [
            models.Index(fields=["phone_normalized"]),
            models.Index(fields=["legacy_doctor_viewer_rep_id", "phone_normalized"]),
        ]


class InclinicManualRepDoctorCorrectionStagingV2(CommonSourceFields):
    staging_uuid = models.CharField(max_length=64, primary_key=True, default=uuid_hex)
    legacy_campaign_id = models.CharField(max_length=255, db_index=True)
    brand_supplied_field_rep_id = models.CharField(max_length=255, db_index=True)
    field_rep_name_raw = models.CharField(max_length=255, null=True, blank=True)
    doctor_name_raw = models.CharField(max_length=255, null=True, blank=True)
    doctor_phone_raw = models.CharField(max_length=50, null=True, blank=True)
    doctor_name_normalized = models.CharField(max_length=255, null=True, blank=True)
    doctor_phone_normalized = models.CharField(max_length=20, null=True, blank=True)
    parse_status = models.CharField(max_length=30, default="parsed")
    parse_notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "inclinic_manual_rep_doctor_correction_staging_v2"
        indexes = [models.Index(fields=["legacy_campaign_id", "brand_supplied_field_rep_id"])]


class InclinicAssignedDoctorRosterV2(CommonSourceFields):
    assigned_roster_uuid = models.CharField(max_length=64, primary_key=True, default=uuid_hex)
    campaign_uuid = models.CharField(max_length=64, db_index=True)
    legacy_campaign_id = models.CharField(max_length=255, db_index=True)
    brand_supplied_field_rep_id = models.CharField(max_length=255, db_index=True)
    campaign_fieldrep_id = models.CharField(max_length=255, db_index=True)
    field_rep_uuid = models.CharField(max_length=64, db_index=True)
    doctor_uuid = models.CharField(max_length=64, null=True, blank=True)
    inclinic_doctor_uuid = models.CharField(max_length=64, null=True, blank=True)
    doctor_name_raw = models.CharField(max_length=255)
    doctor_name_normalized = models.CharField(max_length=255)
    doctor_phone_raw = models.CharField(max_length=50)
    doctor_phone_normalized = models.CharField(max_length=20, db_index=True)
    legacy_doctor_viewer_rep_id = models.CharField(max_length=255, null=True, blank=True)
    match_basis = models.CharField(max_length=100)
    match_status = models.CharField(max_length=30)
    assignment_status = models.CharField(max_length=30, default="active")

    class Meta:
        db_table = "inclinic_assigned_doctor_roster_v2"
        indexes = [
            models.Index(fields=["campaign_uuid", "field_rep_uuid", "doctor_phone_normalized"]),
            models.Index(fields=["legacy_campaign_id", "brand_supplied_field_rep_id"]),
        ]


class InclinicShareEventV2(CommonSourceFields):
    share_event_uuid = models.CharField(max_length=64, primary_key=True, default=uuid_hex)
    campaign_uuid = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    legacy_campaign_id = models.CharField(max_length=255, null=True, blank=True)
    collateral_uuid = models.CharField(max_length=64, null=True, blank=True)
    doctor_uuid = models.CharField(max_length=64, null=True, blank=True)
    inclinic_doctor_uuid = models.CharField(max_length=64, null=True, blank=True)
    doctor_phone_normalized = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    shared_by_field_rep_uuid = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    campaign_fieldrep_id = models.CharField(max_length=255, null=True, blank=True)
    field_rep_email_normalized = models.EmailField(max_length=254, null=True, blank=True)
    field_rep_email_matches_campaign_fieldrep = models.BooleanField(null=True, blank=True)
    share_channel_normalized = models.CharField(max_length=30, null=True, blank=True)
    shared_at = models.DateTimeField(null=True, blank=True)

    old_id = models.CharField(max_length=255, null=True, blank=True)
    old_share_channel = models.CharField(max_length=32, null=True, blank=True)
    old_share_timestamp = models.DateTimeField(null=True, blank=True)
    old_message_text = models.TextField(null=True, blank=True)
    old_created_at = models.DateTimeField(null=True, blank=True)
    old_updated_at = models.DateTimeField(null=True, blank=True)
    old_short_link_id = models.CharField(max_length=255, null=True, blank=True)
    old_collateral_id = models.CharField(max_length=255, null=True, blank=True)
    old_doctor_identifier = models.CharField(max_length=255, null=True, blank=True)
    old_brand_campaign_id = models.CharField(max_length=255, null=True, blank=True)
    old_field_rep_email = models.EmailField(max_length=254, null=True, blank=True)
    old_field_rep_id = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "inclinic_share_event_v2"
        indexes = [
            models.Index(fields=["campaign_uuid", "shared_by_field_rep_uuid"]),
            models.Index(fields=["doctor_phone_normalized", "old_collateral_id"]),
        ]


class InclinicCollateralTransactionV2(CommonSourceFields):
    transaction_uuid = models.CharField(max_length=64, primary_key=True, default=uuid_hex)
    campaign_uuid = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    legacy_campaign_id = models.CharField(max_length=255, null=True, blank=True)
    collateral_uuid = models.CharField(max_length=64, null=True, blank=True)
    doctor_uuid = models.CharField(max_length=64, null=True, blank=True)
    inclinic_doctor_uuid = models.CharField(max_length=64, null=True, blank=True)
    doctor_phone_normalized = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    field_rep_uuid_from_campaign_fieldrep_id = models.CharField(max_length=64, null=True, blank=True)
    field_rep_uuid_from_brand_supplied_id = models.CharField(max_length=64, null=True, blank=True)
    resolved_field_rep_uuid = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    campaign_fieldrep_id = models.CharField(max_length=255, null=True, blank=True)
    brand_supplied_field_rep_id = models.CharField(max_length=255, null=True, blank=True)
    field_rep_identifier_consistency_status = models.CharField(max_length=40, default="missing")
    field_rep_resolution_basis = models.CharField(max_length=100)
    activity_summary_status = models.CharField(max_length=30)

    old_id = models.CharField(max_length=255, null=True, blank=True)
    old_transaction_id = models.CharField(max_length=128, null=True, blank=True)
    old_brand_campaign_id = models.CharField(max_length=255, null=True, blank=True)
    old_field_rep_id = models.CharField(max_length=64, null=True, blank=True)
    old_field_rep_unique_id = models.CharField(max_length=64, null=True, blank=True)
    old_doctor_name = models.CharField(max_length=255, null=True, blank=True)
    old_doctor_number = models.CharField(max_length=64, null=True, blank=True)
    old_doctor_unique_id = models.CharField(max_length=64, null=True, blank=True)
    old_collateral_id = models.CharField(max_length=255, null=True, blank=True)
    old_transaction_date = models.DateTimeField(null=True, blank=True)
    old_has_viewed = models.BooleanField(null=True, blank=True)
    old_downloaded_pdf = models.BooleanField(null=True, blank=True)
    old_pdf_completed = models.BooleanField(null=True, blank=True)
    old_video_view_lt_50 = models.IntegerField(null=True, blank=True)
    old_video_view_gt_50 = models.BooleanField(null=True, blank=True)
    old_video_completed = models.BooleanField(null=True, blank=True)
    old_pdf_total_pages = models.PositiveIntegerField(null=True, blank=True)
    old_last_video_percentage = models.PositiveIntegerField(null=True, blank=True)
    old_pdf_last_page = models.PositiveIntegerField(null=True, blank=True)
    old_doctor_viewer_engagement_id = models.CharField(max_length=255, null=True, blank=True)
    old_share_management_engagement_id = models.CharField(max_length=255, null=True, blank=True)
    old_video_tracking_last_event_id = models.CharField(max_length=255, null=True, blank=True)
    old_created_at = models.DateTimeField(null=True, blank=True)
    old_updated_at = models.DateTimeField(null=True, blank=True)
    old_sent_at = models.DateTimeField(null=True, blank=True)
    old_viewed_at = models.DateTimeField(null=True, blank=True)
    old_first_viewed_at = models.DateTimeField(null=True, blank=True)
    old_viewed_last_page_at = models.DateTimeField(null=True, blank=True)
    old_video_lt_50_at = models.DateTimeField(null=True, blank=True)
    old_video_gt_50_at = models.DateTimeField(null=True, blank=True)
    old_video_100_at = models.DateTimeField(null=True, blank=True)
    old_last_viewed_at = models.DateTimeField(null=True, blank=True)
    old_dv_engagement_id = models.CharField(max_length=255, null=True, blank=True)
    old_field_rep_email = models.EmailField(max_length=254, null=True, blank=True)
    old_share_channel = models.CharField(max_length=32, null=True, blank=True)
    old_sm_engagement_id = models.CharField(max_length=64, null=True, blank=True)
    old_video_watch_percentage = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "inclinic_collateral_transaction_v2"
        indexes = [
            models.Index(fields=["campaign_uuid", "resolved_field_rep_uuid"]),
            models.Index(fields=["doctor_phone_normalized", "old_collateral_id"]),
            models.Index(fields=["field_rep_identifier_consistency_status"]),
        ]


class InclinicDoctorActivityEventV2(CommonSourceFields):
    activity_event_uuid = models.CharField(max_length=64, primary_key=True, default=uuid_hex)
    transaction_uuid = models.CharField(max_length=64, db_index=True)
    share_event_uuid = models.CharField(max_length=64, null=True, blank=True)
    doctor_uuid = models.CharField(max_length=64, null=True, blank=True)
    inclinic_doctor_uuid = models.CharField(max_length=64, null=True, blank=True)
    campaign_uuid = models.CharField(max_length=64, null=True, blank=True)
    collateral_uuid = models.CharField(max_length=64, null=True, blank=True)
    field_rep_uuid_for_activity = models.CharField(max_length=64, null=True, blank=True)
    activity_type = models.CharField(max_length=40, db_index=True)
    activity_at = models.DateTimeField(null=True, blank=True)
    activity_value = models.CharField(max_length=255, null=True, blank=True)
    source_flag_column = models.CharField(max_length=120)

    class Meta:
        db_table = "inclinic_doctor_activity_event_v2"
        indexes = [
            models.Index(fields=["campaign_uuid", "field_rep_uuid_for_activity", "activity_type"]),
            models.Index(fields=["doctor_uuid", "activity_type"]),
        ]


class InclinicCollateralV2(CommonSourceFields):
    collateral_uuid = models.CharField(max_length=64, primary_key=True, default=uuid_hex)
    campaign_uuid = models.CharField(max_length=64, null=True, blank=True)
    content_type_normalized = models.CharField(max_length=40, null=True, blank=True)
    status = models.CharField(max_length=30, null=True, blank=True)

    old_id = models.CharField(max_length=255, null=True, blank=True)
    old_type = models.CharField(max_length=10, null=True, blank=True)
    old_title = models.CharField(max_length=255, null=True, blank=True)
    old_file = models.CharField(max_length=255, null=True, blank=True)
    old_vimeo_url = models.CharField(max_length=255, null=True, blank=True)
    old_content_id = models.CharField(max_length=100, null=True, blank=True)
    old_upload_date = models.DateTimeField(null=True, blank=True)
    old_is_active = models.BooleanField(null=True, blank=True)
    old_created_at = models.DateTimeField(null=True, blank=True)
    old_updated_at = models.DateTimeField(null=True, blank=True)
    old_banner_1 = models.CharField(max_length=255, null=True, blank=True)
    old_banner_2 = models.CharField(max_length=255, null=True, blank=True)
    old_campaign_id = models.CharField(max_length=255, null=True, blank=True)
    old_created_by_id = models.CharField(max_length=255, null=True, blank=True)
    old_description = models.CharField(max_length=255, null=True, blank=True)
    old_purpose = models.CharField(max_length=50, null=True, blank=True)
    old_doctor_name = models.CharField(max_length=255, null=True, blank=True)
    old_webinar_date = models.DateField(null=True, blank=True)
    old_webinar_description = models.TextField(null=True, blank=True)
    old_webinar_title = models.CharField(max_length=255, null=True, blank=True)
    old_webinar_url = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "inclinic_collateral_v2"
        indexes = [models.Index(fields=["old_id"])]


class InclinicCampaignCollateralV2(CommonSourceFields):
    campaign_collateral_uuid = models.CharField(max_length=64, primary_key=True, default=uuid_hex)
    campaign_uuid = models.CharField(max_length=64, null=True, blank=True)
    collateral_uuid = models.CharField(max_length=64)

    old_id = models.CharField(max_length=255, null=True, blank=True)
    old_start_date = models.DateTimeField(null=True, blank=True)
    old_end_date = models.DateTimeField(null=True, blank=True)
    old_created_at = models.DateTimeField(null=True, blank=True)
    old_updated_at = models.DateTimeField(null=True, blank=True)
    old_campaign_id = models.CharField(max_length=255, null=True, blank=True)
    old_collateral_id = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "inclinic_campaign_collateral_v2"
        indexes = [
            models.Index(fields=["campaign_uuid", "collateral_uuid"]),
            models.Index(fields=["old_campaign_id", "old_collateral_id"]),
        ]
