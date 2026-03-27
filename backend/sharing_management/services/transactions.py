# sharing_management/services/transactions.py
from __future__ import annotations

import uuid
from typing import Any, Optional

from django.conf import settings
from django.utils import timezone

from sharing_management.models import CollateralTransaction, ShareLog


MASTER_ALIAS = getattr(settings, "MASTER_DB_ALIAS", "master")
SNAPSHOT_FIELDS = (
    "field_rep_id",
    "field_rep_email",
    "doctor_number",
    "doctor_name",
    "collateral_id",
    "brand_campaign_id",
    "share_channel",
    "sent_at",
    "has_viewed",
    "first_viewed_at",
    "last_viewed_at",
    "pdf_last_page",
    "pdf_total_pages",
    "pdf_completed",
    "downloaded_pdf",
    "video_watch_percentage",
    "video_completed",
    "dv_engagement_id",
    "sm_engagement_id",
)


def _as_str(v: Any) -> str:
    """
    Always return a safe string.
    - UUID -> str(UUID)
    - None -> ""
    """
    if v is None:
        return ""
    if isinstance(v, uuid.UUID):
        return str(v)
    return str(v)


def _resolve_collateral_id(share_log: ShareLog) -> Optional[int]:
    """
    Prefer ShareLog.collateral_id. Fallback to ShortLink.resource_id when needed.
    """
    try:
        if getattr(share_log, "collateral_id", None):
            return int(share_log.collateral_id)
    except Exception:
        pass

    try:
        sl = getattr(share_log, "short_link", None)
        if sl and getattr(sl, "resource_type", "") == "collateral":
            rid = getattr(sl, "resource_id", None)
            if rid is not None:
                return int(rid)
    except Exception:
        pass

    return None


def _maybe_backfill_field_rep_id(share_log: ShareLog) -> None:
    """
    If ShareLog.field_rep_id is missing, try to backfill from master DB using field_rep_email.
    This is best-effort and should never crash tracking.
    """
    if getattr(share_log, "field_rep_id", None):
        return

    email = _as_str(getattr(share_log, "field_rep_email", "")).strip()
    if not email:
        return

    try:
        from campaign_management.master_models import MasterAuthUser, MasterFieldRep

        au = (
            MasterAuthUser.objects.using(MASTER_ALIAS)
            .filter(email__iexact=email)
            .first()
        )
        if not au:
            return

        fr = (
            MasterFieldRep.objects.using(MASTER_ALIAS)
            .filter(user=au)
            .first()
        )
        if not fr:
            return

        share_log.field_rep_id = int(fr.id)
        share_log.save(update_fields=["field_rep_id"])
        print(
            "[TXDBG] backfilled ShareLog.field_rep_id=",
            share_log.field_rep_id,
            " share_log.id=",
            share_log.id,
        )
    except Exception as e:
        print("[TXDBG] backfill field_rep_id failed:", e)


def _base_transaction_values(
    share_log: ShareLog,
    brand_campaign_id: Any = "",
    doctor_name: Optional[str] = None,
    sent_at=None,
) -> Optional[dict[str, Any]]:
    if not share_log:
        return None

    _maybe_backfill_field_rep_id(share_log)

    field_rep_id = getattr(share_log, "field_rep_id", None)
    if field_rep_id is None:
        # IMPORTANT: avoid "Field expected a number but got None"
        print("[TXDBG] ShareLog.field_rep_id is None; skipping transaction upsert. share_log.id=", getattr(share_log, "id", None))
        return None

    bc_raw = brand_campaign_id if brand_campaign_id else getattr(share_log, "brand_campaign_id", "")
    bc_id = _as_str(bc_raw).strip()
    doctor_number = _as_str(getattr(share_log, "doctor_identifier", "")).strip()
    collateral_id = _resolve_collateral_id(share_log)

    values = {
        "field_rep_id": int(field_rep_id),
        "field_rep_email": _as_str(getattr(share_log, "field_rep_email", "")).strip(),
        "brand_campaign_id": bc_id,
        "doctor_number": doctor_number,
        "doctor_name": _as_str(doctor_name).strip() if doctor_name else "",
        "share_channel": _as_str(getattr(share_log, "share_channel", "")).strip(),
        "sent_at": sent_at or getattr(share_log, "share_timestamp", None) or timezone.now(),
        "sm_engagement_id": _as_str(getattr(share_log, "id", "")).strip(),
    }
    if collateral_id is not None:
        values["collateral_id"] = int(collateral_id)

    return values


def _latest_transaction(base_values: dict[str, Any]) -> Optional[CollateralTransaction]:
    queryset = CollateralTransaction.objects.filter(sm_engagement_id=base_values["sm_engagement_id"])

    if base_values.get("field_rep_id") is not None:
        queryset = queryset.filter(field_rep_id=base_values["field_rep_id"])
    if base_values.get("doctor_number"):
        queryset = queryset.filter(doctor_number=base_values["doctor_number"])
    if "collateral_id" in base_values:
        queryset = queryset.filter(collateral_id=base_values["collateral_id"])

    return queryset.order_by("-updated_at", "-id").first()


def _merged_snapshot_values(base_values: dict[str, Any]) -> dict[str, Any]:
    latest = _latest_transaction(base_values)
    snapshot_values: dict[str, Any] = {}

    if latest:
        for field_name in SNAPSHOT_FIELDS:
            snapshot_values[field_name] = getattr(latest, field_name)

    for key, value in base_values.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip() and key in snapshot_values:
            continue
        snapshot_values[key] = value

    return snapshot_values


def _create_snapshot_row(snapshot_values: dict[str, Any], action_name: str) -> Optional[CollateralTransaction]:
    try:
        return CollateralTransaction.objects.create(**snapshot_values)
    except Exception as e:
        print(f"[TXDBG] {action_name} failed:", e)
        return None


def upsert_from_sharelog(
    share_log: ShareLog,
    brand_campaign_id: Any = "",
    doctor_name: Optional[str] = None,
    field_rep_unique_id: Optional[str] = None,  # kept for compatibility; not used
    sent_at=None,
):
    """
    Append one CollateralTransaction snapshot row for this ShareLog.
    Each engagement event keeps the older rows intact and inserts a fresh row.
    """
    base_values = _base_transaction_values(
        share_log=share_log,
        brand_campaign_id=brand_campaign_id,
        doctor_name=doctor_name,
        sent_at=sent_at,
    )
    if not base_values:
        return None

    snapshot_values = _merged_snapshot_values(base_values)
    return _create_snapshot_row(snapshot_values, "upsert_from_sharelog")


def mark_viewed(share_log: ShareLog, sm_engagement_id=None):
    base_values = _base_transaction_values(share_log)
    if not base_values:
        return None

    snapshot_values = _merged_snapshot_values(base_values)
    now = timezone.now()

    snapshot_values["has_viewed"] = True
    if not snapshot_values.get("first_viewed_at"):
        snapshot_values["first_viewed_at"] = now
    snapshot_values["last_viewed_at"] = now

    return _create_snapshot_row(snapshot_values, "mark_viewed")


def mark_pdf_progress(
    share_log: ShareLog,
    last_page=0,
    completed=False,
    dv_engagement_id=None,
    total_pages=0,
    sm_engagement_id=None,
):
    base_values = _base_transaction_values(share_log)
    if not base_values:
        return None

    snapshot_values = _merged_snapshot_values(base_values)
    now = timezone.now()

    try:
        last_page_i = int(last_page or 0)
    except Exception:
        last_page_i = 0
    if last_page_i < 0:
        last_page_i = 0

    try:
        total_pages_i = int(total_pages or 0)
    except Exception:
        total_pages_i = 0
    if total_pages_i < 0:
        total_pages_i = 0

    # Mark viewed as soon as we get scroll progress
    snapshot_values["has_viewed"] = True
    if not snapshot_values.get("first_viewed_at"):
        snapshot_values["first_viewed_at"] = now
    snapshot_values["last_viewed_at"] = now
    snapshot_values["pdf_last_page"] = max(int(snapshot_values.get("pdf_last_page", 0) or 0), last_page_i)

    if total_pages_i:
        snapshot_values["pdf_total_pages"] = max(
            int(snapshot_values.get("pdf_total_pages", 0) or 0),
            total_pages_i,
        )

    if completed:
        snapshot_values["pdf_completed"] = True

    if dv_engagement_id is not None:
        try:
            snapshot_values["dv_engagement_id"] = int(dv_engagement_id)
        except Exception:
            pass

    return _create_snapshot_row(snapshot_values, "mark_pdf_progress")


def mark_downloaded_pdf(share_log: ShareLog, sm_engagement_id=None):
    base_values = _base_transaction_values(share_log)
    if not base_values:
        return None

    snapshot_values = _merged_snapshot_values(base_values)
    snapshot_values["downloaded_pdf"] = True
    snapshot_values["pdf_completed"] = True

    return _create_snapshot_row(snapshot_values, "mark_downloaded_pdf")


def mark_video_event(
    share_log: ShareLog,
    status=0,        # kept for compatibility (not used)
    percentage=0,
    event_id=0,      # kept for compatibility (not used)
    when=None,
    sm_engagement_id=None,
):
    base_values = _base_transaction_values(share_log)
    if not base_values:
        return None

    snapshot_values = _merged_snapshot_values(base_values)
    try:
        pct = int(percentage or 0)
    except Exception:
        pct = 0

    pct = max(0, min(100, pct))

    snapshot_values["video_watch_percentage"] = max(
        int(snapshot_values.get("video_watch_percentage", 0) or 0),
        pct,
    )
    if snapshot_values["video_watch_percentage"] >= 90:
        snapshot_values["video_completed"] = True

    return _create_snapshot_row(snapshot_values, "mark_video_event")
