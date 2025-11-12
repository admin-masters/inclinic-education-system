import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from campaign_management.models import Campaign, CampaignCollateral
from collateral_management.models import Collateral

def check_campaign_collaterals(brand_campaign_id):
    try:
        # Find the campaign by brand_campaign_id
        campaign = Campaign.objects.get(brand_campaign_id=brand_campaign_id)
        print(f'Campaign found: {campaign.name} (ID: {campaign.id}, Brand Campaign ID: {campaign.brand_campaign_id})')
        
        # Get all campaign collaterals for this campaign
        campaign_collaterals = CampaignCollateral.objects.filter(campaign=campaign).select_related('collateral')
        
        if campaign_collaterals.exists():
            print('\nLinked Collaterals:')
            for cc in campaign_collaterals:
                collateral = cc.collateral
                print(f"- ID: {collateral.id}, Title: '{collateral.title}', Type: {collateral.type}")
                print(f"  Start Date: {cc.start_date}, End Date: {cc.end_date}")
        else:
            print('\nNo collaterals are linked to this campaign.')
            
    except Campaign.DoesNotExist:
        print(f'Campaign with brand_campaign_id {brand_campaign_id} not found.')
    except Exception as e:
        print(f'An error occurred: {str(e)}')

if __name__ == "__main__":
    check_campaign_collaterals('BIOTECH-D1D829')
