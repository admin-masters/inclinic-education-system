# sharing_management/services/transactions.py
from __future__ import annotations

from typing import Optional, Tuple

from django.utils import timezone

from sharing_management.models import CollateralTransaction, ShareLog


def _safe_int(v) -> Optional[int]:
    try:
        if v is None:
            return None
        if isinstance(v, int):
            return v
        s = str(v).strip()
        if s == "" or s.lower() == "none":
            return None
        return int(s)
    except Exception:
        return None


def _collateral_id_from_sharelog(sl: ShareLog) -> Optional[int]:
    """
    ShareLog may have collateral_id populated.
    If not, derive from ShortLink (resource_type="collateral").
    """
    try:
        if getattr(sl, "collateral_id", None):
            return int(sl.collateral_id)
    except Exception:
        pass

    try:
        short_link = getattr(sl, "short_link", None)
        if short_link and getattr(short_link, "resource_type", "") == "collateral":
            rid = getattr(short_link, "resource_id", None)
            if rid:
                return int(rid)
    except Exception:
        pass

    return None


def _doctor_number_from_sharelog(sl: ShareLog) -> str:
    return (getattr(sl, "doctor_identifier", "") or "").strip()


def _brand_campaign_id_from_sharelog(sl: ShareLog, fallback: str = "") -> str:
    bc = (getattr(sl, "brand_campaign_id", "") or "").strip()
    if bc:
        return bc
    return (fallback or "").strip()


def _sent_at_from_sharelog(sl: ShareLog, fallback=None):
    if fallback is not None:
        return fallback
    ts = getattr(sl, "share_timestamp", None)
    return ts or timezone.now()


def _get_or_create_tx_for_sharelog(
    sl: ShareLog,
    *,
    brand_campaign_id: str = "",
    doctor_name: Optional[str] = None,
    sent_at=None,
) -> Tuple[Optional[CollateralTransaction], bool]:
    """
    Creates/returns a CollateralTransaction row for this ShareLog, without using transaction_date.
    We mimic the old "transaction_date" grouping by using sent_at__date (local date).
    """
    field_rep_id = _safe_int(getattr(sl, "field_rep_id", None))
    doctor_number = _doctor_number_from_sharelog(sl)
    collateral_id = _collateral_id_from_sharelog(sl)
    share_channel = (getattr(sl, "share_channel", "") or "").strip()
    field_rep_email = (getattr(sl, "field_rep_email", "") or "").strip()
    bc_id = _brand_campaign_id_from_sharelog(sl, fallback=brand_campaign_id)
    sent_at_dt = _sent_at_from_sharelog(sl, fallback=sent_at)

    if not doctor_number or not collateral_id:
        print(
            "[TXNDBG] cannot create tx: missing doctor_number or collateral_id",
            "doctor_number=",
            doctor_number,
            "collateral_id=",
            collateral_id,
        )
        return None, False

    # Find an existing transaction for same rep+doctor+collateral ON SAME DAY (sent_at__date),
    # which replaces the old transaction_date behavior.
    qs = CollateralTransaction.objects.filter(
        doctor_number=doctor_number,
        collateral_id=collateral_id,
    )

    # field_rep_id can be null for legacy rows, but try to match when possible.
    if field_rep_id is not None:
        qs = qs.filter(field_rep_id=field_rep_id)
    else:
        qs = qs.filter(field_rep_id__isnull=True)

    if bc_id:
        qs = qs.filter(brand_campaign_id=bc_id)

    try:
        sent_day = timezone.localdate(sent_at_dt)
        qs = qs.filter(sent_at__date=sent_day)
    except Exception:
        # If sent_at_dt is weird, just skip date grouping.
        pass

    tx = qs.order_by("-sent_at", "-id").first()
    if tx:
        # Keep these fields reasonably synced (best effort).
        changed = False
        if bc_id and (tx.brand_campaign_id or "") != bc_id:
            tx.brand_campaign_id = bc_id
            changed = True
        if share_channel and (tx.share_channel or "") != share_channel:
            tx.share_channel = share_channel
            changed = True
        if field_rep_email and (tx.field_rep_email or "") != field_rep_email:
            tx.field_rep_email = field_rep_email
            changed = True
        if doctor_name and (tx.doctor_name or "") != doctor_name:
            tx.doctor_name = doctor_name
            changed = True
        if tx.sent_at is None:
            tx.sent_at = sent_at_dt
            changed = True

        if changed:
            tx.save(update_fields=["brand_campaign_id", "share_channel", "field_rep_email", "doctor_name", "sent_at", "updated_at"])
        return tx, False

    # Create new transaction row
    try:
        tx = CollateralTransaction.objects.create(
            field_rep_id=field_rep_id,
            field_rep_email=field_rep_email,
            brand_campaign_id=bc_id,
            doctor_number=doctor_number,
            doctor_name=(doctor_name or ""),
            collateral_id=collateral_id,
            share_channel=share_channel,
            sent_at=sent_at_dt,
        )
        print(
            "[TXNDBG] created CollateralTransaction",
            "id=",
            tx.id,
            "field_rep_id=",
            tx.field_rep_id,
            "doctor_number=",
            tx.doctor_number,
            "collateral_id=",
            tx.collateral_id,
            "brand_campaign_id=",
            tx.brand_campaign_id,
        )
        return tx, True
    except Exception as e:
        print("[TXNDBG] ERROR creating CollateralTransaction:", e)
        return None, False


# ---------------------------------------------------------------------
# Public API used by views
# ---------------------------------------------------------------------
def upsert_from_sharelog(
    share_log: ShareLog,
    *,
    brand_campaign_id: str = "",
    doctor_name: Optional[str] = None,
    field_rep_unique_id=None,  # kept for backward compatibility (unused)
    sent_at=None,
) -> Optional[CollateralTransaction]:
    tx, _created = _get_or_create_tx_for_sharelog(
        share_log,
        brand_campaign_id=brand_campaign_id,
        doctor_name=doctor_name,
        sent_at=sent_at,
    )
    return tx


def mark_viewed(share_log: ShareLog, sm_engagement_id=None) -> Optional[CollateralTransaction]:
    tx, _ = _get_or_create_tx_for_sharelog(share_log)
    if not tx:
        return None

    now = timezone.now()
    update_fields = ["has_viewed", "last_viewed_at", "updated_at"]

    if not tx.first_viewed_at:
        tx.first_viewed_at = now
        update_fields.append("first_viewed_at")

    tx.has_viewed = True
    tx.last_viewed_at = now

    if sm_engagement_id is not None:
        tx.sm_engagement_id = sm_engagement_id
        update_fields.append("sm_engagement_id")

    tx.save(update_fields=update_fields)
    return tx


def mark_pdf_progress(
    share_log: ShareLog,
    *,
    last_page: int = 0,
    completed: bool = False,
    dv_engagement_id=None,
    total_pages: int = 0,
) -> Optional[CollateralTransaction]:
    tx, _ = _get_or_create_tx_for_sharelog(share_log)
    if not tx:
        return None

    try:
        last_page = int(last_page or 0)
    except Exception:
        last_page = 0

    try:
        total_pages = int(total_pages or 0)
    except Exception:
        total_pages = 0

    update_fields = ["updated_at"]

    if last_page > int(tx.pdf_last_page or 0):
        tx.pdf_last_page = last_page
        update_fields.append("pdf_last_page")

    if total_pages > 0 and total_pages != int(tx.pdf_total_pages or 0):
        tx.pdf_total_pages = total_pages
        update_fields.append("pdf_total_pages")

    if completed and not bool(tx.pdf_completed):
        tx.pdf_completed = True
        update_fields.append("pdf_completed")

    if dv_engagement_id is not None:
        tx.dv_engagement_id = dv_engagement_id
        update_fields.append("dv_engagement_id")

    # Viewing PDF implies viewed
    if not tx.has_viewed:
        tx.has_viewed = True
        update_fields.append("has_viewed")
    if not tx.first_viewed_at:
        tx.first_viewed_at = timezone.now()
        update_fields.append("first_viewed_at")
    tx.last_viewed_at = timezone.now()
    update_fields.append("last_viewed_at")

    tx.save(update_fields=update_fields)
    return tx


def mark_downloaded_pdf(share_log: ShareLog) -> Optional[CollateralTransaction]:
    tx, _ = _get_or_create_tx_for_sharelog(share_log)
    if not tx:
        return None

    update_fields = ["downloaded_pdf", "updated_at"]
    tx.downloaded_pdf = True

    if not bool(tx.pdf_completed):
        tx.pdf_completed = True
        update_fields.append("pdf_completed")

    tx.save(update_fields=update_fields)
    return tx


def mark_video_event(
    share_log: ShareLog,
    *,
    status: int = 0,
    percentage: int = 0,
    event_id=0,  # kept for compat (unused)
    when=None,
) -> Optional[CollateralTransaction]:
    tx, _ = _get_or_create_tx_for_sharelog(share_log)
    if not tx:
        return None

    try:
        percentage = int(percentage or 0)
    except Exception:
        percentage = 0
    percentage = max(0, min(100, percentage))

    update_fields = ["video_watch_percentage", "updated_at"]

    if percentage > int(tx.video_watch_percentage or 0):
        tx.video_watch_percentage = percentage

    if percentage >= 90 and not bool(tx.video_completed):
        tx.video_completed = True
        update_fields.append("video_completed")

    # mark as viewed too
    if not tx.has_viewed:
        tx.has_viewed = True
        update_fields.append("has_viewed")
    if not tx.first_viewed_at:
        tx.first_viewed_at = when or timezone.now()
        update_fields.append("first_viewed_at")
    tx.last_viewed_at = when or timezone.now()
    update_fields.append("last_viewed_at")

    tx.save(update_fields=update_fields)
    return tx
