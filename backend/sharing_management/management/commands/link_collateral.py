from django.core.management.base import BaseCommand
from campaign_management.models import Campaign, CampaignCollateral
from collateral_management.models import Collateral

class Command(BaseCommand):
    help = 'Link a collateral to a campaign'

    def handle(self, *args, **options):
        try:
            # Get the campaign and collateral
            campaign = Campaign.objects.get(brand_campaign_id='BIOTECH-D1D829')
            collateral = Collateral.objects.get(id=213)  # Biopharma collateral
            
            # Create the association if it doesn't exist
            cc, created = CampaignCollateral.objects.get_or_create(
                campaign=campaign,
                collateral_id=collateral.id
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f'Successfully linked collateral "{collateral.title}" to campaign "{campaign.name}"'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Collateral "{collateral.title}" is already linked to campaign "{campaign.name}"'
                ))
                
        except Campaign.DoesNotExist:
            self.stderr.write(self.style.ERROR('Campaign with brand_campaign_id=BIOTECH-D1D829 not found'))
        except Collateral.DoesNotExist:
            self.stderr.write(self.style.ERROR('Collateral with id=213 not found'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {str(e)}'))
