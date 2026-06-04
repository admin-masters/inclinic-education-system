from __future__ import annotations

import uuid
from datetime import date
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
RUNTIME_SHARE_TABLE = "runtime_share_event"
RUNTIME_TRANSACTION_TABLE = "runtime_collateral_transaction"


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


def _runtime_uuid() -> str:
    return uuid.uuid4().hex


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


def _runtime_common(table: str, row: dict[str, Any], batch_id: str, basis: str, status: str = "verified"):
    now = timezone.now()
    row = {
        "id": clean_text(row.get("id")) or _runtime_uuid(),
        "created_at": row.get("created_at") or now,
        "updated_at": row.get("updated_at") or now,
        **row,
    }
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


def _build_transaction_id(values: dict[str, Any]) -> str:
    sent_at = values.get("sent_at") or timezone.now()
    if timezone.is_naive(sent_at):
        sent_at = timezone.make_aware(sent_at, timezone.get_current_timezone())
    try:
        sent_at = timezone.localtime(sent_at)
    except Exception:
        pass

    field_part = clean_text(values.get("field_rep_unique_id")) or clean_text(values.get("field_rep_id")) or "unknown"
    doctor_part = clean_text(values.get("doctor_number")) or "unknown"
    collateral_part = clean_text(values.get("collateral_id")) or "unknown"
    timestamp_part = sent_at.strftime("%Y%m%d%H%M%S")
    return f"{field_part}-{doctor_part}-{collateral_part}-{timestamp_part}"[:128]


def _date_value(value):
    if isinstance(value, date):
        return value
    if value:
        try:
            if timezone.is_naive(value):
                value = timezone.make_aware(value, timezone.get_current_timezone())
            return timezone.localdate(value)
        except Exception:
            pass
    return timezone.localdate()


def _share_event_payload(row: dict[str, Any], batch_id: str, basis: str, source_table: str):
    field_rep_id = clean_text(row.get("field_rep_id"))
    field_rep = _master_field_rep(field_rep_id)
    field_rep_email = normalize_email(row.get("field_rep_email"))
    auth_email = normalize_email(getattr(getattr(field_rep, "user", None), "email", "")) if field_rep else ""
    email_matches = field_rep_email == auth_email if field_rep_email and auth_email else None
    phone_norm = normalize_phone(row.get("doctor_identifier"))

    return {
        **_runtime_common(
            source_table,
            row,
            batch_id,
            basis,
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
    }


def _transaction_resolution(row: dict[str, Any]):
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

    return field_rep, brand_field_rep, resolved_uuid, brand_supplied_id, consistency_status, basis


def _transaction_payload(row: dict[str, Any], batch_id: str, basis_prefix: str, source_table: str):
    field_rep_id = clean_text(row.get("field_rep_id"))
    raw_unique_id = clean_text(row.get("field_rep_unique_id"))
    field_rep, brand_field_rep, resolved_uuid, brand_supplied_id, consistency_status, basis = _transaction_resolution(row)
    phone_norm = normalize_phone(row.get("doctor_number"))
    activity_status = "viewed" if _viewed_after_current_send(row) else "sent"

    return {
        **_runtime_common(
            source_table,
            row,
            batch_id,
            f"{basis_prefix}_{basis}",
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
        "old_first_viewed_at": row.get("first_viewed_at") or row.get("viewed_at"),
        "old_viewed_last_page_at": row.get("viewed_last_page_at"),
        "old_video_lt_50_at": row.get("video_lt_50_at"),
        "old_video_gt_50_at": row.get("video_gt_50_at"),
        "old_video_100_at": row.get("video_100_at"),
        "old_last_viewed_at": row.get("last_viewed_at") or row.get("viewed_at"),
        "old_dv_engagement_id": clean_text(row.get("doctor_viewer_engagement_id")),
        "old_field_rep_email": clean_text(row.get("field_rep_email")) or (
            clean_text(getattr(getattr(field_rep, "user", None), "email", "")) if field_rep else None
        ),
        "old_share_channel": clean_text(row.get("share_channel")),
        "old_sm_engagement_id": clean_text(row.get("share_management_engagement_id")),
        "old_video_watch_percentage": parse_int(row.get("last_video_percentage")),
    }


def create_direct_share_tracking_v2(
    *,
    short_link_id: Any,
    collateral_id: Any,
    field_rep_id: Any,
    field_rep_email: Any = "",
    doctor_identifier: Any,
    share_channel: str = "WhatsApp",
    share_timestamp=None,
    message_text: str = "",
    brand_campaign_id: Any = "",
    doctor_name: Any = "",
    field_rep_unique_id: Any = "",
    share_event_uuid: str | None = None,
) -> tuple[str | None, str | None]:
    batch_id = _active_batch_id()
    if not batch_id:
        return None, None

    now = timezone.now()
    sent_at = share_timestamp or now
    share_uuid = clean_text(share_event_uuid) or _runtime_uuid()
    transaction_uuid = stable_uuid("runtime_collateral_transaction", share_uuid)
    phone = clean_text(doctor_identifier)

    share_row = {
        "id": share_uuid,
        "short_link_id": clean_text(short_link_id),
        "collateral_id": clean_text(collateral_id),
        "field_rep_id": clean_text(field_rep_id),
        "field_rep_email": clean_text(field_rep_email),
        "doctor_identifier": phone,
        "share_channel": share_channel,
        "share_timestamp": sent_at,
        "message_text": clean_text(message_text),
        "brand_campaign_id": clean_text(brand_campaign_id),
        "created_at": sent_at,
        "updated_at": now,
    }

    tx_row = {
        "id": transaction_uuid,
        "transaction_id": _build_transaction_id(
            {
                "field_rep_unique_id": field_rep_unique_id,
                "field_rep_id": field_rep_id,
                "doctor_number": phone,
                "collateral_id": collateral_id,
                "sent_at": sent_at,
            }
        ),
        "brand_campaign_id": clean_text(brand_campaign_id),
        "field_rep_id": clean_text(field_rep_id),
        "field_rep_unique_id": clean_text(field_rep_unique_id),
        "doctor_name": clean_text(doctor_name),
        "doctor_number": phone,
        "doctor_unique_id": "",
        "collateral_id": clean_text(collateral_id),
        "transaction_date": _date_value(sent_at),
        "has_viewed": False,
        "has_downloaded_pdf": False,
        "has_viewed_last_page": False,
        "video_view_lt_50": False,
        "video_view_gt_50": False,
        "video_view_100": False,
        "total_video_events": 0,
        "last_video_percentage": 0,
        "last_page_scrolled": 0,
        "doctor_viewer_engagement_id": "",
        "share_management_engagement_id": share_uuid,
        "video_tracking_last_event_id": "",
        "sent_at": sent_at,
        "viewed_at": None,
        "downloaded_pdf_at": None,
        "viewed_last_page_at": None,
        "video_lt_50_at": None,
        "video_gt_50_at": None,
        "video_100_at": None,
        "last_video_event_at": None,
        "created_at": sent_at,
        "updated_at": now,
        "field_rep_email": clean_text(field_rep_email),
        "share_channel": share_channel,
    }

    try:
        update_by_pk(
            InclinicShareEventV2,
            share_uuid,
            _share_event_payload(
                share_row,
                batch_id,
                "runtime_v2_direct_share",
                RUNTIME_SHARE_TABLE,
            ),
        )
        update_by_pk(
            InclinicCollateralTransactionV2,
            transaction_uuid,
            _transaction_payload(
                tx_row,
                batch_id,
                "runtime_v2_direct",
                RUNTIME_TRANSACTION_TABLE,
            ),
        )
        return share_uuid, transaction_uuid
    except Exception as exc:
        print("[V2SYNC] direct share tracking sync failed:", exc)
        return None, None


def get_v2_share_event(share_id: Any):
    value = clean_text(share_id)
    if not value:
        return None
    try:
        return InclinicShareEventV2.objects.filter(share_event_uuid=value).first()
    except Exception:
        return None


def matching_v2_share_id_for_phone(short_link_id: Any, whatsapp_number: str | None) -> str | None:
    phone_norm = normalize_phone(whatsapp_number)
    if not phone_norm:
        return None
    try:
        row = (
            InclinicShareEventV2.objects.filter(
                old_short_link_id=clean_text(short_link_id),
                doctor_phone_normalized=phone_norm,
                is_current=True,
            )
            .order_by("-shared_at", "-migrated_at")
            .values("share_event_uuid")
            .first()
        )
        return row["share_event_uuid"] if row else None
    except Exception as exc:
        print("[V2SYNC] matching v2 share lookup failed:", exc)
        return None


def latest_v2_share_status(*, collateral_id: Any, doctor_identifier: Any, field_rep_ids: list[int] | None = None):
    phone_norm = normalize_phone(doctor_identifier)
    if not phone_norm:
        return None
    qs = InclinicShareEventV2.objects.filter(
        old_collateral_id=clean_text(collateral_id),
        doctor_phone_normalized=phone_norm,
        is_current=True,
    )
    if field_rep_ids:
        qs = qs.filter(campaign_fieldrep_id__in=[clean_text(value) for value in field_rep_ids])
    runtime_share = qs.filter(source_table=RUNTIME_SHARE_TABLE).order_by("-shared_at", "-migrated_at").first()
    share = runtime_share or qs.order_by("-shared_at", "-migrated_at").first()
    if not share:
        return None
    tx = (
        InclinicCollateralTransactionV2.objects.filter(
            old_share_management_engagement_id=share.share_event_uuid,
            is_current=True,
        )
        .order_by("-migrated_at")
        .first()
    )
    opened = False
    viewed_at = getattr(tx, "old_viewed_at", None) if tx else None
    if tx and tx.activity_summary_status == "viewed":
        opened = bool(not share.shared_at or (viewed_at and viewed_at >= share.shared_at))
    return {
        "share_id": share.share_event_uuid,
        "shared_at": share.shared_at,
        "opened": opened,
        "doctor_identifier": share.old_doctor_identifier,
        "source_table": share.source_table,
        "is_runtime": share.source_table == RUNTIME_SHARE_TABLE,
    }


def mark_v2_tracking_event(
    share_id: Any,
    *,
    event: str = "viewed",
    last_page: int = 0,
    completed: bool = False,
    dv_engagement_id: Any = None,
    total_pages: int = 0,
    percentage: int | None = None,
    when=None,
) -> bool:
    share = get_v2_share_event(share_id)
    if not share:
        return False

    now = when or timezone.now()
    tx = (
        InclinicCollateralTransactionV2.objects.filter(
            old_share_management_engagement_id=share.share_event_uuid,
            is_current=True,
        )
        .order_by("-migrated_at")
        .first()
    )
    if not tx:
        _share_collateral_id = share.old_collateral_id or ""
        _, transaction_uuid = create_direct_share_tracking_v2(
            short_link_id=share.old_short_link_id,
            collateral_id=_share_collateral_id,
            field_rep_id=share.campaign_fieldrep_id,
            field_rep_email=share.old_field_rep_email or "",
            doctor_identifier=share.old_doctor_identifier,
            share_channel=share.old_share_channel or "WhatsApp",
            share_timestamp=share.shared_at or now,
            message_text=share.old_message_text or "",
            brand_campaign_id=share.old_brand_campaign_id or "",
            field_rep_unique_id="",
            share_event_uuid=share.share_event_uuid,
        )
        tx = InclinicCollateralTransactionV2.objects.filter(transaction_uuid=transaction_uuid).first()
    if not tx:
        return False

    updates = {
        "activity_summary_status": "viewed",
        "old_has_viewed": True,
        "old_last_viewed_at": now,
        "source_updated_at": now,
        "migrated_at": now,
        "old_updated_at": now,
    }
    if not tx.old_viewed_at or (share.shared_at and tx.old_viewed_at < share.shared_at):
        updates["old_viewed_at"] = now
        updates["old_first_viewed_at"] = now
    if dv_engagement_id not in (None, ""):
        updates["old_doctor_viewer_engagement_id"] = clean_text(dv_engagement_id)
        updates["old_dv_engagement_id"] = clean_text(dv_engagement_id)

    try:
        page_i = int(last_page or 0)
    except Exception:
        page_i = 0
    if page_i > 0:
        updates["old_pdf_last_page"] = max(int(tx.old_pdf_last_page or 0), page_i)

    if completed or event == "pdf_download":
        updates["old_downloaded_pdf"] = True
        updates["old_pdf_completed"] = True
        updates["old_viewed_last_page_at"] = tx.old_viewed_last_page_at or now

    if event == "video_progress":
        try:
            pct = int(percentage or 0)
        except Exception:
            pct = 0
        pct = max(0, min(100, pct))
        updates["old_last_video_percentage"] = max(int(tx.old_last_video_percentage or 0), pct)
        updates["old_video_watch_percentage"] = updates["old_last_video_percentage"]
        if 0 < pct < 50:
            updates["old_video_view_lt_50"] = 1
            updates["old_video_lt_50_at"] = tx.old_video_lt_50_at or now
        if 50 <= pct < 100:
            updates["old_video_view_gt_50"] = True
            updates["old_video_gt_50_at"] = tx.old_video_gt_50_at or now
        if pct >= 100:
            updates["old_video_completed"] = True
            updates["old_video_100_at"] = tx.old_video_100_at or now

    try:
        InclinicCollateralTransactionV2.objects.filter(transaction_uuid=tx.transaction_uuid).update(**updates)
        return True
    except Exception as exc:
        print("[V2SYNC] mark v2 tracking event failed:", exc)
        return False


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
