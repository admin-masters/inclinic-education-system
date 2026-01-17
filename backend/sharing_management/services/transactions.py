from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from sharing_management.models import CollateralTransaction, ShareLog


@dataclass
class TxIdentity:
    brand_campaign_id: str
    field_rep_id: str
    doctor_number: str  # keep consistent with ShareLog.doctor_identifier
    collateral_id: int
    transaction_date: timezone.datetime.date


def get_or_create_tx(identity: TxIdentity) -> CollateralTransaction:
    tx, _ = CollateralTransaction.objects.get_or_create(
        brand_campaign_id=identity.brand_campaign_id,
        field_rep_id=identity.field_rep_id,
        doctor_number=identity.doctor_number,
        collateral_id=identity.collateral_id,
        transaction_date=identity.transaction_date,
    )
    return tx


@transaction.atomic
def upsert_from_sharelog(share_log: ShareLog, brand_campaign_id: str) -> CollateralTransaction:
    identity = TxIdentity(
        brand_campaign_id=brand_campaign_id,
        field_rep_id=str(share_log.field_rep_id),
        doctor_number=share_log.doctor_identifier,
        collateral_id=share_log.collateral_id,
        transaction_date=share_log.share_timestamp.date(),
    )
    tx = get_or_create_tx(identity)
    tx.sent_at = share_log.share_timestamp
    tx.save(update_fields=["sent_at"])
    return tx


def _get_tx_for_share(share_log: ShareLog) -> CollateralTransaction:
    return CollateralTransaction.objects.get(
        field_rep_id=str(share_log.field_rep_id),
        doctor_number=share_log.doctor_identifier,
        collateral_id=share_log.collateral_id,
        transaction_date=share_log.share_timestamp.date(),
    )


def _get_or_create_tx_for_share(share_log: ShareLog) -> CollateralTransaction:
    """
    ShareLogs created before transaction upsert existed (or if upsert failed)
    may not have a corresponding CollateralTransaction row. Create it on demand
    so open/progress tracking never breaks.
    """
    try:
        return _get_tx_for_share(share_log)
    except CollateralTransaction.DoesNotExist:
        brand_campaign_id = getattr(share_log, "campaign_id", "") or ""
        try:
            upsert_from_sharelog(share_log, brand_campaign_id=brand_campaign_id)
        except Exception:
            pass
        return _get_tx_for_share(share_log)


def mark_viewed(share_log: ShareLog, sm_engagement_id: Optional[str] = None) -> None:
    tx = _get_or_create_tx_for_share(share_log)
    tx.has_viewed = True
    tx.viewed_at = timezone.now()
    if sm_engagement_id:
        tx.share_management_engagement_id = sm_engagement_id
    tx.save(update_fields=["has_viewed", "viewed_at", "share_management_engagement_id"])


def mark_pdf_progress(share_log: ShareLog, last_page_scrolled: int) -> None:
    tx = _get_or_create_tx_for_share(share_log)
    if last_page_scrolled is not None:
        tx.last_page_scrolled = max(tx.last_page_scrolled or 0, int(last_page_scrolled))
    tx.save(update_fields=["last_page_scrolled"])


def mark_video_progress(share_log: ShareLog, video_watch_percentage: float) -> None:
    tx = _get_or_create_tx_for_share(share_log)
    if video_watch_percentage is not None:
        try:
            pct = float(video_watch_percentage)
        except (TypeError, ValueError):
            return
        tx.video_watch_percentage = max(float(tx.video_watch_percentage or 0), pct)
    tx.save(update_fields=["video_watch_percentage"])


def mark_video_event(share_log: ShareLog, event: str, current_time: float = 0, total_time: float = 0) -> None:
    if total_time and current_time and total_time > 0:
        pct = (current_time / total_time) * 100.0
        mark_video_progress(share_log, pct)


def mark_downloaded_pdf(share_log: ShareLog) -> None:
    tx = _get_or_create_tx_for_share(share_log)
    tx.has_downloaded_pdf = True
    tx.save(update_fields=["has_downloaded_pdf"])
