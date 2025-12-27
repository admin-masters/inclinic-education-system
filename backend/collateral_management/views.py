from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.db import transaction 
from django.http import FileResponse, Http404
import os
from .decorators import admin_required
from .models import Collateral, CampaignCollateral
from .forms import CollateralForm, CampaignCollateralForm
from campaign_management.models import Campaign
from .forms import CampaignCollateralDateForm

class CollateralListView(ListView):
    model = Collateral
    template_name = 'collateral_management/collateral_list.html'
    context_object_name = 'collaterals'
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Return collaterals, optionally filtered by brand campaign"""
        queryset = Collateral.objects.filter(is_active=True)
        
        # Check for campaign filter in query parameters
        campaign_filter = self.request.GET.get('campaign')
        if campaign_filter:
            # Filter collaterals that are linked to the specified brand campaign
            queryset = queryset.filter(
                campaign__brand_campaign_id=campaign_filter
            )
            
        return queryset.select_related('campaign')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get the current campaign filter
        campaign_id = self.request.GET.get('campaign', '')
        campaign = None
        
        if campaign_id:
            try:
                campaign = Campaign.objects.get(brand_campaign_id=campaign_id)
            except Campaign.DoesNotExist:
                pass
                
        context['campaign_filter'] = campaign  # Now passing the campaign object
        
        # Get all unique campaigns that have collaterals
        context['available_campaigns'] = Campaign.objects.filter(
            id__in=Collateral.objects.filter(is_active=True)
                                   .values_list('campaign', flat=True)
                                   .distinct()
        ).order_by('brand_campaign_id')
        
        return context


class CollateralDetailView(DetailView):
    model = Collateral
    template_name = 'collateral_management/collateral_detail.html'
    context_object_name = 'collateral'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        collateral = self.get_object()
        absolute_pdf_url = None
        try:
            if getattr(collateral, 'file', None):
                import os
                from django.urls import reverse
                
                # Generate URL using the custom serve_collateral_pdf function
                filename = os.path.basename(collateral.file.name)
                absolute_pdf_url = self.request.build_absolute_uri(
                    reverse('serve_collateral_pdf', args=[filename])
                )
                print(f"DEBUG: Generated PDF URL: {absolute_pdf_url}")
        except Exception as e:
            print(f"Error generating PDF URL: {e}")
            # Even if there's an error, don't fall back to collateral.file.url
            # Instead, try to construct the URL manually
            try:
                if getattr(collateral, 'file', None):
                    import os
                    filename = os.path.basename(collateral.file.name)
                    absolute_pdf_url = self.request.build_absolute_uri(f'/collaterals/tmp/{filename}/')
                    print(f"DEBUG: Manually constructed PDF URL: {absolute_pdf_url}")
            except Exception as manual_error:
                print(f"DEBUG: Manual URL construction also failed: {manual_error}")
        
        context['absolute_pdf_url'] = absolute_pdf_url
        return context


@method_decorator(admin_required, name='dispatch')
class CollateralCreateView(CreateView):
    model = Collateral
    form_class = CollateralForm
    template_name = 'collateral_management/collateral_create.html'
    success_url = reverse_lazy('collateral_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.is_active = True  # Ensure collateral is active by default
        return super().form_valid(form)


@method_decorator(admin_required, name='dispatch')
class CollateralUpdateView(UpdateView):
    model = Collateral
    form_class = CollateralForm
    template_name = 'collateral_management/collateral_update.html'
    success_url = reverse_lazy('collateral_list')


@method_decorator(admin_required, name='dispatch')
class CollateralDeleteView(DeleteView):
    model = Collateral
    template_name = 'collateral_management/collateral_delete.html'
    success_url = reverse_lazy('collateral_list')


@admin_required
def link_collateral_to_campaign(request):
    if request.method == 'POST':
        form = CampaignCollateralForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            exists = CampaignCollateral.objects.filter(
                campaign=obj.campaign,
                collateral=obj.collateral
            ).exists()
            if exists:
                messages.warning(request, "That collateral is already linked to this campaign.")
            else:
                obj.save()
                messages.success(request, "Collateral linked to campaign successfully.")
            return redirect('link_collateral_to_campaign')
    else:
        form = CampaignCollateralForm()

    linked = CampaignCollateral.objects.select_related('campaign', 'collateral').all()

    return render(request, 'collateral_management/link_collateral_to_campaign.html', {
        'form': form,
        'linked': linked,
    })


def unlink_collateral_from_campaign(request, pk):
    record = get_object_or_404(CampaignCollateral, pk=pk)
    record.delete()
    messages.success(request, "Collateral unlinked from campaign.")
    return redirect('link_collateral_to_campaign')


# @admin_required
def add_collateral_with_campaign(request, brand_campaign_id=None):
    """
    One-page “Add Collateral” wizard that also links it to a Brand-Campaign.
    If brand_campaign_id is provided, filter campaigns to show only that brand's campaigns.
    """
    selected_campaign = None
    
    # If brand_campaign_id is provided, get the campaign and filter choices
    if brand_campaign_id:
        try:
            selected_campaign = Campaign.objects.get(brand_campaign_id=brand_campaign_id)
        except Campaign.DoesNotExist:
            messages.error(request, f"Campaign with Brand Campaign ID '{brand_campaign_id}' not found.")
            return redirect("collateral_list")
    
    if request.method == "POST":
        form = CollateralForm(
            request.POST, 
            request.FILES, 
            brand_campaign_id=brand_campaign_id
        )
        if form.is_valid():
            with transaction.atomic():
                collateral = form.save(commit=False)
                collateral.created_by = request.user
                collateral.is_active = True  # Ensure collateral is active by default
                # Correct: read from the proper purpose field
                collateral.purpose = form.cleaned_data.get('purpose')
                
                # If we have a selected campaign, ensure it's set on the collateral
                if selected_campaign:
                    collateral.campaign = selected_campaign
                
                collateral.save()
                
                # Create the campaign collateral link
                CampaignCollateral.objects.create(
                    campaign=collateral.campaign,
                    collateral=collateral,
                )
                
                # Get the brand campaign ID for the success message
                brand_id = collateral.campaign.brand_campaign_id if collateral.campaign else 'unknown'
                messages.success(
                    request, 
                    f"Collateral created & linked to campaign {brand_id} ✔︎"
                )
                
                # Redirect to the sharing dashboard with the brand filter
                if brand_campaign_id:
                    return redirect(f"/share/dashboard/?campaign={brand_campaign_id}")
                return redirect("fieldrep_dashboard")
    else:
        # Initialize the form with the brand_campaign_id
        form = CollateralForm(brand_campaign_id=brand_campaign_id)
        
        # If we have a selected campaign, set the initial value
        if selected_campaign:
            form.fields['campaign'].initial = selected_campaign

    return render(
        request,
        "collateral_management/add_collateral_combined.html",
        {
            "collateral_form": form,
            "selected_campaign": selected_campaign,
            "brand_campaign_id": brand_campaign_id,
        },
    )
def edit_campaign_collateral_dates(request, pk):
    campaign_collateral = get_object_or_404(CampaignCollateral, pk=pk)
    
    if request.method == 'POST':
        form = CampaignCollateralDateForm(request.POST, instance=campaign_collateral)
        if form.is_valid():
            form.save()
            return redirect('collateral_list')  # 🔁 replace with your actual redirect view name
    else:
        form = CampaignCollateralDateForm(instance=campaign_collateral)
    
    return render(request, 'collateral_management/edit_calendar.html', {
        'form': form,
        'campaign_collateral': campaign_collateral
    })

def replace_collateral(request, pk):
    # First try to get from collateral_management.Collateral
    try:
        from collateral_management.models import Collateral
        collateral = get_object_or_404(Collateral, pk=pk)
        
        # Get the campaign information for this collateral if it exists
        campaign_id = None
        if hasattr(collateral, 'campaign') and collateral.campaign:
            campaign_id = collateral.campaign.brand_campaign_id if hasattr(collateral.campaign, 'brand_campaign_id') else None
            
        # Define the form class
        from django import forms
        class SimpleCollateralForm(forms.ModelForm):
            class Meta:
                model = Collateral
                fields = ['title', 'type', 'vimeo_url', 'content_id', 'banner_1', 'banner_2', 'description', 'is_active', 'file']
                widgets = {
                    'title': forms.TextInput(attrs={'class': 'form-control'}),
                    'type': forms.Select(attrs={'class': 'form-select'}),
                    'vimeo_url': forms.HiddenInput(),
                    'content_id': forms.TextInput(attrs={'class': 'form-control'}),
                    'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                    'banner_1': forms.FileInput(attrs={'class': 'form-control'}),
                    'banner_2': forms.FileInput(attrs={'class': 'form-control'}),
                    'file': forms.FileInput(attrs={'class': 'form-control'}),
                    'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'})
                }
            
            # Add extra fields to match the original form
            campaign = forms.CharField(
                max_length=255,
                required=False,
                widget=forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
                label="Brand Campaign ID"
            )

            # New: accept Vimeo embed code
            vimeo_embed_code = forms.CharField(
                required=False,
                widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': '<iframe src="https://player.vimeo.com/video/123456789" ...></iframe>'}),
                label="Vimeo Embed Code"
            )
            
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                # Set initial values
                if self.instance and self.instance.pk:
                    self.fields['campaign'].initial = getattr(self.instance, 'campaign.brand_campaign_id', '')

            def clean(self):
                cleaned = super().clean()
                embed = cleaned.get('vimeo_embed_code', '').strip()
                c_type = cleaned.get('type')
                url_f = cleaned.get('vimeo_url')
                import re
                if embed:
                    src_match = re.search(r'src\s*=\s*"([^"]+)"', embed)
                    candidate = src_match.group(1) if src_match else embed
                    id_match = re.search(r'(?:player\.vimeo\.com\/video\/|vimeo\.com\/)(\d+)', candidate)
                    if id_match:
                        video_id = id_match.group(1)
                        cleaned['vimeo_url'] = f"https://player.vimeo.com/video/{video_id}"
                    elif 'player.vimeo.com' in candidate:
                        cleaned['vimeo_url'] = candidate
                    else:
                        self.add_error('vimeo_embed_code', 'Could not parse Vimeo embed code. Paste the full iframe code.')
                # Require video URL for video types
                if c_type == 'video' and not cleaned.get('vimeo_url'):
                    self.add_error('vimeo_embed_code', 'Provide a Vimeo embed code for videos.')
                if c_type == 'pdf_video' and not cleaned.get('vimeo_url'):
                    self.add_error('vimeo_embed_code', 'Provide a Vimeo embed code (for PDF + Video).')
                return cleaned
        
        # Set initial values for the form fields
        initial_data = {
            'campaign': campaign_id,
            'title': getattr(collateral, 'title', ''),
            'type': getattr(collateral, 'type', ''),
            'content_id': getattr(collateral, 'content_id', ''),
            'description': getattr(collateral, 'description', ''),
            'is_active': getattr(collateral, 'is_active', True),
            'vimeo_url': getattr(collateral, 'vimeo_url', ''),
            'banner_1': getattr(collateral, 'banner_1', None),
            'banner_2': getattr(collateral, 'banner_2', None),
        }
        
        # Get the campaign information for this collateral if it exists through CampaignCollateral
        campaign_id = None
        campaign_link = None
        try:
            # First try to get campaign directly from collateral
            if hasattr(collateral, 'campaign') and collateral.campaign:
                campaign_id = collateral.campaign.brand_campaign_id if hasattr(collateral.campaign, 'brand_campaign_id') else 'Unknown'
            else:
                # Fallback to CampaignCollateral link
                from campaign_management.models import CampaignCollateral as CampaignCollateralLink
                campaign_link = CampaignCollateralLink.objects.filter(collateral_id=collateral.id).select_related('campaign').first()
                if campaign_link and campaign_link.campaign:
                    campaign_id = getattr(campaign_link.campaign, 'brand_campaign_id', 'Unknown')
                else:
                    campaign_id = 'Unknown'
        except Exception as e:
            print(f"Error getting campaign link: {str(e)}")
            campaign_id = 'Unknown'
        
        # Define the form class
        from django import forms
        class SimpleCollateralForm(forms.ModelForm):
            class Meta:
                model = Collateral
                fields = ['title', 'type', 'vimeo_url', 'content_id', 'banner_1', 'banner_2', 'description', 'is_active', 'file']
                widgets = {
                    'title': forms.TextInput(attrs={'class': 'form-control'}),
                    'type': forms.Select(attrs={'class': 'form-select'}),
                    'vimeo_url': forms.HiddenInput(),
                    'content_id': forms.TextInput(attrs={'class': 'form-control'}),
                    'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                    'banner_1': forms.FileInput(attrs={'class': 'form-control'}),
                    'banner_2': forms.FileInput(attrs={'class': 'form-control'}),
                    'file': forms.FileInput(attrs={'class': 'form-control'}),
                    'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'})
                }
            
            # Add extra fields to match the original form
            campaign = forms.CharField(
                max_length=255,
                required=False,
                widget=forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
                label="Brand Campaign ID"
            )
            
            # Collateral title field (readonly)
            collateral_title = forms.CharField(
                required=False,
                widget=forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
                label="Collateral Title"
            )

            # New: accept Vimeo embed code
            vimeo_embed_code = forms.CharField(
                required=False,
                widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': '<iframe src="https://player.vimeo.com/video/123456789" ...></iframe>'}),
                label="Vimeo Embed Code"
            )
            
            # Update Purpose of the Collateral field to match Add Collateral form
            PURPOSE_CHOICES = [
                ('', 'Select Purpose of the Collateral (Optional)'),
                ('Doctor education short', 'Doctor education short'),
                ('Doctor education long', 'Doctor education long'),
                ('Patient education compliance', 'Patient education compliance'),
                ('Patient education general', 'Patient education general'),
            ]
            
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                
                # Make title field optional and hidden since we're using it for the collateral name
                if 'title' in self.fields:
                    self.fields['title'].required = False
                    self.fields['title'].widget = forms.HiddenInput()
                
                # Set choices for the purpose field
                self.fields['purpose'] = forms.ChoiceField(
                    choices=self.PURPOSE_CHOICES,
                    required=False,
                    label="Purpose of the Collateral",
                    widget=forms.Select(attrs={'class': 'form-select'})
                )
                
                # Set initial values
                if self.instance and self.instance.pk:
                    self.fields['campaign'].initial = campaign_id
                    self.fields['collateral_title'].initial = self.instance.title
                    # Set initial title to avoid validation errors
                    self.initial['title'] = self.instance.title
                    self.fields['purpose'].initial = getattr(self.instance, 'purpose', '')

            def clean(self):
                cleaned = super().clean()
                embed = cleaned.get('vimeo_embed_code', '').strip()
                c_type = cleaned.get('type')
                url_f = cleaned.get('vimeo_url')
                import re
                if embed:
                    src_match = re.search(r'src\s*=\s*"([^"]+)"', embed)
                    candidate = src_match.group(1) if src_match else embed
                    id_match = re.search(r'(?:player\.vimeo\.com\/video\/|vimeo\.com\/)(\d+)', candidate)
                    if id_match:
                        video_id = id_match.group(1)
                        cleaned['vimeo_url'] = f"https://player.vimeo.com/video/{video_id}"
                    elif 'player.vimeo.com' in candidate:
                        cleaned['vimeo_url'] = candidate
                    else:
                        self.add_error('vimeo_embed_code', 'Could not parse Vimeo embed code. Paste the full iframe code.')
                # Require video URL for video types
                if c_type == 'video' and not cleaned.get('vimeo_url'):
                    self.add_error('vimeo_embed_code', 'Provide a Vimeo embed code for videos.')
                if c_type == 'pdf_video' and not cleaned.get('vimeo_url'):
                    self.add_error('vimeo_embed_code', 'Provide a Vimeo embed code (for PDF + Video).')
                return cleaned
            
            def save(self, commit=True):
                instance = super().save(commit=False)
                # Map purpose field if it exists
                if 'purpose' in self.cleaned_data:
                    instance.purpose = self.cleaned_data['purpose']
                if commit:
                    instance.save()
                return instance
        
        # Get the current collateral title with multiple fallbacks
        current_title = (
            getattr(collateral, 'title', None) or 
            getattr(collateral, 'name', None) or 
            getattr(collateral, 'item_name', None) or 
            'Untitled Collateral'
        )

        # Set initial values for the form fields
        initial_data = {
            'campaign': campaign_id,
            'title': current_title,  # Use the determined title
            'type': getattr(collateral, 'type', ''),  # Get existing type
            'content_id': getattr(collateral, 'content_id', ''),  # Get content_id
            'description': getattr(collateral, 'description', ''),
            'is_active': getattr(collateral, 'is_active', True),
            'vimeo_url': getattr(collateral, 'vimeo_url', ''),
            'banner_1': getattr(collateral, 'banner_1', None),
            'banner_2': getattr(collateral, 'banner_2', None),
            'collateral_title': current_title,  # Also set the display field
        }
        
        if request.method == 'POST':
            # Create a mutable copy of the POST data
            post_data = request.POST.copy()
            
            # Handle file uploads
            files = request.FILES
            
            # Initialize form with POST data and FILES
            form = SimpleCollateralForm(post_data, files, instance=collateral)
            
            if form.is_valid():
                try:
                    # Get the instance but don't save yet
                    instance = form.save(commit=False)
                    
                    # Preserve the original title
                    if not instance.title or instance.title.strip() == '':
                        instance.title = current_title
                    
                    # First save the instance to get an ID if it's a new instance
                    instance.save()
                    
                    # Handle file uploads
                    if 'file' in files and files['file']:
                        # Get the file and its extension
                        new_file = files['file']
                        file_extension = os.path.splitext(new_file.name)[1].lower()
                        
                        # Only allow PDF files
                        if file_extension != '.pdf':
                            messages.error(request, 'Only PDF files are allowed for replacement.')
                            return redirect('replace_collateral', pk=instance.pk)
                            
                        # Delete old file if it exists
                        if instance.file:
                            try:
                                storage, path = instance.file.storage, instance.file.path
                                storage.delete(path)
                            except Exception as e:
                                print(f"Error deleting old file: {str(e)}")
                        
                        # Set new file with original filename but new content
                        original_filename = os.path.basename(instance.file.name) if instance.file else new_file.name
                        instance.file.save(
                            original_filename,
                            new_file,
                            save=False
                        )
                    
                    # Handle banner uploads
                    if 'banner_1' in files and files['banner_1']:
                        if instance.banner_1:
                            instance.banner_1.delete(save=False)
                        instance.banner_1.save(
                            files['banner_1'].name,
                            files['banner_1'],
                            save=False
                        )
                        
                    if 'banner_2' in files and files['banner_2']:
                        if instance.banner_2:
                            instance.banner_2.delete(save=False)
                        instance.banner_2.save(
                            files['banner_2'].name,
                            files['banner_2'],
                            save=False
                        )
                    
                    # Save the instance with the new files
                    instance.save()
                    
                    # Save many-to-many fields if any
                    form.save_m2m()
                    
                    # Redirect back to the same page instead of dashboard
                    return redirect('replace_collateral', pk=instance.pk)
                    
                except Exception as e:
                    # Log the error for debugging
                    print(f"Error saving collateral: {str(e)}")
            else:
                # Log form errors for debugging
                print("Form errors:", form.errors)
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
        
        # For GET requests or if form is invalid, render the form
        form = SimpleCollateralForm(instance=collateral, initial=initial_data)
        form.fields['campaign'].initial = campaign_id
        
        # Debug: Print all attributes of the collateral object
        print("Collateral object attributes:")
        for attr in dir(collateral):
            if not attr.startswith('_'):  # Skip private attributes
                try:
                    value = getattr(collateral, attr)
                    print(f"  {attr}: {value}")
                except Exception as e:
                    print(f"  {attr}: <error accessing>")
        
        # Get the title with multiple fallbacks
        collateral_title = (
            getattr(collateral, 'title', None) or 
            getattr(collateral, 'name', None) or 
            getattr(collateral, 'item_name', None) or 
            'Untitled Collateral'
        )
        
        # Set initial values for form fields
        form.fields['collateral_title'].initial = collateral_title
        form.fields['purpose'].initial = getattr(collateral, 'purpose', '')
        
        # Remove the title field since we're using it for the collateral name
        if 'title' in form.fields:
            form.fields.pop('title')
        
        # Debug output
        print(f"Final collateral title: {collateral_title}")
        print(f"Collateral ID: {getattr(collateral, 'id', 'N/A')}")
        print(f"Collateral type: {type(collateral)}")
        print(f"Form fields: {form.fields.keys()}")
        
        # Create a simple dictionary with the collateral data
        collateral_data = {
            'title': collateral_title,
            'id': getattr(collateral, 'id', ''),
            'file': getattr(collateral, 'file', None),
            'type': getattr(collateral, 'type', ''),
            'description': getattr(collateral, 'description', '')
        }
        
        context = {
            'form': form,
            'collateral': collateral_data,
            'debug_collateral': str(collateral)  # For template debugging
        }
        
        return render(request, 'collateral_management/replace_collateral_simple_updated.html', context)
    except Exception as e:
        print(f"Error in replace_collateral: {str(e)}")
        # Fallback to collateral_management.Collateral
        collateral = get_object_or_404(Collateral, pk=pk)
        if request.method == 'POST':
            form = CollateralForm(request.POST, request.FILES, instance=collateral)
            if form.is_valid():
                form.save()
                messages.success(request, 'Collateral replaced successfully!')
                return redirect('collateral_list')
        else:
            form = CollateralForm(instance=collateral)
        return render(request, 'collateral_management/replace_collateral_simple_updated.html', {'form': form, 'collateral': collateral})

def dashboard_delete_collateral(request, pk):
    from django.shortcuts import get_object_or_404, redirect
    from .models import Collateral
    if request.method == "POST":
        collateral = get_object_or_404(Collateral, pk=pk)
        collateral.delete()
        return redirect('/share/dashboard/')
    return redirect('/share/dashboard/')


def preview_collateral(request, pk):
    collateral = get_object_or_404(Collateral, pk=pk)
    absolute_pdf_url = None

    try:
        if getattr(collateral, 'file', None):
            import os
            from django.urls import reverse
            
            # Generate URL using the custom serve_collateral_pdf function
            filename = os.path.basename(collateral.file.name)
            absolute_pdf_url = request.build_absolute_uri(
                reverse('serve_collateral_pdf', args=[filename])
            )
            print(f"DEBUG: Generated PDF URL: {absolute_pdf_url}")

    except Exception as e:
        print(f"Error generating PDF URL: {e}")
        # Even if there's an error, don't fall back to collateral.file.url
        # Instead, try to construct the URL manually
        try:
            if getattr(collateral, 'file', None):
                import os
                filename = os.path.basename(collateral.file.name)
                absolute_pdf_url = request.build_absolute_uri(f'/collaterals/tmp/{filename}/')
                print(f"DEBUG: Manually constructed PDF URL: {absolute_pdf_url}")
        except Exception as manual_error:
            print(f"DEBUG: Manual URL construction also failed: {manual_error}")

    return render(request, 'doctor_viewer/view.html', {
        'verified': True,
        'collateral': collateral,
        'archives': [],
        'absolute_pdf_url': absolute_pdf_url,
        'engagement_id': 0,
        'short_code': '',
    })


def serve_collateral_pdf(request, filename):
    BASE_PDF_PATH = "/var/www/inclinic-media/collaterals/tmp/"
    file_path = os.path.join(BASE_PDF_PATH, filename)

    # Debug logging
    print(f"DEBUG serve_collateral_pdf: Looking for file: {filename}")
    print(f"DEBUG serve_collateral_pdf: Primary path: {file_path}")
    print(f"DEBUG serve_collateral_pdf: File exists at primary path: {os.path.exists(file_path)}")

    if not os.path.exists(file_path):
        # Try alternative paths based on how files might be stored
        alternative_paths = [
            os.path.join("/var/www/inclinic-media/", filename),
            os.path.join("/var/www/inclinic-media/collaterals/", filename),
        ]
        
        print(f"DEBUG serve_collateral_pdf: Trying alternative paths: {alternative_paths}")
        
        for alt_path in alternative_paths:
            print(f"DEBUG serve_collateral_pdf: Checking path: {alt_path} - Exists: {os.path.exists(alt_path)}")
            if os.path.exists(alt_path):
                file_path = alt_path
                print(f"DEBUG serve_collateral_pdf: Found file at: {file_path}")
                break
        else:
            print(f"DEBUG serve_collateral_pdf: File not found in any location")
            raise Http404("File not found")

    return FileResponse(open(file_path, "rb"), content_type="application/pdf")
