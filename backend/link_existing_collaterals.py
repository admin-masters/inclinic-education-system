import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from campaign_management.models import Campaign, CampaignCollateral
from collateral_management.models import Collateral

def link_existing_collaterals():
    try:
        # Get the campaign
        campaign = Campaign.objects.get(brand_campaign_id='BIOTECH-D1D829')
        print(f"Found campaign: {campaign.name} (ID: {campaign.id})")
        
        # Get collaterals directly linked to the campaign
        # First try the direct foreign key relationship
        collaterals = Collateral.objects.filter(campaign=campaign)
        
        # If no collaterals found, try through the many-to-many relationship
        if not collaterals.exists():
            collaterals = campaign.collaterals.all()
            
        print(f"Found {collaterals.count()} collaterals linked to campaign")
        
        for collateral in collaterals:
            # Check if the link already exists in CampaignCollateral
            if not CampaignCollateral.objects.filter(campaign=campaign, collateral=collateral).exists():
                # Create the link
                CampaignCollateral.objects.create(
                    campaign=campaign,
                    collateral=collateral
                )
                print(f"Linked collateral: {collateral.title} (ID: {collateral.id})")
            else:
                print(f"Collateral {collateral.title} (ID: {collateral.id}) is already linked")
        
        print("\nAll collaterals should now be linked in CampaignCollateral table")
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    link_existing_collaterals()
