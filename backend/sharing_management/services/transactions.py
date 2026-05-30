# sharing_management/services/transactions.py
from __future__ import annotations

import re
import uuid
from typing import Any, Optional
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from campaign_management.campaign_ids import canonical_brand_campaign_id
from sharing_management.models import CollateralTransaction, ShareLog


MASTER_ALIAS = getattr(settings, "MASTER_DB_ALIAS", "master")
TRANSACTION_DATETIME_FORMAT = "%Y%m%d%H%M%S"
TRANSACTION_ID_TIME_ZONE = getattr(settings, "TRANSACTION_ID_TIME_ZONE", "Asia/Kolkata")

SNAPSHOT_FIELDS = (
    "transaction_id",
    "brand_campaign_id",
    "field_rep_id",
    "field_rep_unique_id",
    "doctor_name",
    "doctor_number",
    "doctor_unique_id",
    "collateral_id",
    "transaction_date",
    "has_viewed",
    "has_downloaded_pdf",
    "has_viewed_last_page",
    "video_view_lt_50",
    "video_view_gt_50",
    "video_view_100",
    "total_video_events",
    "last_video_percentage",
    "last_page_scrolled",
    "doctor_viewer_engagement_id",
    "share_management_engagement_id",
    "video_tracking_last_event_id",
    "sent_at",
    "viewed_at",
    "downloaded_pdf_at",
    "viewed_last_page_at",
    "video_lt_50_at",
    "video_gt_50_at",
    "video_100_at",
    "last_video_event_at",
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


def _as_int(v: Any) -> Optional[int]:
    try:
        if v is None or v == "":
            return None
        return int(v)
    except Exception:
        return None


def _local_dt(value=None):
    dt = value or timezone.now()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    try:
        tx_timezone = ZoneInfo(TRANSACTION_ID_TIME_ZONE)
    except Exception:
        tx_timezone = timezone.get_current_timezone()
    return timezone.localtime(dt, tx_timezone)


def _transaction_part(value: Any, fallback: str = "unknown") -> str:
    text = _as_str(value).strip()
    if not text:
        return fallback
    return re.sub(r"\s+", "", text)


def _build_transaction_id(values: dict[str, Any]) -> str:
    """
    Format:
      brandsuppliedfieldid-doctornumber-collateralid-datetime

    Example:
      FR001-919876543210-42-20260530143005
    """
    dt = _local_dt(values.get("sent_at") or values.get("created_at"))
    field_part = _transaction_part(
        values.get("field_rep_unique_id") or values.get("field_rep_id")
    )
    doctor_part = _transaction_part(values.get("doctor_number"))
    collateral_part = _transaction_part(values.get("collateral_id"))
    datetime_part = dt.strftime(TRANSACTION_DATETIME_FORMAT)
    return f"{field_part}-{doctor_part}-{collateral_part}-{datetime_part}"[:128]


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


def _infer_brand_campaign_id(share_log: ShareLog) -> str:
    bc_id = _as_str(getattr(share_log, "__dict__", {}).get("brand_campaign_id", "")).strip()
    if bc_id:
        return bc_id

    collateral_id = _resolve_collateral_id(share_log)
    if not collateral_id:
        return ""

    try:
        from collateral_management.models import CampaignCollateral

        link = (
            CampaignCollateral.objects.select_related("campaign")
            .filter(collateral_id=collateral_id)
            .order_by("-id")
            .first()
        )
        if link and getattr(link, "campaign", None):
            return _as_str(getattr(link.campaign, "brand_campaign_id", "")).strip()
    except Exception:
        pass

    return ""


def _brand_field_id_from_portal_user(field_rep_id: Any) -> str:
    rep_pk = _as_int(field_rep_id)
    if not rep_pk:
        return ""

    try:
        from user_management.models import User

        field_id = (
            User.objects.filter(id=rep_pk)
            .values_list("field_id", flat=True)
            .first()
        )
        if field_id:
            return _as_str(field_id).strip()
    except Exception:
        pass

    return ""


def _brand_field_id_from_master(share_log: ShareLog, field_rep_id: Any) -> str:
    email = _as_str(getattr(share_log, "__dict__", {}).get("field_rep_email", "")).strip()

    try:
        from campaign_management.master_models import MasterFieldRep

        queryset = MasterFieldRep.objects.using(MASTER_ALIAS).select_related("user")
        rep = None
        if email:
            rep = queryset.filter(user__email__iexact=email).first()
        if not rep:
            rep_pk = _as_int(field_rep_id)
            if rep_pk:
                rep = queryset.filter(id=rep_pk).first()

        if rep:
            return _as_str(getattr(rep, "brand_supplied_field_rep_id", "")).strip()
    except Exception:
        pass

    return ""


def _resolve_brand_supplied_field_id(
    share_log: ShareLog,
    explicit_field_id: Optional[str] = None,
) -> str:
    explicit = _as_str(explicit_field_id).strip()
    if explicit:
        return explicit

    field_rep_id = getattr(share_log, "field_rep_id", None)

    # In older rows field_rep_id points to the local portal User; in newer flows it
    # can point to the master FieldRep. Try both and keep the raw id as fallback.
    field_id = _brand_field_id_from_portal_user(field_rep_id)
    if field_id:
        return field_id

    field_id = _brand_field_id_from_master(share_log, field_rep_id)
    if field_id:
        return field_id

    return ""


def _maybe_backfill_field_rep_id(share_log: ShareLog) -> None:
    """
    If ShareLog.field_rep_id is missing, try to backfill from master DB using field_rep_email.
    This is best-effort and should never crash tracking.
    """
    if getattr(share_log, "field_rep_id", None):
        return

    email = _as_str(getattr(share_log, "__dict__", {}).get("field_rep_email", "")).strip()
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
    field_rep_unique_id: Optional[str] = None,
    sent_at=None,
) -> Optional[dict[str, Any]]:
    if not share_log:
        return None

    _maybe_backfill_field_rep_id(share_log)

    field_rep_id = getattr(share_log, "field_rep_id", None)
    if field_rep_id is None:
        print(
            "[TXDBG] ShareLog.field_rep_id is None; skipping transaction upsert. share_log.id=",
            getattr(share_log, "id", None),
        )
        return None

    collateral_id = _resolve_collateral_id(share_log)
    if collateral_id is None:
        print(
            "[TXDBG] ShareLog collateral is missing; skipping transaction upsert. share_log.id=",
            getattr(share_log, "id", None),
        )
        return None

    event_at = sent_at or getattr(share_log, "share_timestamp", None) or timezone.now()
    bc_raw = _as_str(brand_campaign_id).strip() or _infer_brand_campaign_id(share_log)
    bc_id = canonical_brand_campaign_id(bc_raw, sync_from_master=True)
    doctor_number = _as_str(getattr(share_log, "doctor_identifier", "")).strip()

    values = {
        "brand_campaign_id": bc_id,
        "field_rep_id": _as_str(field_rep_id).strip(),
        "field_rep_unique_id": _resolve_brand_supplied_field_id(
            share_log,
            explicit_field_id=field_rep_unique_id,
        ),
        "doctor_name": _as_str(doctor_name).strip() if doctor_name else None,
        "doctor_number": doctor_number,
        "collateral_id": int(collateral_id),
        "transaction_date": _local_dt(event_at).date(),
        "share_management_engagement_id": _as_int(getattr(share_log, "id", None)),
        "sent_at": event_at,
    }
    values["transaction_id"] = _build_transaction_id(values)
    return values


def _latest_transaction(base_values: dict[str, Any]) -> Optional[CollateralTransaction]:
    sm_engagement_id = base_values.get("share_management_engagement_id")
    if sm_engagement_id:
        latest = (
            CollateralTransaction.objects.filter(
                share_management_engagement_id=sm_engagement_id
            )
            .order_by("-updated_at", "-id")
            .first()
        )
        if latest:
            return latest

    queryset = CollateralTransaction.objects.filter(
        field_rep_id=_as_str(base_values.get("field_rep_id")).strip(),
        doctor_number=base_values.get("doctor_number") or "",
        collateral_id=base_values.get("collateral_id"),
    )

    if base_values.get("transaction_date"):
        queryset = queryset.filter(transaction_date=base_values["transaction_date"])

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
        if key == "transaction_id" and snapshot_values.get("transaction_id"):
            continue
        if isinstance(value, str) and not value.strip() and key in snapshot_values:
            continue
        snapshot_values[key] = value

    if not snapshot_values.get("field_rep_unique_id"):
        snapshot_values["field_rep_unique_id"] = snapshot_values.get("field_rep_id", "")

    if not snapshot_values.get("transaction_id"):
        snapshot_values["transaction_id"] = _build_transaction_id(snapshot_values)

    return snapshot_values


def _save_transaction(
    snapshot_values: dict[str, Any],
    action_name: str,
    *,
    refresh_transaction_id: bool = False,
) -> Optional[CollateralTransaction]:
    try:
        if refresh_transaction_id:
            snapshot_values["transaction_id"] = _build_transaction_id(snapshot_values)

        lookup = {
            "field_rep_id": _as_str(snapshot_values.get("field_rep_id")).strip(),
            "doctor_number": snapshot_values.get("doctor_number") or "",
            "collateral_id": int(snapshot_values.get("collateral_id") or 0),
            "transaction_date": snapshot_values.get("transaction_date"),
        }

        defaults = {
            key: value
            for key, value in snapshot_values.items()
            if key not in lookup and key in SNAPSHOT_FIELDS
        }

        obj, _created = CollateralTransaction.objects.update_or_create(
            defaults=defaults,
            **lookup,
        )
        return obj
    except Exception as e:
        print(f"[TXDBG] {action_name} failed:", e)
        return None


def upsert_from_sharelog(
    share_log: ShareLog,
    brand_campaign_id: Any = "",
    doctor_name: Optional[str] = None,
    field_rep_unique_id: Optional[str] = None,
    sent_at=None,
):
    """
    Create or update the transaction row for this ShareLog.
    transaction_id is persisted as:
      brandsuppliedfieldid-doctornumber-collateralid-datetime
    """
    base_values = _base_transaction_values(
        share_log=share_log,
        brand_campaign_id=brand_campaign_id,
        doctor_name=doctor_name,
        field_rep_unique_id=field_rep_unique_id,
        sent_at=sent_at,
    )
    if not base_values:
        return None

    snapshot_values = _merged_snapshot_values(base_values)
    return _save_transaction(
        snapshot_values,
        "upsert_from_sharelog",
        refresh_transaction_id=True,
    )


def mark_viewed(share_log: ShareLog, sm_engagement_id=None, when=None):
    base_values = _base_transaction_values(share_log)
    if not base_values:
        return None

    snapshot_values = _merged_snapshot_values(base_values)
    now = when or timezone.now()

    snapshot_values["has_viewed"] = True
    if not snapshot_values.get("viewed_at"):
        snapshot_values["viewed_at"] = now

    return _save_transaction(snapshot_values, "mark_viewed")


def mark_pdf_progress(
    share_log: ShareLog,
    last_page=0,
    completed=False,
    dv_engagement_id=None,
    total_pages=0,
    sm_engagement_id=None,
    when=None,
):
    base_values = _base_transaction_values(share_log)
    if not base_values:
        return None

    snapshot_values = _merged_snapshot_values(base_values)
    now = when or timezone.now()

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

    snapshot_values["has_viewed"] = True
    if not snapshot_values.get("viewed_at"):
        snapshot_values["viewed_at"] = now

    snapshot_values["last_page_scrolled"] = max(
        int(snapshot_values.get("last_page_scrolled", 0) or 0),
        last_page_i,
    )

    if completed or (
        total_pages_i > 0 and snapshot_values["last_page_scrolled"] >= total_pages_i
    ):
        snapshot_values["has_viewed_last_page"] = True
        if not snapshot_values.get("viewed_last_page_at"):
            snapshot_values["viewed_last_page_at"] = now

    dv_id = _as_int(dv_engagement_id)
    if dv_id is not None:
        snapshot_values["doctor_viewer_engagement_id"] = dv_id

    return _save_transaction(snapshot_values, "mark_pdf_progress")


def mark_downloaded_pdf(share_log: ShareLog, sm_engagement_id=None, when=None):
    base_values = _base_transaction_values(share_log)
    if not base_values:
        return None

    snapshot_values = _merged_snapshot_values(base_values)
    now = when or timezone.now()

    snapshot_values["has_downloaded_pdf"] = True
    if not snapshot_values.get("downloaded_pdf_at"):
        snapshot_values["downloaded_pdf_at"] = now

    return _save_transaction(snapshot_values, "mark_downloaded_pdf")


def mark_video_event(
    share_log: ShareLog,
    status=0,        # kept for compatibility (not used)
    percentage=0,
    event_id=0,
    when=None,
    sm_engagement_id=None,
):
    base_values = _base_transaction_values(share_log)
    if not base_values:
        return None

    snapshot_values = _merged_snapshot_values(base_values)
    now = when or timezone.now()

    try:
        pct = int(percentage or 0)
    except Exception:
        pct = 0
    pct = max(0, min(100, pct))

    snapshot_values["total_video_events"] = int(
        snapshot_values.get("total_video_events", 0) or 0
    ) + 1
    snapshot_values["last_video_percentage"] = max(
        int(snapshot_values.get("last_video_percentage", 0) or 0),
        pct,
    )
    snapshot_values["last_video_event_at"] = now

    if 0 < pct < 50:
        snapshot_values["video_view_lt_50"] = True
        if not snapshot_values.get("video_lt_50_at"):
            snapshot_values["video_lt_50_at"] = now
    if 50 <= pct < 100:
        snapshot_values["video_view_gt_50"] = True
        if not snapshot_values.get("video_gt_50_at"):
            snapshot_values["video_gt_50_at"] = now
    if pct >= 100:
        snapshot_values["video_view_100"] = True
        if not snapshot_values.get("video_100_at"):
            snapshot_values["video_100_at"] = now

    event_id_int = _as_int(event_id)
    if event_id_int is not None:
        snapshot_values["video_tracking_last_event_id"] = event_id_int

    return _save_transaction(snapshot_values, "mark_video_event")
