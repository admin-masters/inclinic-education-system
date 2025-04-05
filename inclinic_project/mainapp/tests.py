from django.test import TestCase, Client
from django.contrib.auth.models import User
from .models import Campaign

class BasicModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')

    def test_campaign_creation(self):
        camp = Campaign.objects.create(
            campaign_name="Test Campaign",
            therapy_area="Pediatrics",
            start_date="2025-01-01",
            end_date="2025-12-31",
            created_by=self.user
        )
        self.assertEqual(camp.campaign_name, "Test Campaign")

class BasicViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass')

    def test_login_required_list_campaigns(self):
        # Not logged in -> should redirect to login
        response = self.client.get('/list_campaigns/')
        self.assertEqual(response.status_code, 302)

        # Log in
        self.client.login(username='testuser', password='testpass')
        response = self.client.get('/list_campaigns/')
        self.assertEqual(response.status_code, 200)

