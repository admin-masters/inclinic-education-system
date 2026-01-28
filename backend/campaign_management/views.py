# campaign_management/views.py
from django.http import HttpResponseBadRequest, HttpResponse
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

from django.conf import settings
from django.db import connections

from .master_models import MasterCampaign
from .publisher_auth import publisher_or_login_required

from .models import Campaign, CampaignAssignment, CampaignCollateral
from .forms import CampaignForm, CampaignAssignmentForm, CampaignCollateralForm, CampaignSearchForm, CampaignFilterForm
from .decorators import admin_required
from user_management.models import User
from .publisher_auth import (
    establish_publisher_session,
    extract_jwt_from_request,
    publisher_or_login_required,
    publisher_session_required,
    validate_publisher_jwt,
)
from .master_models import MasterCampaign

import logging

logger = logging.getLogger(__name__)


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
@method_decorator(publisher_or_login_required, name="dispatch")
class CampaignCreateView(CreateView):
    model = Campaign
    form_class = CampaignForm
    template_name = "campaign_management/campaign_create.html"

    def _get_campaign_id(self):
        return (
            self.request.POST.get("campaign-id")
            or self.request.POST.get("campaign_id")
            or self.request.GET.get("campaign-id")
            or self.request.GET.get("campaign_id")
            or self.request.session.get("publisher_campaign_id")
        )

    def dispatch(self, request, *args, **kwargs):
        self.passed_campaign_id = self._get_campaign_id()

        # If campaign already exists in default DB, go to update instead of crashing on unique constraint
        if self.passed_campaign_id:
            request.session["publisher_campaign_id"] = self.passed_campaign_id
            if Campaign.objects.filter(brand_campaign_id=self.passed_campaign_id).exists():
                return redirect("publisher_campaign_update", campaign_id=self.passed_campaign_id)

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.setdefault("initial", {})
        kwargs["initial"].setdefault("status", "Draft")
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["campaign_id"] = self.passed_campaign_id
        return context

    def form_valid(self, form):
        campaign_id = self._get_campaign_id()
        if not campaign_id:
            return HttpResponseBadRequest("Missing campaign-id")

        # Use campaign-id from master system, do NOT generate
        form.instance.brand_campaign_id = campaign_id

        # Insert NULL for master-owned fields (per requirement)
        # Insert empty values for master-owned fields (DB-safe)
        form.instance.company_name = ""
        form.instance.incharge_name = ""
        form.instance.incharge_contact = ""
        form.instance.num_doctors = 0
        form.instance.brand_name = ""

        if self.request.user.is_authenticated:
            form.instance.created_by = self.request.user

        return super().form_valid(form)

    def get_success_url(self):
        # For publisher flow, go directly to edit screen
        if self.passed_campaign_id or self.request.session.get("publisher_authenticated"):
            return reverse("publisher_campaign_update", kwargs={"campaign_id": self.object.brand_campaign_id})
        return reverse("manage_data_panel")



# ------------------------------------------------------------------------
# Update Campaign (any authenticated user)
# ------------------------------------------------------------------------
# @method_decorator(publisher_or_login_required, name="dispatch")
class CampaignUpdateView(UpdateView):
    model = Campaign
    form_class = CampaignForm
    template_name = "campaign_management/campaign_update.html"
    context_object_name = "campaign"

    def get_queryset(self):
        # FORCE default DB
        return Campaign.objects.using("default")

    # Only these are editable in PE system
    EDITABLE_FIELDS = [
        "name",
        "incharge_designation",
        "items_per_clinic_per_year",
        "start_date",
        "end_date",
        "contract",
        "brand_logo",
        "company_logo",
        "printing_required",
        "description",
        "status",
    ]

    def dispatch(self, request, *args, **kwargs):
        self.publisher_campaign_id = kwargs.get("campaign_id")

        # If publisher tries to edit a campaign that doesn't exist in default DB yet, route to create.
        if self.publisher_campaign_id and not Campaign.objects.using("default").filter(
                brand_campaign_id=self.publisher_campaign_id
        ).exists():
            return redirect(f"{reverse('campaign_create')}?campaign-id={self.publisher_campaign_id}")

        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        # Publisher route uses campaign-id, not pk
        campaign_id = self.kwargs.get("campaign_id")
        if campaign_id:
            return get_object_or_404(
                Campaign.objects.using("default"),
                brand_campaign_id=campaign_id
            )

        # Admin/internal route: existing pk behavior
        return super().get_object(queryset)

    def _fetch_master_campaign(self):
        campaign_id = self.object.brand_campaign_id

        # Must be a UUID string
        if not isinstance(campaign_id, str):
            return None

        try:
            campaign_uuid = uuid.UUID(campaign_id)
        except (ValueError, TypeError):
            return None

        return (
            MasterCampaign.objects
            .using("master")
            .select_related("brand")
            .filter(pk=campaign_uuid)
            .first()
        )

    def _fetch_master_company_name(self, master_campaign):
        """
        Company name isn't present in your provided master Campaign model snippet.
        This attempts to fetch Brand.company_name from master DB if it exists.
        If your schema differs, set MASTER_BRAND_DB_TABLE and/or adjust this query.
        """
        if not master_campaign or not getattr(master_campaign, "brand_id", None):
            return None

        brand_table = getattr(settings, "MASTER_BRAND_DB_TABLE", "Brand")
        conn = connections["master"]
        quoted_table = conn.ops.quote_name(brand_table)

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT company_name FROM {quoted_table} WHERE id = %s",
                    [str(master_campaign.brand_id)],
                )
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception:
            return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        master_campaign = self._fetch_master_campaign()

        context["master_fields"] = {
            "Brand–Campaign ID": self.object.brand_campaign_id,
            "Brand name": getattr(master_campaign, "name", None),
            "Company name": None,
            "Incharge name": getattr(master_campaign, "contact_person_name", None),
            "Incharge contact": getattr(master_campaign, "contact_person_phone", None),
            "Num doctors": getattr(master_campaign, "num_doctors_supported", None),
        }
        return context

    def form_valid(self, form):
        # Save only editable fields to DEFAULT DB row
        self.object = form.save(commit=False)
        self.object.save(
            using="default",
            update_fields=self.EDITABLE_FIELDS
        )
        return redirect(self.get_success_url())

    def get_success_url(self):
        if self.kwargs.get("campaign_id") or self.request.session.get("publisher_authenticated"):
            return reverse("publisher_campaign_update", kwargs={"campaign_id": self.object.brand_campaign_id})
        return reverse("manage_data_panel")

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
        else:
            messages.error(request, "Invalid status selected.")
    
    return redirect('campaign_detail', pk=campaign.pk)


def publisher_landing_page(request):
    logger.info("publisher_landing_page: request started")
    logger.info("Path=%s Method=%s", request.path, request.method)
    logger.info("GET params=%s", dict(request.GET))
    logger.info("Session key=%s", request.session.session_key)
    logger.info("Session data BEFORE=%s", dict(request.session))

    token, source = extract_jwt_from_request(request)
    logger.info("JWT extracted=%s source=%s", bool(token), source)

    # ---- First hit: token-based bootstrap ----
    if token:
        try:
            logger.info("Validating publisher JWT")
            payload = validate_publisher_jwt(token)
            logger.info(
                "JWT valid: sub=%s username=%s roles=%s exp=%s",
                payload.get("sub"),
                payload.get("username"),
                payload.get("roles"),
                payload.get("exp"),
            )
        except Exception as e:
            logger.exception("JWT validation failed")
            return HttpResponse("unauthorised access", status=401)

        establish_publisher_session(request, payload)
        logger.info(
            "Session established: authenticated=%s username=%s",
            request.session.get("publisher_authenticated"),
            request.session.get("publisher_username"),
        )
        logger.info("Session data AFTER establish=%s", dict(request.session))

        # Strip token from URL
        if source == "query_string":
            params = request.GET.copy()
            for k in ("jwt", "token", "access_token"):
                params.pop(k, None)
            url = request.path
            if params:
                url += "?" + params.urlencode()

            logger.info("Redirecting to clean URL: %s", url)
            return redirect(url)

    # ---- No token: rely on session ----
    logger.info(
        "Checking publisher session: authenticated=%s",
        request.session.get("publisher_authenticated"),
    )

    if not request.session.get("publisher_authenticated"):
        logger.warning("No publisher session found, retrying token extraction")

        token, source = extract_jwt_from_request(request)
        logger.info("Retry extract JWT: found=%s source=%s", bool(token), source)

        if not token:
            logger.error("Unauthorized: no token and no session")
            return HttpResponse("unauthorised access", status=401)

        try:
            payload = validate_publisher_jwt(token)
            establish_publisher_session(request, payload)
            logger.info("Session established on retry")
        except Exception:
            logger.exception("JWT validation failed on retry")
            return HttpResponse("unauthorised access", status=401)

    campaign_id = request.GET.get("campaign-id") or request.GET.get("campaign_id")
    logger.info("campaign_id=%s", campaign_id)

    if not campaign_id:
        logger.error("Missing campaign-id")
        return HttpResponseBadRequest("Missing campaign-id")

    request.session["publisher_campaign_id"] = campaign_id
    request.session.modified = True

    logger.info("Rendering landing page")
    logger.info("FINAL session data=%s", dict(request.session))

    return render(
        request,
        "campaign_management/publisher_landing_page.html",
        {
            "campaign_id": campaign_id,
            "publisher_username": request.session.get("publisher_username", ""),
        },
    )



@publisher_session_required
def publisher_campaign_select(request):
    """
    Simple “enter another campaign-id” page for publishers.
    """
    if request.method == "POST":
        campaign_id = request.POST.get("campaign-id") or request.POST.get("campaign_id")
        if not campaign_id:
            return HttpResponseBadRequest("Missing campaign-id")
        return redirect("publisher_campaign_update", campaign_id=campaign_id)

    return render(request, "campaign_management/publisher_campaign_select.html")
