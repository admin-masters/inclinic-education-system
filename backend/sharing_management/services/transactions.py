# sharing_management/services/transactions.py
from __future__ import annotations

import uuid
from typing import Any, Optional

from django.conf import settings
from django.utils import timezone

from sharing_management.models import CollateralTransaction, ShareLog


MASTER_ALIAS = getattr(settings, "MASTER_DB_ALIAS", "master")


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


def upsert_from_sharelog(
    share_log: ShareLog,
    brand_campaign_id: Any = "",
    doctor_name: Optional[str] = None,
    field_rep_unique_id: Optional[str] = None,  # kept for compatibility; not used
    sent_at=None,
):
    """
    Create/update one CollateralTransaction row for this ShareLog.
    Primary key mapping is done via sm_engagement_id = ShareLog.id.
    """
    if not share_log:
        return None

    _maybe_backfill_field_rep_id(share_log)

    field_rep_id = getattr(share_log, "field_rep_id", None)
    if field_rep_id is None:
        # IMPORTANT: avoid "Field expected a number but got None"
        print("[TXDBG] ShareLog.field_rep_id is None; skipping transaction upsert. share_log.id=", getattr(share_log, "id", None))
        return None

    now = timezone.now()

    # ---- CRITICAL FIX: always string-cast before strip() ----
    bc_raw = brand_campaign_id if brand_campaign_id else getattr(share_log, "brand_campaign_id", "")
    bc_id = _as_str(bc_raw).strip()

    doctor_number = _as_str(getattr(share_log, "doctor_identifier", "")).strip()
    collateral_id = _resolve_collateral_id(share_log)

    # Build defaults carefully (avoid None -> int field failures)
    defaults = {
        "field_rep_id": int(field_rep_id),
        "field_rep_email": _as_str(getattr(share_log, "field_rep_email", "")).strip(),
        "brand_campaign_id": bc_id,
        "doctor_number": doctor_number,
        "doctor_name": _as_str(doctor_name).strip() if doctor_name else "",
        "share_channel": _as_str(getattr(share_log, "share_channel", "")).strip(),
        "sent_at": sent_at or getattr(share_log, "share_timestamp", None) or now,
        "sm_engagement_id": int(getattr(share_log, "id", 0) or 0),
        "updated_at": now,
    }

    if collateral_id is not None:
        defaults["collateral_id"] = int(collateral_id)

    lookup = {"sm_engagement_id": defaults["sm_engagement_id"]}

    try:
        tx, _created = CollateralTransaction.objects.update_or_create(
            **lookup,
            defaults=defaults,
        )
        return tx

    except CollateralTransaction.MultipleObjectsReturned:
        # If duplicates exist, update the newest row deterministically.
        tx = (
            CollateralTransaction.objects.filter(**lookup)
            .order_by("-id")
            .first()
        )
        if not tx:
            return None

        for k, v in defaults.items():
            setattr(tx, k, v)

        tx.save()
        return tx

    except Exception as e:
        print("[TXDBG] upsert_from_sharelog failed:", e)
        return None


def mark_viewed(share_log: ShareLog, sm_engagement_id=None):
    tx = upsert_from_sharelog(share_log)
    if not tx:
        return None

    now = timezone.now()

    if not getattr(tx, "has_viewed", False):
        tx.has_viewed = True
        if not getattr(tx, "first_viewed_at", None):
            tx.first_viewed_at = now

    tx.last_viewed_at = now
    tx.updated_at = now

    try:
        tx.save(update_fields=["has_viewed", "first_viewed_at", "last_viewed_at", "updated_at"])
    except Exception:
        tx.save()

    return tx


def mark_pdf_progress(
    share_log: ShareLog,
    last_page=0,
    completed=False,
    dv_engagement_id=None,
    total_pages=0,
    sm_engagement_id=None,
):
    tx = upsert_from_sharelog(share_log)
    if not tx:
        return None

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
    tx.has_viewed = True
    if not getattr(tx, "first_viewed_at", None):
        tx.first_viewed_at = now
    tx.last_viewed_at = now

    tx.pdf_last_page = max(int(getattr(tx, "pdf_last_page", 0) or 0), last_page_i)

    if total_pages_i:
        tx.pdf_total_pages = max(int(getattr(tx, "pdf_total_pages", 0) or 0), total_pages_i)

    if completed:
        tx.pdf_completed = True

    if dv_engagement_id is not None:
        try:
            tx.dv_engagement_id = int(dv_engagement_id)
        except Exception:
            pass

    tx.updated_at = now

    try:
        tx.save(update_fields=[
            "has_viewed",
            "first_viewed_at",
            "last_viewed_at",
            "pdf_last_page",
            "pdf_total_pages",
            "pdf_completed",
            "dv_engagement_id",
            "updated_at",
        ])
    except Exception:
        tx.save()

    return tx


def mark_downloaded_pdf(share_log: ShareLog, sm_engagement_id=None):
    tx = upsert_from_sharelog(share_log)
    if not tx:
        return None

    now = timezone.now()
    tx.downloaded_pdf = True
    tx.pdf_completed = True
    tx.updated_at = now

    try:
        tx.save(update_fields=["downloaded_pdf", "pdf_completed", "updated_at"])
    except Exception:
        tx.save()

    return tx


def mark_video_event(
    share_log: ShareLog,
    status=0,        # kept for compatibility (not used)
    percentage=0,
    event_id=0,      # kept for compatibility (not used)
    when=None,
    sm_engagement_id=None,
):
    tx = upsert_from_sharelog(share_log)
    if not tx:
        return None

    try:
        pct = int(percentage or 0)
    except Exception:
        pct = 0

    pct = max(0, min(100, pct))

    tx.video_watch_percentage = max(int(getattr(tx, "video_watch_percentage", 0) or 0), pct)
    if tx.video_watch_percentage >= 90:
        tx.video_completed = True

    tx.updated_at = when or timezone.now()

    try:
        tx.save(update_fields=["video_watch_percentage", "video_completed", "updated_at"])
    except Exception:
        tx.save()

    return tx
