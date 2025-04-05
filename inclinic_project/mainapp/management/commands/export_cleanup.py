from django.core.management.base import BaseCommand
from django.utils import timezone
from mainapp.models import (Campaign, CampaignContent, DoctorShare, PDFEvent, VideoEvent)
from django.db import connections

class Command(BaseCommand):
    help = "Exports new records to the reporting DB, marks them as exported, and archives completed campaigns."

    def handle(self, *args, **options):
        self.stdout.write("Starting export & cleanup...")

        # 1. Get reporting DB connection from Django
        report_conn = connections['reporting']  # We'll define 'reporting' in DATABASES

        # 2. Export each table to mirrored tables in reporting DB
        self.export_table(Campaign, 'campaigns_rep', 'campaign_id', report_conn)
        self.export_table(CampaignContent, 'campaign_content_rep', 'content_id', report_conn)
        self.export_table(DoctorShare, 'doctor_shares_rep', 'share_id', report_conn)
        self.export_table(PDFEvent, 'pdf_events_rep', 'pdf_event_id', report_conn)
        self.export_table(VideoEvent, 'video_events_rep', 'video_event_id', report_conn)

        # 3. Archive completed campaigns
        self.archive_completed_campaigns()

        self.stdout.write("Export & cleanup completed successfully.")

    def export_table(self, model_class, report_table_name, pk_field, report_conn):
        """
        Exports rows where exported_at IS NULL to the reporting DB,
        then sets exported_at to now() in the transaction DB.
        """
        qs = model_class.objects.filter(exported_at__isnull=True)
        if not qs.exists():
            return

        # We'll build an INSERT statement dynamically
        columns = [field.name for field in model_class._meta.get_fields() if field.name not in ['exported_at']]
        cursor = report_conn.cursor()

        for obj in qs:
            # Build the column values
            row_data = {}
            for col in columns:
                row_data[col] = getattr(obj, col, None)

            # Construct column list & placeholders
            col_string = ', '.join(columns)
            placeholder_string = ', '.join(['%s'] * len(columns))

            insert_sql = f"INSERT INTO {report_table_name} ({col_string}) VALUES ({placeholder_string})"
            # Convert datetimes to string if needed
            values_tuple = tuple(row_data[col] if row_data[col] is not None else None for col in columns)

            cursor.execute(insert_sql, values_tuple)

            # Mark as exported
            obj.exported_at = timezone.now()
            obj.save()

        report_conn.commit()
        cursor.close()

    def archive_completed_campaigns(self):
        # Simple approach: mark campaigns ended in the past as ARCHIVED if end_date < today
        today = timezone.now().date()
        completed_campaigns = Campaign.objects.filter(end_date__lt=today, status='ACTIVE')
        for camp in completed_campaigns:
            camp.status = 'COMPLETED'
            camp.save()

