from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils import timezone

from reporting_etl.inclinic_v2 import (
    clean_text,
    common_fields,
    normalize_campaign_id,
    normalize_email,
    normalize_phone,
    parse_bool,
    parse_int,
    stable_uuid,
    update_by_pk,
)
from reporting_etl.models import InclinicCollateralTransactionV2, InclinicShareEventV2
from reporting_etl.v2_switch import get_active_v2_batch


DEFAULT_ALIAS = "default"


def _active_batch_id() -> str:
    try:
        batch = get_active_v2_batch()
        return batch.migration_batch_id if batch else ""
    except Exception:
        return ""


def _row_from_model(obj) -> dict[str, Any]:
    row = {}
    for field in obj._meta.concrete_fields:
        row[field.attname] = getattr(obj, field.attname)
    return row


def _field_rep_uuid(field_rep_id: Any) -> str | None:
    value = clean_text(field_rep_id)
    return stable_uuid("field_rep", value) if value else None


def _campaign_uuid(campaign_id: Any) -> str | None:
    value = normalize_campaign_id(campaign_id)
    return stable_uuid("campaign", value) if value else None


def _doctor_uuid(phone: Any) -> str | None:
    value = normalize_phone(phone)
    return stable_uuid("doctor", value) if value else None


def _collateral_uuid(collateral_id: Any) -> str | None:
    value = clean_text(collateral_id)
    return stable_uuid("collateral", value) if value else None


def _source_common(table: str, row: dict[str, Any], batch_id: str, basis: str, status: str = "verified"):
    return common_fields(
        alias=DEFAULT_ALIAS,
        table=table,
        row=row,
        batch_id=batch_id,
        verification_status=status,
        verification_basis=basis,
    )


def _master_field_rep(field_rep_id: Any):
    value = clean_text(field_rep_id)
    if not value:
        return None
    try:
        from campaign_management.master_models import MasterFieldRep

        return (
            MasterFieldRep.objects.using(getattr(settings, "MASTER_DB_ALIAS", "master"))
            .select_related("user")
            .filter(id=int(value))
            .first()
        )
    except Exception:
        return None


def _master_field_rep_by_brand_id(brand_supplied_field_rep_id: Any):
    value = clean_text(brand_supplied_field_rep_id)
    if not value:
        return None
    try:
        from campaign_management.master_models import MasterFieldRep

        return (
            MasterFieldRep.objects.using(getattr(settings, "MASTER_DB_ALIAS", "master"))
            .select_related("user")
            .filter(brand_supplied_field_rep_id=value)
            .first()
        )
    except Exception:
        return None


def _inclinic_doctor_uuid(phone: Any) -> str | None:
    phone_norm = normalize_phone(phone)
    if not phone_norm:
        return None
    candidates = {phone_norm, f"91{phone_norm}", f"+91{phone_norm}"}
    try:
        from doctor_viewer.models import Doctor

        doctor = Doctor.objects.filter(phone__in=candidates).order_by("-id").first()
        return stable_uuid("inclinic_doctor", doctor.id) if doctor else None
    except Exception:
        return None


def _viewed_after_current_send(row: dict[str, Any]) -> bool:
    if not parse_bool(row.get("has_viewed")) and not row.get("viewed_at"):
        return False
    viewed_at = row.get("viewed_at")
    sent_at = row.get("sent_at")
    if not viewed_at:
        return not bool(sent_at)
    if not sent_at:
        return True
    try:
        if timezone.is_naive(viewed_at):
            viewed_at = timezone.make_aware(viewed_at, timezone.get_current_timezone())
        if timezone.is_naive(sent_at):
            sent_at = timezone.make_aware(sent_at, timezone.get_current_timezone())
        return viewed_at >= sent_at
    except Exception:
        return True


def sync_sharelog_to_v2(share_log) -> None:
    batch_id = _active_batch_id()
    if not batch_id or share_log is None:
        return

    try:
        row = _row_from_model(share_log)
        field_rep_id = clean_text(row.get("field_rep_id"))
        field_rep = _master_field_rep(field_rep_id)
        field_rep_email = normalize_email(row.get("field_rep_email"))
        auth_email = normalize_email(getattr(getattr(field_rep, "user", None), "email", "")) if field_rep else ""
        email_matches = field_rep_email == auth_email if field_rep_email and auth_email else None
        phone_norm = normalize_phone(row.get("doctor_identifier"))
        pk = stable_uuid("share_event", row.get("id"))

        update_by_pk(
            InclinicShareEventV2,
            pk,
            {
                **_source_common(
                    "sharing_management_sharelog",
                    row,
                    batch_id,
                    "runtime_sharelog_dual_write",
                    "verified" if field_rep else "unresolved",
                ),
                "campaign_uuid": _campaign_uuid(row.get("brand_campaign_id")),
                "legacy_campaign_id": clean_text(row.get("brand_campaign_id")),
                "collateral_uuid": _collateral_uuid(row.get("collateral_id")),
                "doctor_uuid": _doctor_uuid(phone_norm),
                "inclinic_doctor_uuid": _inclinic_doctor_uuid(row.get("doctor_identifier")),
                "doctor_phone_normalized": phone_norm or None,
                "shared_by_field_rep_uuid": _field_rep_uuid(field_rep_id) if field_rep else None,
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
    except Exception as exc:
        print("[V2SYNC] sharelog sync failed:", exc)


def sync_collateral_transaction_to_v2(transaction) -> None:
    batch_id = _active_batch_id()
    if not batch_id or transaction is None:
        return

    try:
        row = _row_from_model(transaction)
        field_rep_id = clean_text(row.get("field_rep_id"))
        raw_unique_id = clean_text(row.get("field_rep_unique_id"))
        field_rep = _master_field_rep(field_rep_id)
        brand_supplied_id = clean_text(getattr(field_rep, "brand_supplied_field_rep_id", "")) if field_rep else raw_unique_id
        brand_field_rep = _master_field_rep_by_brand_id(raw_unique_id)
        resolved_uuid = _field_rep_uuid(field_rep_id) if field_rep else None

        if not field_rep:
            consistency_status = "missing"
            basis = "campaign_fieldrep_id_missing"
        elif (
            raw_unique_id
            and raw_unique_id not in {brand_supplied_id, field_rep_id}
            and getattr(brand_field_rep, "id", None) != getattr(field_rep, "id", None)
        ):
            consistency_status = "conflict"
            basis = "campaign_fieldrep_id_preferred_over_conflicting_brand_supplied_id"
        elif raw_unique_id:
            consistency_status = "consistent"
            basis = "campaign_fieldrep_id_and_brand_supplied_id"
        else:
            consistency_status = "consistent"
            basis = "campaign_fieldrep_id_resolved_brand_supplied_id_from_master"

        phone_norm = normalize_phone(row.get("doctor_number"))
        activity_status = "viewed" if _viewed_after_current_send(row) else "sent"
        pk = stable_uuid("collateral_transaction", row.get("id"))

        update_by_pk(
            InclinicCollateralTransactionV2,
            pk,
            {
                **_source_common(
                    "sharing_management_collateraltransaction",
                    row,
                    batch_id,
                    f"runtime_{basis}",
                    "verified" if resolved_uuid else "unresolved",
                ),
                "campaign_uuid": _campaign_uuid(row.get("brand_campaign_id")),
                "legacy_campaign_id": clean_text(row.get("brand_campaign_id")),
                "collateral_uuid": _collateral_uuid(row.get("collateral_id")),
                "doctor_uuid": _doctor_uuid(phone_norm),
                "inclinic_doctor_uuid": _inclinic_doctor_uuid(row.get("doctor_number")),
                "doctor_phone_normalized": phone_norm or None,
                "field_rep_uuid_from_campaign_fieldrep_id": _field_rep_uuid(field_rep_id) if field_rep else None,
                "field_rep_uuid_from_brand_supplied_id": _field_rep_uuid(getattr(brand_field_rep, "id", None)),
                "resolved_field_rep_uuid": resolved_uuid,
                "campaign_fieldrep_id": field_rep_id,
                "brand_supplied_field_rep_id": brand_supplied_id,
                "field_rep_identifier_consistency_status": consistency_status,
                "field_rep_resolution_basis": basis,
                "activity_summary_status": activity_status,
                "old_id": clean_text(row.get("id")),
                "old_transaction_id": clean_text(row.get("transaction_id")),
                "old_brand_campaign_id": clean_text(row.get("brand_campaign_id")),
                "old_field_rep_id": field_rep_id,
                "old_field_rep_unique_id": raw_unique_id,
                "old_doctor_name": clean_text(row.get("doctor_name")),
                "old_doctor_number": clean_text(row.get("doctor_number")),
                "old_doctor_unique_id": clean_text(row.get("doctor_unique_id")),
                "old_collateral_id": clean_text(row.get("collateral_id")),
                "old_transaction_date": row.get("transaction_date"),
                "old_has_viewed": parse_bool(row.get("has_viewed")),
                "old_downloaded_pdf": parse_bool(row.get("has_downloaded_pdf")),
                "old_pdf_completed": parse_bool(row.get("has_viewed_last_page")),
                "old_video_view_lt_50": parse_int(row.get("video_view_lt_50")),
                "old_video_view_gt_50": parse_bool(row.get("video_view_gt_50")),
                "old_video_completed": parse_bool(row.get("video_view_100")),
                "old_last_video_percentage": parse_int(row.get("last_video_percentage")),
                "old_pdf_last_page": parse_int(row.get("last_page_scrolled")),
                "old_doctor_viewer_engagement_id": clean_text(row.get("doctor_viewer_engagement_id")),
                "old_share_management_engagement_id": clean_text(row.get("share_management_engagement_id")),
                "old_video_tracking_last_event_id": clean_text(row.get("video_tracking_last_event_id")),
                "old_created_at": row.get("created_at"),
                "old_updated_at": row.get("updated_at"),
                "old_sent_at": row.get("sent_at"),
                "old_viewed_at": row.get("viewed_at"),
                "old_first_viewed_at": row.get("viewed_at"),
                "old_viewed_last_page_at": row.get("viewed_last_page_at"),
                "old_video_lt_50_at": row.get("video_lt_50_at"),
                "old_video_gt_50_at": row.get("video_gt_50_at"),
                "old_video_100_at": row.get("video_100_at"),
                "old_last_viewed_at": row.get("viewed_at"),
                "old_dv_engagement_id": clean_text(row.get("doctor_viewer_engagement_id")),
                "old_field_rep_email": clean_text(getattr(getattr(field_rep, "user", None), "email", "")) or None,
                "old_share_channel": "",
                "old_sm_engagement_id": clean_text(row.get("share_management_engagement_id")),
                "old_video_watch_percentage": parse_int(row.get("last_video_percentage")),
            },
        )
    except Exception as exc:
        print("[V2SYNC] collateral transaction sync failed:", exc)
