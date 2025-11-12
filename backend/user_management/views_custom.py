from django.contrib.auth.views import LoginView as BaseLoginView
from django.urls import reverse_lazy, reverse
from django.shortcuts import redirect
from django.http import HttpResponseRedirect, QueryDict
from django.utils.http import url_has_allowed_host_and_scheme

class CustomAdminLoginView(BaseLoginView):
    template_name = 'admin/login.html'
    
    def get(self, request, *args, **kwargs):
        # Store campaign from URL in session if it exists
        campaign_id = request.GET.get('campaign') or request.GET.get('brand_campaign_id')
        if campaign_id:
            request.session['brand_campaign_id'] = campaign_id
        return super().get(request, *args, **kwargs)
    
    def post(self, request, *args, **kwargs):
        # Store campaign from URL in session if it exists
        campaign_id = request.GET.get('campaign') or request.GET.get('brand_campaign_id')
        if campaign_id:
            request.session['brand_campaign_id'] = campaign_id
            
        # Also check for campaign in POST data (from hidden input)
        if not campaign_id:
            campaign_id = request.POST.get('campaign') or request.POST.get('brand_campaign_id')
            if campaign_id:
                request.session['brand_campaign_id'] = campaign_id
        
        return super().post(request, *args, **kwargs)
    
    def get_success_url(self):
        """Determine the URL to redirect to after successful login."""
        # Get the redirect URL from the form or URL
        redirect_to = self.request.POST.get(
            self.redirect_field_name,
            self.request.GET.get(self.redirect_field_name, '')
        )
        
        # If we have a valid redirect_to value, use it
        if url_has_allowed_host_and_scheme(redirect_to, allowed_hosts=None):
            return redirect_to
        
        # Get campaign from session
        campaign_id = self.request.session.get('brand_campaign_id')
        
        # Build the base URL
        url = reverse('admin-dashboard:fieldrep_list')
        
        # Add campaign parameter if it exists
        if campaign_id:
            return f"{url}?brand_campaign_id={campaign_id}"
            
        return url
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get campaign from URL or session
        campaign_id = self.request.GET.get('campaign') or \
                     self.request.GET.get('brand_campaign_id') or \
                     self.request.session.get('brand_campaign_id')
        
        if campaign_id:
            # Ensure the campaign is in the session
            self.request.session['brand_campaign_id'] = campaign_id
            
            # Set the next URL with the campaign parameter
            context['next'] = f"{reverse('admin-dashboard:fieldrep_list')}?brand_campaign_id={campaign_id}"
            
            # Add campaign to form action URL
            context['campaign'] = campaign_id
        
        return context
