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
    doctor_number: str          # 10 or “91xxxxxxxxxx”, keep consistent with your ShareLog
    collateral_id: int
    transaction_date: timezone.datetime.date


def make_transaction_id(field_rep_id: str, doctor_number: str, collateral_id: int) -> str:
    # mandatory format: field_rep_id + "*" + doctor_phone_number + "*" + collateral_id
    return f"{field_rep_id}*{doctor_number}*{collateral_id}"


@transaction.atomic
def upsert_from_sharelog(
    share_log: ShareLog,
    brand_campaign_id: str,
    doctor_name: Optional[str] = None,
    doctor_unique_id: Optional[str] = None,
    field_rep_unique_id: Optional[str] = None,
    sent_at: Optional[timezone.datetime] = None,
) -> CollateralTransaction:
    """
    Called when a field rep SENDS a collateral (ShareLog created).
    SCENARIO 1: same day, same link → update same row
    SCENARIO 2: new day (or new send) → new row
    """
    tx_date = (share_log.share_timestamp or timezone.now()).date()
    tx_id = make_transaction_id(str(share_log.field_rep_id), share_log.doctor_identifier, int(share_log.collateral_id))

    defaults = {
        "transaction_id": tx_id,
        "brand_campaign_id": str(brand_campaign_id),
        "field_rep_unique_id": field_rep_unique_id,
        "doctor_name": doctor_name,
        "doctor_unique_id": doctor_unique_id,
        "created_at": timezone.now(),
        "sent_at": sent_at or share_log.share_timestamp or timezone.now(),
    }

    obj, created = CollateralTransaction.objects.get_or_create(
        field_rep_id=str(share_log.field_rep_id),
        doctor_number=share_log.doctor_identifier,
        collateral_id=int(share_log.collateral_id),
        transaction_date=tx_date,
        defaults=defaults,
    )
    if not created:
        # keep non-empty values only; don't overwrite useful data with None
        changed = False
        for k, v in defaults.items():
            if v and getattr(obj, k, None) in (None, "", 0):
                setattr(obj, k, v); changed = True
        if changed:
            obj.updated_at = timezone.now()
            obj.save()
    return obj


@transaction.atomic
def mark_viewed(share_log: ShareLog, when=None, sm_engagement_id: Optional[int]=None):
    when = when or timezone.now()
    tx = _get_tx_for_share(share_log)
    tx.has_viewed = True
    tx.viewed_at = tx.viewed_at or when
    if sm_engagement_id:
        tx.share_management_engagement_id = sm_engagement_id
    tx.updated_at = when
    tx.save(update_fields=["has_viewed","viewed_at","share_management_engagement_id","updated_at"])


@transaction.atomic
def mark_pdf_progress(share_log: ShareLog, last_page: int, completed: bool, when=None, dv_engagement_id: Optional[int]=None):
    when = when or timezone.now()
    tx = _get_tx_for_share(share_log)
    if last_page and last_page > (tx.last_page_scrolled or 0):
        tx.last_page_scrolled = last_page
    if completed:
        tx.has_viewed_last_page = True
        tx.viewed_last_page_at = tx.viewed_last_page_at or when
    if dv_engagement_id:
        tx.doctor_viewer_engagement_id = dv_engagement_id
    tx.updated_at = when
    tx.save()


@transaction.atomic
def mark_video_event(share_log: ShareLog, status: int, percentage: int, event_id: int, when=None):
    """
    percentage: 0..100 (int)
    status: your current smallint code (Play/Pause/Completed). We only care about percentage thresholds here.
    """
    when = when or timezone.now()
    tx = _get_tx_for_share(share_log)
    tx.total_video_events = (tx.total_video_events or 0) + 1
    if percentage is not None and percentage >= (tx.last_video_percentage or 0):
        tx.last_video_percentage = percentage
        tx.last_video_event_at = when
        tx.video_tracking_last_event_id = event_id
    # threshold flags
    if percentage is not None:
        if percentage >= 100:
            tx.video_view_100 = True
            tx.video_100_at = tx.video_100_at or when
        elif percentage >= 50:
            tx.video_view_gt_50 = True
            tx.video_gt_50_at = tx.video_gt_50_at or when
        elif percentage > 0:
            tx.video_view_lt_50 = True
            tx.video_lt_50_at = tx.video_lt_50_at or when
    tx.updated_at = when
    tx.save()


def _get_tx_for_share(share_log: ShareLog) -> CollateralTransaction:
    tx_date = (share_log.share_timestamp or timezone.now()).date()
    return CollateralTransaction.objects.get(
        field_rep_id=str(share_log.field_rep_id),
        doctor_number=share_log.doctor_identifier,
        collateral_id=int(share_log.collateral_id),
        transaction_date=tx_date,
    )


@transaction.atomic
def mark_downloaded_pdf(share_log: ShareLog, when=None):
    when = when or timezone.now()
    tx = _get_tx_for_share(share_log)
    tx.has_downloaded_pdf = True
    tx.downloaded_pdf_at = tx.downloaded_pdf_at or when
    tx.updated_at = when
    tx.save(update_fields=["has_downloaded_pdf","downloaded_pdf_at","updated_at"])