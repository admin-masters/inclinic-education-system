from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.db import transaction 
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
        """Return only active collaterals"""
        return Collateral.objects.filter(is_active=True)


class CollateralDetailView(DetailView):
    model = Collateral
    template_name = 'collateral_management/collateral_detail.html'
    context_object_name = 'collateral'


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
def add_collateral_with_campaign(request):
    """
    One-page “Add Collateral” wizard that also links it to a Brand-Campaign.
    """
    if request.method == "POST":
        form = CollateralForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                collateral = form.save(commit=False)
                collateral.created_by = request.user
                collateral.is_active = True  # Ensure collateral is active by default
                # Correct: read from the proper purpose field
                collateral.purpose = form.cleaned_data.get('purpose')
                collateral.save()
                CampaignCollateral.objects.create(
                    campaign=collateral.campaign,  # Use campaign from form
                    collateral=collateral,
                )
            messages.success(request, "Collateral created & linked ✔︎")
            return redirect("collateral_list")
    else:
        form = CollateralForm()

    return render(
        request,
        "collateral_management/add_collateral_combined.html",
        {
            "collateral_form": form,
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
    # First try to get from campaign_management.Collateral
    try:
        from campaign_management.models import Collateral as CampaignCollateral
        import pandas as pd
        import os
        
        # Check if this is a CSV ID (from submissions.csv)
        csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'submissions.csv')
        try:
            df = pd.read_csv(csv_path)
        except FileNotFoundError:
            # If file not found, create an empty DataFrame to avoid errors
            df = pd.DataFrame(columns=['id', 'ItemName', 'Brand_Campaign_ID'])
            print(f"Warning: submissions.csv not found at {csv_path}")
        except Exception as e:
            # For any other error, create an empty DataFrame
            df = pd.DataFrame(columns=['id', 'ItemName', 'Brand_Campaign_ID'])
            print(f"Error reading submissions.csv: {e}")
        
        # Try to find the collateral by CSV ID first
        csv_row = df[df['id'] == pk]
        if not csv_row.empty:
            # Found CSV ID, now find the corresponding Campaign Management collateral
            item_name = csv_row.iloc[0]['ItemName']
            brand_campaign_id = csv_row.iloc[0]['Brand_Campaign_ID']
            
            # Find the campaign first
            from campaign_management.models import Campaign
            campaign = Campaign.objects.filter(brand_campaign_id=brand_campaign_id).first()
            
            if campaign:
                # Find the collateral in Campaign Management table
                collateral = CampaignCollateral.objects.filter(item_name=item_name).first()
                if collateral:
                    # Found the collateral, continue with the rest of the function
                    pass
                else:
                    # Fallback to direct ID lookup
                    collateral = get_object_or_404(CampaignCollateral, pk=pk)
            else:
                # Fallback to direct ID lookup
                collateral = get_object_or_404(CampaignCollateral, pk=pk)
        else:
            # Not a CSV ID, try direct lookup
            collateral = get_object_or_404(CampaignCollateral, pk=pk)
        
        # Get the campaign information for this collateral
        from campaign_management.models import CampaignCollateral as CampaignCollateralLink
        campaign_link = CampaignCollateralLink.objects.filter(collateral=collateral).first()
        campaign_id = campaign_link.campaign.brand_campaign_id if campaign_link else 'Unknown'
        
        # Define the form class once
        from django import forms
        class SimpleCollateralForm(forms.ModelForm):
            # Add extra fields to match the original form
            campaign = forms.CharField(
                max_length=255,
                required=False,
                widget=forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
                label="Brand Campaign ID"
            )
            title = forms.ChoiceField(
                choices=[('', 'Select Purpose of the Collateral')] + [
                    ('Doctor education short', 'Doctor education short'),
                    ('Doctor education long', 'Doctor education long'),
                    ('Patient education compliance', 'Patient education compliance'),
                    ('Patient education general', 'Patient education general'),
                ],
                widget=forms.Select(attrs={'class': 'form-select'}),
                required=True,
                label="Purpose of the Collateral"
            )
            type = forms.ChoiceField(
                choices=[('', 'Select Type')] + [
                    ('pdf', 'PDF'),
                    ('video', 'Video'),
                ],
                widget=forms.Select(attrs={'class': 'form-select'}),
                required=True,
                label="Item Type"
            )
            vimeo_url = forms.URLField(
                required=False,
                widget=forms.URLInput(attrs={'class': 'form-control'}),
                label="Video URL"
            )
            content_id = forms.CharField(
                max_length=100,
                required=False,
                widget=forms.TextInput(attrs={'class': 'form-control'}),
                label="Item Name"
            )
            banner_1 = forms.ImageField(
                required=False,
                widget=forms.FileInput(attrs={'class': 'form-control'}),
                label="Banner 1"
            )
            banner_2 = forms.ImageField(
                required=False,
                widget=forms.FileInput(attrs={'class': 'form-control'}),
                label="Banner 2"
            )
            is_active = forms.BooleanField(
                required=False,
                initial=True,
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
                label="Is Active"
            )
            
            class Meta:
                model = CampaignCollateral
                fields = ['item_name', 'description', 'file']
                widgets = {
                    'item_name': forms.TextInput(attrs={'class': 'form-control'}),
                    'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                    'file': forms.FileInput(attrs={'class': 'form-control'}),
                }
        
        # Set initial values for the form fields
        initial_data = {
            'campaign': campaign_id,
            'title': 'Doctor education short',  # Default value
            'type': 'pdf',  # Default value
            'content_id': collateral.item_name,  # Use item_name as content_id
            'description': collateral.description,
            'is_active': True,
        }
        
        if request.method == 'POST':
            form = SimpleCollateralForm(request.POST, request.FILES, instance=collateral, initial=initial_data)
            if form.is_valid():
                form.save()
                messages.success(request, 'Collateral replaced successfully!')
                return redirect('fieldrep_dashboard')
        else:
            form = SimpleCollateralForm(instance=collateral, initial=initial_data)
        
        return render(request, 'collateral_management/replace_collateral_simple.html', {'form': form, 'collateral': collateral})
    except:
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
        return render(request, 'collateral_management/replace_collateral.html', {'form': form, 'collateral': collateral})

def dashboard_delete_collateral(request, pk):
    from django.shortcuts import get_object_or_404, redirect
    from .models import Collateral
    if request.method == "POST":
        collateral = get_object_or_404(Collateral, pk=pk)
        collateral.delete()
        return redirect('/share/dashboard/')
    return redirect('/share/dashboard/')