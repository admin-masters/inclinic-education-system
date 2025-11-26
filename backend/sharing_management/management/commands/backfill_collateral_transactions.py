from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from sharing_management.models import ShareLog
from sharing_management.services.transactions import (
    upsert_from_sharelog,
    mark_viewed,
    mark_pdf_progress,
    mark_video_event,
)


class Command(BaseCommand):
    help = "Backfill CollateralTransaction from existing ShareLog & engagement tables"

    def add_arguments(self, parser):
        parser.add_argument('--brand', dest='brand', required=True)

    @transaction.atomic
    def handle(self, *args, **opts):
        brand = str(opts['brand'])
        for sl in ShareLog.objects.all().select_related('collateral'):
            upsert_from_sharelog(sl, brand_campaign_id=brand, sent_at=sl.share_timestamp)
            # If you want to traverse your existing engagement rows and call mark_* accordingly, do it here.
            # (e.g., loop over DoctorEngagement/VTR logs linked to this ShareLog and call mark_* helpers)
        self.stdout.write(self.style.SUCCESS("Backfill done"))