import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from django.db import connection
from campaign_management.models import Campaign, CampaignCollateral
from collateral_management.models import Collateral

def check_relationships():
    try:
        # Get the campaign
        campaign = Campaign.objects.get(brand_campaign_id='BIOTECH-D1D829')
        print(f"\nCampaign: {campaign.name} (ID: {campaign.id}, Brand Campaign ID: {campaign.brand_campaign_id})")
        
        # Check direct foreign key relationship
        print("\nChecking direct foreign key relationship (Collateral.campaign):")
        collaterals_direct = Collateral.objects.filter(campaign=campaign)
        print(f"Found {collaterals_direct.count()} collaterals with direct foreign key to campaign")
        for c in collaterals_direct:
            print(f"- ID: {c.id}, Title: '{c.title}', Type: {c.type}")
        
        # Check many-to-many through CampaignCollateral
        print("\nChecking many-to-many through CampaignCollateral:")
        campaign_collaterals = CampaignCollateral.objects.filter(campaign=campaign).select_related('collateral')
        print(f"Found {campaign_collaterals.count()} campaign collateral links")
        for cc in campaign_collaterals:
            print(f"- CampaignCollateral ID: {cc.id}, Collateral ID: {cc.collateral_id}, "
                  f"Title: '{cc.collateral.title}', Type: {cc.collateral.type}")
        
        # Check if the campaign has a many-to-many field to collaterals
        if hasattr(campaign, 'collaterals'):
            print("\nChecking many-to-many field 'collaterals' on Campaign:")
            m2m_collaterals = campaign.collaterals.all()
            print(f"Found {m2m_collaterals.count()} collaterals through many-to-many field")
            for c in m2m_collaterals:
                print(f"- ID: {c.id}, Title: '{c.title}', Type: {c.type}")
        
        # Check all collaterals to see if any reference this campaign
        print("\nChecking all collaterals for any references to this campaign:")
        all_collaterals = Collateral.objects.all()
        matching = []
        for c in all_collaterals:
            if hasattr(c, 'campaign') and c.campaign == campaign:
                matching.append(c)
            elif hasattr(c, 'campaigns') and campaign in c.campaigns.all():
                matching.append(c)
        
        print(f"Found {len(matching)} collaterals with any reference to this campaign")
        for c in matching:
            print(f"- ID: {c.id}, Title: '{c.title}', Type: {c.type}")
        
    except Campaign.DoesNotExist:
        print("Campaign with brand_campaign_id 'BIOTECH-D1D829' not found.")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_relationships()
