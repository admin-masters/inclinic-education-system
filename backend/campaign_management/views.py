# campaign_management/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy, reverse
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django import forms
from django.db.models import Q
from django.core.paginator import Paginator
import uuid
import re

from .models import Campaign, CampaignAssignment, CampaignCollateral
from .forms import CampaignForm, CampaignAssignmentForm, CampaignCollateralForm, CampaignSearchForm, CampaignFilterForm
from .decorators import admin_required
from user_management.models import User

# ------------------------------------------------------------------------
# Campaign List (open to all roles to see a list, but optional restrict)
# ------------------------------------------------------------------------
class CampaignListView(ListView):
    model = Campaign
    template_name = 'campaign_management/campaign_list.html'
    context_object_name = 'campaigns'
    ordering = ['-created_at']  # most recent first
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Handle search functionality
        search_form = CampaignSearchForm(self.request.GET)
        if search_form.is_valid():
            brand_campaign_id = search_form.cleaned_data.get('brand_campaign_id')
            name = search_form.cleaned_data.get('name')
            brand_name = search_form.cleaned_data.get('brand_name')
            status = search_form.cleaned_data.get('status')
            
            if brand_campaign_id:
                queryset = queryset.filter(brand_campaign_id__icontains=brand_campaign_id)
            if name:
                queryset = queryset.filter(name__icontains=name)
            if brand_name:
                queryset = queryset.filter(brand_name__icontains=brand_name)
            if status:
                queryset = queryset.filter(status=status)
        
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_form'] = CampaignSearchForm(self.request.GET)
        context['total_campaigns'] = self.get_queryset().count()
        return context


# ------------------------------------------------------------------------
# View Campaign Details
# ------------------------------------------------------------------------
class CampaignDetailView(DetailView):
    model = Campaign
    template_name = 'campaign_management/campaign_detail.html'
    context_object_name = 'campaign'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        campaign = self.get_object()
        
        # Add related data to context
        context['assignments'] = CampaignAssignment.objects.filter(campaign=campaign).select_related('field_rep')
        context['collaterals'] = CampaignCollateral.objects.filter(campaign=campaign).select_related('collateral')
        
        return context


# ------------------------------------------------------------------------
# Create Campaign (now available to any authenticated user)
# ------------------------------------------------------------------------
@method_decorator(login_required, name='dispatch')
class CampaignCreateView(CreateView):
    model = Campaign
    form_class = CampaignForm
    template_name = 'campaign_management/campaign_create.html'
    success_url = reverse_lazy('manage_data_panel')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['initial'] = {
            'status': 'draft',  # Default status for new campaigns
        }
        return kwargs

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        
        # Safety: ensure brand_campaign_id is set even if form did not include it
        if not getattr(form.instance, 'brand_campaign_id', None):
            base = (form.cleaned_data.get('brand_name') or form.cleaned_data.get('name') or 'CMP')
            base = re.sub(r'[^A-Za-z0-9]+', '-', base).strip('-').upper()[:12]
            if not base:
                base = 'CMP'
            form.instance.brand_campaign_id = f"{base}-{uuid.uuid4().hex[:6].upper()}"
        
        resp = super().form_valid(form)
        messages.success(self.request, f"Campaign created. Brand–Campaign ID: {self.object.brand_campaign_id}")
        return resp

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return super().form_invalid(form)


# ------------------------------------------------------------------------
# Update Campaign (any authenticated user)
# ------------------------------------------------------------------------
@method_decorator(login_required, name='dispatch')
class CampaignUpdateView(UpdateView):
    model = Campaign
    form_class = CampaignForm
    template_name = 'campaign_management/campaign_update.html'
    success_url = reverse_lazy('manage_data_panel')

    def form_valid(self, form):
        messages.success(self.request, f"Campaign '{form.instance.name}' updated successfully!")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return super().form_invalid(form)


# ------------------------------------------------------------------------
# Delete Campaign (any authenticated user)
# ------------------------------------------------------------------------
@method_decorator(login_required, name='dispatch')
class CampaignDeleteView(DeleteView):
    model = Campaign
    template_name = 'campaign_management/campaign_delete.html'
    success_url = reverse_lazy('manage_data_panel')

    def delete(self, request, *args, **kwargs):
        campaign = self.get_object()
        messages.success(request, f"Campaign '{campaign.name}' deleted successfully!")
        return super().delete(request, *args, **kwargs)


# ------------------------------------------------------------------------
# Campaign Reports/Filter View
# ------------------------------------------------------------------------
@admin_required
def campaign_reports(request):
    campaigns = Campaign.objects.all().order_by('-created_at')
    filter_form = CampaignFilterForm(request.GET)
    
    if filter_form.is_valid():
        start_date = filter_form.cleaned_data.get('start_date')
        end_date = filter_form.cleaned_data.get('end_date')
        status = filter_form.cleaned_data.get('status')
        
        if start_date:
            campaigns = campaigns.filter(start_date__gte=start_date)
        if end_date:
            campaigns = campaigns.filter(end_date__lte=end_date)
        if status:
            campaigns = campaigns.filter(status=status)
    
    # Pagination
    paginator = Paginator(campaigns, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'campaigns': page_obj,
        'filter_form': filter_form,
        'total_campaigns': campaigns.count(),
    }
    
    return render(request, 'campaign_management/campaign_reports.html', context)


@login_required
def manage_data_panel(request):
    campaigns = Campaign.objects.all().order_by('-start_date')
    return render(request, 'campaign_management/manage_data_panel.html', {
        'campaigns': campaigns,
    })


# ------------------------------------------------------------------------
# Assign Field Reps to a Campaign
# ------------------------------------------------------------------------
# @admin_required

def assign_field_reps(request, pk):
    """
    Show current assignments, allow admin to add new Field Rep or remove existing.
    """
    campaign = get_object_or_404(Campaign, pk=pk)

    if request.method == 'POST':
        form = CampaignAssignmentForm(request.POST)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.campaign = campaign
            assignment.assigned_by = request.user

            from admin_dashboard.models import FieldRepCampaign

            if not CampaignAssignment.objects.filter(campaign=campaign, field_rep=assignment.field_rep).exists():
                assignment.save()
                FieldRepCampaign.objects.get_or_create(field_rep=assignment.field_rep, campaign=campaign)
                messages.success(request, f"Field Rep '{assignment.field_rep.get_full_name()}' assigned successfully.")
            else:
                messages.warning(request, "That Field Rep is already assigned to this campaign.")
            # redirect to filtered field rep list for this brand campaign id
            url = f"{reverse('admin_dashboard:fieldrep_list')}?campaign={campaign.brand_campaign_id}"
            return redirect(url)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CampaignAssignmentForm()
        form.fields['campaign'].initial = campaign.id
        form.fields['campaign'].widget = forms.HiddenInput()

    assignments = CampaignAssignment.objects.filter(campaign=campaign).select_related('field_rep')

    return render(request, 'campaign_management/assign_field_reps.html', {
        'campaign': campaign,
        'form': form,
        'assignments': assignments
    })


# ------------------------------------------------------------------------
# Remove Field Rep Assignment
# ------------------------------------------------------------------------
# @admin_required

def remove_field_rep(request, pk, assignment_id):
    """
    Remove an assignment.
    """
    campaign = get_object_or_404(Campaign, pk=pk)
    assignment = get_object_or_404(CampaignAssignment, pk=assignment_id, campaign=campaign)
    field_rep = assignment.field_rep

    from admin_dashboard.models import FieldRepCampaign

    assignment.delete()
    FieldRepCampaign.objects.filter(field_rep=field_rep, campaign=campaign).delete()
    messages.success(request, f"Field Rep '{field_rep.get_full_name()}' unassigned successfully.")
    # redirect to filtered field rep list for this brand campaign id
    url = f"{reverse('admin_dashboard:fieldrep_list')}?campaign={campaign.brand_campaign_id}"
    return redirect(url)


# ------------------------------------------------------------------------
# Edit Collateral Dates
# ------------------------------------------------------------------------
@login_required
def edit_collateral_dates(request, pk):
    campaign_collateral = get_object_or_404(CampaignCollateral, pk=pk)
    
    # Check if user has permission to edit this collateral
    if not request.user.is_admin and campaign_collateral.campaign.created_by != request.user:
        messages.error(request, "You don't have permission to edit this collateral.")
        return redirect('campaign_list')
    
    if request.method == 'POST':
        form = CampaignCollateralForm(request.POST, instance=campaign_collateral)
        if form.is_valid():
            form.save()
            messages.success(request, "Collateral dates updated successfully.")
            return redirect('campaign_detail', pk=campaign_collateral.campaign.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CampaignCollateralForm(instance=campaign_collateral)
    
    return render(request, 'campaign_management/edit_collateral_dates.html', {
        'form': form,
        'campaign_collateral': campaign_collateral
    })


# ------------------------------------------------------------------------
# Add Collateral to Campaign
# ------------------------------------------------------------------------
@login_required
def add_campaign_collateral(request, campaign_pk):
    campaign = get_object_or_404(Campaign, pk=campaign_pk)
    
    # Check if user has permission to add collateral
    if not request.user.is_admin and campaign.created_by != request.user:
        messages.error(request, "You don't have permission to add collateral to this campaign.")
        return redirect('campaign_list')
    
    if request.method == 'POST':
        form = CampaignCollateralForm(request.POST)
        if form.is_valid():
            collateral = form.save(commit=False)
            collateral.campaign = campaign
            collateral.save()
            messages.success(request, "Collateral added to campaign successfully.")
            return redirect('campaign_detail', pk=campaign.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CampaignCollateralForm()
    
    return render(request, 'campaign_management/add_campaign_collateral.html', {
        'form': form,
        'campaign': campaign
    })


# ------------------------------------------------------------------------
# Remove Collateral from Campaign
# ------------------------------------------------------------------------
@login_required
def remove_campaign_collateral(request, pk):
    campaign_collateral = get_object_or_404(CampaignCollateral, pk=pk)
    campaign_pk = campaign_collateral.campaign.pk
    
    # Check if user has permission to remove collateral
    if not request.user.is_admin and campaign_collateral.campaign.created_by != request.user:
        messages.error(request, "You don't have permission to remove this collateral.")
        return redirect('campaign_list')
    
    campaign_collateral.delete()
    messages.success(request, "Collateral removed from campaign successfully.")
    return redirect('campaign_detail', pk=campaign_pk)


# ------------------------------------------------------------------------
# Campaign Dashboard
# ------------------------------------------------------------------------
@login_required
def campaign_dashboard(request):
    total_campaigns = Campaign.objects.count()
    active_campaigns = Campaign.objects.filter(status='active').count()
    draft_campaigns = Campaign.objects.filter(status='draft').count()
    completed_campaigns = Campaign.objects.filter(status='completed').count()
    
    # Recent campaigns
    recent_campaigns = Campaign.objects.all().order_by('-created_at')[:5]
    
    # Campaigns needing attention (ending in next 7 days)
    from django.utils import timezone
    from datetime import timedelta
    week_from_now = timezone.now() + timedelta(days=7)
    ending_soon = Campaign.objects.filter(
        end_date__lte=week_from_now, 
        end_date__gte=timezone.now(),
        status='active'
    )
    
    context = {
        'total_campaigns': total_campaigns,
        'active_campaigns': active_campaigns,
        'draft_campaigns': draft_campaigns,
        'completed_campaigns': completed_campaigns,
        'recent_campaigns': recent_campaigns,
        'ending_soon': ending_soon,
    }
    
    return render(request, 'campaign_management/campaign_dashboard.html', context)


# ------------------------------------------------------------------------
# Quick Campaign Status Update
# ------------------------------------------------------------------------
@login_required
def quick_update_status(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    
    # Check if user has permission to update status
    if not request.user.is_admin and campaign.created_by != request.user:
        messages.error(request, "You don't have permission to update this campaign's status.")
        return redirect('campaign_list')
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(Campaign.STATUS_CHOICES):
            old_status = campaign.status
            campaign.status = new_status
            campaign.save()
            messages.success(request, f"Campaign status updated from {old_status} to {new_status}.")
        else:
            messages.error(request, "Invalid status selected.")
    
    return redirect('campaign_detail', pk=campaign.pk)