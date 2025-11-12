from sharing_management.views import prefilled_fieldrep_gmail_share_collateral
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.messages import get_messages

def fix_collaterals():
    # Create a test request
    factory = RequestFactory()
    request = factory.get('/share/prefilled-fieldrep-gmail-share-collateral/?campaign=BIOTECH-D1D829')
    
    # Set up session data
    request.session = {
        'field_rep_id': 14133,
        'field_rep_email': 'bhartidhote8@gmail.com',
        'field_rep_field_id': 'bharti.dhote_1'
    }
    
    # Set up messages
    setattr(request, '_messages', FallbackStorage(request))
    
    # Call the view
    response = prefilled_fieldrep_gmail_share_collateral(request)
    
    # Print debug info
    print("Status code:", response.status_code)
    print("Messages:", [str(m) for m in get_messages(request)])
    
    if hasattr(response, 'context_data'):
        collaterals = response.context_data.get('collaterals', [])
        print(f"Found {len(collaterals)} collaterals")
        for c in collaterals:
            print(f"- {c.get('name')} (ID: {c.get('id')})")

if __name__ == "__main__":
    import os
    import django
    
    # Set up Django environment
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
    django.setup()
    
    # Run the fix
    fix_collaterals()
