import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from django import forms
from collateral_management.models import Collateral
from campaign_management.models import Campaign, CampaignCollateral
from campaign_management.forms import CampaignCollateralForm

def link_collateral_to_campaign():
    try:
        # Find the collateral with ID 209
        collateral = Collateral.objects.get(id=209)
        print(f'Found collateral: {collateral.title} (ID: {collateral.id})')
        
        # Find the campaign with the specified brand_campaign_id
        campaign = Campaign.objects.get(brand_campaign_id='BIOTECH-D1D829')
        print(f'Found campaign: {campaign.name} (Brand Campaign ID: {campaign.brand_campaign_id})')
        
        # Check if the association already exists
        if CampaignCollateral.objects.filter(campaign=campaign, collateral=collateral).exists():
            print('This collateral is already associated with the campaign')
        else:
            # Create the association using the form
            form_data = {
                'campaign': campaign.brand_campaign_id,
                'collateral': collateral.id,
                # Add any other required fields here
            }
            
            form = CampaignCollateralForm(form_data)
            
            if form.is_valid():
                campaign_collateral = form.save(commit=False)
                campaign_collateral.campaign = campaign
                campaign_collateral.save()
                print(f'Successfully associated collateral "{collateral.title}" with campaign "{campaign.brand_campaign_id}"')
            else:
                print('Form validation failed:')
                for field, errors in form.errors.items():
                    print(f'  {field}: {errors}')
        
        # Verify the association
        associated_collaterals = CampaignCollateral.objects.filter(campaign=campaign).select_related('collateral')
        print(f'\nCollaterals associated with campaign {campaign.brand_campaign_id}:')
        for cc in associated_collaterals:
            print(f'- {cc.collateral.title} (ID: {cc.collateral_id})')
            
    except Collateral.DoesNotExist:
        print('Error: Collateral with ID 209 not found')
    except Campaign.DoesNotExist:
        print('Error: Campaign with brand_campaign_id "BIOTECH-D1D829" not found')
    except Exception as e:
        print(f'An error occurred: {str(e)}')

if __name__ == "__main__":
    link_collateral_to_campaign()
