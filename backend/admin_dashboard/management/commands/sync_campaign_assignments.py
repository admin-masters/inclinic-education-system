from django.core.management.base import BaseCommand
from django.db import transaction
from campaign_management.models import CampaignAssignment
from admin_dashboard.models import FieldRepCampaign


class Command(BaseCommand):
    help = 'Sync CampaignAssignment records with existing FieldRepCampaign records'

    def handle(self, *args, **options):
        created_count = 0
        skipped_count = 0
        
        self.stdout.write('Starting sync of CampaignAssignment records...')
        
        with transaction.atomic():
            # Get all FieldRepCampaign records
            field_rep_campaigns = FieldRepCampaign.objects.all()
            
            for frc in field_rep_campaigns:
                # Check if corresponding CampaignAssignment exists
                existing_assignment = CampaignAssignment.objects.filter(
                    field_rep=frc.field_rep,
                    campaign=frc.campaign
                ).first()
                
                if not existing_assignment:
                    # Create the missing CampaignAssignment
                    CampaignAssignment.objects.create(
                        field_rep=frc.field_rep,
                        campaign=frc.campaign
                    )
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Created CampaignAssignment for {frc.field_rep.email} -> {frc.campaign.brand_campaign_id}'
                        )
                    )
                else:
                    skipped_count += 1
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Sync completed: Created {created_count} new CampaignAssignment records, '
                    f'skipped {skipped_count} existing records.'
                )
            )
