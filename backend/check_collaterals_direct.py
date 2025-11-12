import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from django.db import connection
from campaign_management.models import Campaign, CampaignCollateral
from collateral_management.models import Collateral

def check_all_tables():
    # Check campaigns
    print("\nCampaigns:")
    for campaign in Campaign.objects.all():
        print(f"- ID: {campaign.id}, Name: {campaign.name}, Brand Campaign ID: {campaign.brand_campaign_id}")
    
    # Check campaign collaterals
    print("\nCampaign Collaterals:")
    for cc in CampaignCollateral.objects.all().select_related('campaign', 'collateral'):
        print(f"- Campaign: {cc.campaign.brand_campaign_id} ({cc.campaign.name}), "
              f"Collateral ID: {cc.collateral.id}, Title: {getattr(cc.collateral, 'title', getattr(cc.collateral, 'item_name', 'N/A'))}")
    
    # Check all collaterals
    print("\nAll Collaterals:")
    for c in Collateral.objects.all():
        print(f"- ID: {c.id}, Title: '{getattr(c, 'title', getattr(c, 'item_name', 'N/A'))}', Type: {getattr(c, 'type', 'N/A')}")
    
    # Specifically check for BIOTECH-D1D829
    print("\nChecking collaterals for BIOTECH-D1D829:")
    from django.db.models import Q
    
    # Check through CampaignCollateral
    campaign_collaterals = CampaignCollateral.objects.filter(
        Q(campaign__brand_campaign_id='BIOTECH-D1D829') |
        Q(campaign__id=63)  # From your previous output
    ).select_related('campaign', 'collateral')
    
    if campaign_collaterals.exists():
        print("\nFound collaterals through CampaignCollateral:")
        for cc in campaign_collaterals:
            print(f"- Collateral ID: {cc.collateral.id}, "
                  f"Title: '{getattr(cc.collateral, 'title', getattr(cc.collateral, 'item_name', 'N/A'))}', "
                  f"Campaign: {cc.campaign.brand_campaign_id} ({cc.campaign.name})")
    else:
        print("No collaterals found through CampaignCollateral")
    
    # Check collaterals directly linked to campaign
    direct_collaterals = Collateral.objects.filter(
        campaign__brand_campaign_id='BIOTECH-D1D829'
    )
    
    if direct_collaterals.exists():
        print("\nFound collaterals directly linked to campaign:")
        for c in direct_collaterals:
            print(f"- ID: {c.id}, Title: '{getattr(c, 'title', getattr(c, 'item_name', 'N/A'))}', Type: {getattr(c, 'type', 'N/A')}")

if __name__ == "__main__":
    check_all_tables()
