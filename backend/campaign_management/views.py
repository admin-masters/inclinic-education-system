# campaign_management/views.py
from django.http import HttpResponseBadRequest, HttpResponse, Http404
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


from django.contrib import messages
from django.urls import reverse


from .master_models import MasterCampaign, MasterBrand

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
from campaign_management.master_models import MasterCampaign

import logging

logger = logging.getLogger(__name__)

import uuid
from django.shortcuts import get_object_or_404
from django.views.generic import DetailView
from .models import Campaign

def normalize_campaign_id(value: str) -> str:
    """
    Returns a dashed UUID string if value looks like a UUID (dashed or dashless).
    Otherwise returns the original string.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    try:
        return str(uuid.UUID(s))  # works for dashed + dashless
    except Exception:
        return s

from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.views.generic import DetailView

from .models import Campaign


@method_decorator(login_required, name="dispatch")
class CampaignDetailByCampaignIdView(DetailView):
    """
    Canonical detail view using brand_campaign_id from the URL.
    If campaign row does not exist yet in DEFAULT DB, redirect to edit/create flow.
    """
    model = Campaign
    template_name = "campaign_management/campaign_detail.html"
    context_object_name = "campaign"

    def get_queryset(self):
        # Always read from PE DB
        return Campaign.objects.using("default")

    def dispatch(self, request, *args, **kwargs):
        campaign_id = kwargs.get("campaign_id")
        if not campaign_id:
            return HttpResponseBadRequest("Missing campaign-id")

        # If not yet created in default DB, send user to edit route
        if not Campaign.objects.using("default").filter(brand_campaign_id=campaign_id).exists():
            return redirect("campaign_by_id_update", campaign_id=campaign_id)

        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        campaign_id = self.kwargs.get("campaign_id")
        return get_object_or_404(
            Campaign.objects.using("default"),
            brand_campaign_id=campaign_id,
        )



# ------------------------------------------------------------------------
# Master DB helpers (read-only fields always come from "master")
# ------------------------------------------------------------------------

_UUID_HEX_32_RE = re.compile(r"^[0-9a-fA-F]{32}$")

MASTER_READONLY_FORM_FIELDS = [
    "brand_name",
    "company_name",
    "incharge_name",
    "incharge_contact",
    "num_doctors",
]


def normalize_master_campaign_id(value):
    """
    Returns dashless 32-hex string if value is UUID-like.
    Otherwise returns None (for legacy/non-UUID campaign IDs).
    """
    if not value:
        return None

    if isinstance(value, uuid.UUID):
        return value.hex

    s = str(value).strip()
    # Already dashless?
    if _UUID_HEX_32_RE.match(s):
        return s.lower()

    # Try dashed UUID -> dashless
    try:
        return uuid.UUID(s).hex
    except (ValueError, TypeError):
        # Try stripping dashes/braces
        s2 = s.replace("-", "").replace("{", "").replace("}", "")
        if _UUID_HEX_32_RE.match(s2):
            return s2.lower()

    return None


def uuid_dashed_from_dashless(dashless_32):
    """32-hex -> dashed UUID string."""
    return str(uuid.UUID(hex=dashless_32))


def campaign_id_variants(value):
    """
    Used to match existing default rows regardless of dashed/dashless input.
    Returns a de-duplicated list: [raw, dashless, dashed] when UUID-like.
    """
    raw = "" if value is None else str(value).strip()
    dashless = normalize_master_campaign_id(raw)
    if not dashless:
        return [raw]

    dashed = uuid_dashed_from_dashless(dashless)
    return list({raw, dashless, dashed})


def fetch_company_names_for_brand_ids(brand_ids):
    """
    Bulk fetch {brand_id: company_name} from master Brand table.
    Uses raw SQL because MasterBrand model may not include company_name field.
    """
    brand_ids = [b for b in set(brand_ids) if b]
    if not brand_ids:
        return {}

    conn = connections["master"]
    table = MasterBrand._meta.db_table
    quoted_table = conn.ops.quote_name(table)

    placeholders = ",".join(["%s"] * len(brand_ids))
    sql = f"SELECT id, company_name FROM {quoted_table} WHERE id IN ({placeholders})"

    out = {}
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, brand_ids)
            for brand_id, company_name in cursor.fetchall():
                out[str(brand_id)] = company_name
    except Exception:
        logger.exception("Error fetching company_name from master brand table")
    return out


def bulk_master_snapshots(brand_campaign_ids):
    """
    Returns a dict:
      {dashless_campaign_id: snapshot_dict}
    snapshot_dict keys:
      brand_name, company_name, incharge_name, incharge_contact, num_doctors
    """
    dashless_ids = []
    for bc_id in brand_campaign_ids:
        d = normalize_master_campaign_id(bc_id)
        if d:
            dashless_ids.append(d)

    dashless_ids = list(set(dashless_ids))
    if not dashless_ids:
        return {}

    master_qs = (
        MasterCampaign.objects.using("master")
        .select_related("brand")
        .filter(id__in=dashless_ids)
    )
    master_list = list(master_qs)

    brand_ids = [mc.brand_id for mc in master_list if getattr(mc, "brand_id", None)]
    company_map = fetch_company_names_for_brand_ids(brand_ids)

    snapshots = {}
    for mc in master_list:
        brand_obj = getattr(mc, "brand", None)
        snapshots[mc.id] = {
            "brand_name": getattr(brand_obj, "name", None),
            "company_name": company_map.get(str(getattr(mc, "brand_id", ""))),
            "incharge_name": getattr(mc, "contact_person_name", None),
            "incharge_contact": getattr(mc, "contact_person_phone", None),
            "num_doctors": getattr(mc, "num_doctors_supported", None),
        }
    return snapshots


def get_default_campaign_by_campaign_id(campaign_id):
    """
    Fetch Campaign from DEFAULT DB by matching brand_campaign_id against
    raw/dashless/dashed variants. Returns Campaign or None.
    """
    variants = campaign_id_variants(campaign_id)
    return (
        Campaign.objects.using("default")
        .filter(brand_campaign_id__in=variants)
        .order_by("-created_at")
        .first()
    )


# ------------------------------------------------------------------------
# Campaign List (open to all roles to see a list, but optional restrict)
# ------------------------------------------------------------------------
class CampaignListView(ListView):
    model = Campaign
    template_name = 'campaign_management/campaign_list.html'
    context_object_name = 'campaigns'
    ordering = ['-created_at']
    paginate_by = 20

    def get_queryset(self):
        queryset = Campaign.objects.using("default").all().order_by(*self.ordering)

        search_form = CampaignSearchForm(self.request.GET)
        if search_form.is_valid():
            brand_campaign_id = search_form.cleaned_data.get('brand_campaign_id')
            name = search_form.cleaned_data.get('name')
            brand_name = search_form.cleaned_data.get('brand_name')
            status = search_form.cleaned_data.get('status')

            if brand_campaign_id:
                # Match dashed/dashless variants when UUID-like
                variants = campaign_id_variants(brand_campaign_id)
                queryset = queryset.filter(
                    Q(brand_campaign_id__in=variants) |
                    Q(brand_campaign_id__icontains=brand_campaign_id)
                )

            if name:
                queryset = queryset.filter(name__icontains=name)

            if status:
                queryset = queryset.filter(status=status)

            # ✅ brand_name comes from MASTER DB
            if brand_name:
                master_ids = list(
                    MasterCampaign.objects.using("master")
                    .select_related("brand")
                    .filter(brand__name__icontains=brand_name)
                    .values_list("id", flat=True)
                )

                # default may store dashed or dashless depending on history → match both
                default_variants = set()
                for mid in master_ids:
                    default_variants.add(mid)
                    try:
                        default_variants.add(uuid_dashed_from_dashless(mid))
                    except Exception:
                        pass

                queryset = queryset.filter(brand_campaign_id__in=list(default_variants))

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        campaigns = context.get("campaigns", [])
        snapshots = bulk_master_snapshots([c.brand_campaign_id for c in campaigns])

        # attach convenience attributes (no DB writes)
        for c in campaigns:
            dashless = normalize_master_campaign_id(c.brand_campaign_id)
            snap = snapshots.get(dashless, {}) if dashless else {}
            c.master_brand_name = snap.get("brand_name")
            c.master_company_name = snap.get("company_name")
            c.master_incharge_name = snap.get("incharge_name")
            c.master_incharge_contact = snap.get("incharge_contact")
            c.master_num_doctors = snap.get("num_doctors")

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

    def get_queryset(self):
        return Campaign.objects.using("default")

    def get_object(self, queryset=None):
        # If you add the campaign_id URL (below), this supports it.
        campaign_id = self.kwargs.get("campaign_id")
        if campaign_id:
            obj = get_default_campaign_by_campaign_id(campaign_id)
            if not obj:
                raise Http404("Campaign not found in default DB")
            return obj
        return super().get_object(queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        campaign = self.get_object()

        context['assignments'] = (
            CampaignAssignment.objects.using("default")
            .filter(campaign=campaign)
            .select_related('field_rep')
        )
        context['collaterals'] = (
            CampaignCollateral.objects.using("default")
            .filter(campaign=campaign)
            .select_related('collateral')
        )

        snapshots = bulk_master_snapshots([campaign.brand_campaign_id])
        dashless = normalize_master_campaign_id(campaign.brand_campaign_id)
        snap = snapshots.get(dashless, {}) if dashless else {}

        context["master_fields"] = {
            "Brand–Campaign ID": campaign.brand_campaign_id,
            "Brand name": snap.get("brand_name"),
            "Company name": snap.get("company_name"),
            "Incharge name": snap.get("incharge_name"),
            "Incharge contact": snap.get("incharge_contact"),
            "Num doctors": snap.get("num_doctors"),
        }
        return context



def campaign_thank_you(request):
    """
    Thank-you landing page shown after a campaign is created/updated.
    """
    # If messages middleware is working, message will come from messages.success().
    # Fallback in case template doesn't render messages:
    default_message = "Thank you for adding/updating the brand"

    campaign_id = request.GET.get("campaign_id") or ""
    return render(
        request,
        "campaign_management/campaign_thank_you.html",
        {
            "campaign_id": campaign_id,
            "message": default_message,
        },
    )

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
        raw_id = self._get_campaign_id()
        # Canonicalize UUID-like IDs to dashless for storage/lookup consistency
        canon = normalize_master_campaign_id(raw_id) or raw_id
        self.passed_campaign_id = canon

        if canon:
            request.session["publisher_campaign_id"] = canon

            existing = get_default_campaign_by_campaign_id(canon)
            if existing:
                return redirect("publisher_campaign_update", campaign_id=existing.brand_campaign_id)

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.setdefault("initial", {})
        kwargs["initial"].setdefault("status", "Draft")

        # If CampaignForm includes master fields, show them read-only with master values
        if self.passed_campaign_id:
            dashless = normalize_master_campaign_id(self.passed_campaign_id)
            snap = bulk_master_snapshots([dashless]).get(dashless, {}) if dashless else {}
            kwargs["initial"].update({
                "brand_name": snap.get("brand_name") or "",
                "company_name": snap.get("company_name") or "",
                "incharge_name": snap.get("incharge_name") or "",
                "incharge_contact": snap.get("incharge_contact") or "",
                "num_doctors": snap.get("num_doctors") or 0,
            })

        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["campaign_id"] = self.passed_campaign_id

        dashless = normalize_master_campaign_id(self.passed_campaign_id)
        snap = bulk_master_snapshots([dashless]).get(dashless, {}) if dashless else {}

        context["master_fields"] = {
            "Brand–Campaign ID": self.passed_campaign_id,
            "Brand name": snap.get("brand_name"),
            "Company name": snap.get("company_name"),
            "Incharge name": snap.get("incharge_name"),
            "Incharge contact": snap.get("incharge_contact"),
            "Num doctors": snap.get("num_doctors"),
        }
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Make master fields read-only IF they exist in the form
        for f in MASTER_READONLY_FORM_FIELDS:
            if f in form.fields:
                form.fields[f].disabled = True
                form.fields[f].required = False
        return form

    def form_valid(self, form):
        campaign_id = self._get_campaign_id()
        if not campaign_id:
            return HttpResponseBadRequest("Missing campaign-id")

        canon = normalize_master_campaign_id(campaign_id) or campaign_id

        # ✅ Use canonical ID for default DB row
        form.instance.brand_campaign_id = canon

        # ✅ Master-owned fields must NOT be persisted in default (keep empty/0)
        form.instance.company_name = ""
        form.instance.incharge_name = ""
        form.instance.incharge_contact = ""
        form.instance.num_doctors = 0
        form.instance.brand_name = ""

        if self.request.user.is_authenticated:
            form.instance.created_by = self.request.user


        response = super().form_valid(form)

        # ✅ success message
        messages.success(self.request, "Thank you for adding/updating the brand")
        return response

    def get_success_url(self):
        """
        After creating the default-db Campaign row, redirect to canonical edit-by-campaign-id page.
        This prevents Django from trying to call model.get_absolute_url().
        """
        campaign_id = getattr(self.object, "brand_campaign_id", None)
        if campaign_id:
            return reverse("campaign_by_id_update", kwargs={"campaign_id": str(campaign_id)})
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

    def get_queryset(self):
        return Campaign.objects.using("default")

    def dispatch(self, request, *args, **kwargs):
        campaign_id = kwargs.get("campaign_id")
        if campaign_id:
            existing = get_default_campaign_by_campaign_id(campaign_id)
            if not existing:
                canon = normalize_master_campaign_id(campaign_id) or campaign_id
                return redirect(f"{reverse('campaign_create')}?campaign-id={canon}")
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        campaign_id = self.kwargs.get("campaign_id")
        if campaign_id:
            obj = get_default_campaign_by_campaign_id(campaign_id)
            if not obj:
                raise Http404("Campaign not found in default DB")
            return obj
        return super().get_object(queryset)

    def _get_master_snapshot(self):
        if hasattr(self, "_master_snapshot_cache"):
            return self._master_snapshot_cache

        dashless = normalize_master_campaign_id(self.object.brand_campaign_id)
        snap = bulk_master_snapshots([dashless]).get(dashless, {}) if dashless else {}
        self._master_snapshot_cache = snap
        return snap

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        snap = self._get_master_snapshot()

        # Make master fields read-only IF they exist in the form
        initial_map = {
            "brand_name": snap.get("brand_name") or "",
            "company_name": snap.get("company_name") or "",
            "incharge_name": snap.get("incharge_name") or "",
            "incharge_contact": snap.get("incharge_contact") or "",
            "num_doctors": snap.get("num_doctors") or 0,
        }
        for f in MASTER_READONLY_FORM_FIELDS:
            if f in form.fields:
                form.fields[f].disabled = True
                form.fields[f].required = False
                form.initial[f] = initial_map.get(f, form.initial.get(f))
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        snap = self._get_master_snapshot()

        context["master_fields"] = {
            "Brand–Campaign ID": self.object.brand_campaign_id,
            "Brand name": snap.get("brand_name"),
            "Company name": snap.get("company_name"),
            "Incharge name": snap.get("incharge_name"),
            "Incharge contact": snap.get("incharge_contact"),
            "Num doctors": snap.get("num_doctors"),
        }
        return context

    def form_valid(self, form):
        # Save only editable fields to DEFAULT DB row
        self.object = form.save(commit=False)
        self.object.save(using="default", update_fields=self.EDITABLE_FIELDS)

        # ✅ success message
        messages.success(self.request, "Thank you for adding/updating the brand")

        # ✅ redirect to thank-you
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


from django.contrib.auth.decorators import login_required
from django.db import connections
from django.conf import settings

from .master_models import MasterCampaign
from .models import Campaign

def _fetch_company_names_for_brand_ids(brand_ids):
    """
    Batch fetch company_name for brand_ids from master DB.
    """
    if not brand_ids:
        return {}

    brand_table = getattr(settings, "MASTER_BRAND_DB_TABLE", "campaign_brand")
    placeholders = ",".join(["%s"] * len(brand_ids))

    sql = f"SELECT id, company_name FROM {brand_table} WHERE id IN ({placeholders})"

    conn = connections["master"]
    with conn.cursor() as cursor:
        cursor.execute(sql, brand_ids)
        rows = cursor.fetchall()

    return {str(r[0]): r[1] for r in rows}

@login_required
def manage_data_panel(request):
    master_campaigns = (
        MasterCampaign.objects.using("master")
        .select_related("brand")
        .all()
    )

    # Normalize master campaign IDs into dashed UUIDs for default DB lookup + URLs
    normalized_campaign_ids = []
    brand_ids = []

    master_rows = []
    for mc in master_campaigns:
        cid = normalize_campaign_id(mc.id)  # dashed if uuid-like
        normalized_campaign_ids.append(cid)
        master_rows.append((cid, mc))
        if getattr(mc, "brand_id", None):
            brand_ids.append(str(mc.brand_id))

    company_by_brand_id = _fetch_company_names_for_brand_ids(list(set(brand_ids)))

    default_qs = Campaign.objects.using("default").filter(
        brand_campaign_id__in=normalized_campaign_ids
    )
    default_by_campaign_id = {c.brand_campaign_id: c for c in default_qs}

    campaigns = []
    for cid, mc in master_rows:
        dc = default_by_campaign_id.get(cid)

        campaigns.append({
            "brand_campaign_id": cid,

            # ✅ MASTER DB fields
            "brand_name": getattr(getattr(mc, "brand", None), "name", "") or "",
            "company_name": company_by_brand_id.get(str(getattr(mc, "brand_id", "")), "") or "",
            "incharge_name": getattr(mc, "contact_person_name", "") or "",
            "incharge_contact": getattr(mc, "contact_person_phone", "") or "",
            "num_doctors": getattr(mc, "num_doctors_supported", 0) or 0,

            # ✅ DEFAULT DB fields (editable ones)
            "name": getattr(dc, "name", "") if dc else "",
            "start_date": getattr(dc, "start_date", None) if dc else None,
            "end_date": getattr(dc, "end_date", None) if dc else None,
            "status": getattr(dc, "status", "") if dc else "",
            "has_default": bool(dc),
        })

    # 🔍 Apply search filter from query param
    q = request.GET.get("q", "").strip()
    if q:
        q_lower = q.lower()
        campaigns = [
            c for c in campaigns
            if q_lower in str(c.get("brand_campaign_id", "")).lower()
            or q_lower in str(c.get("brand_name", "")).lower()
            or q_lower in str(c.get("company_name", "")).lower()
        ]

    return render(request, "campaign_management/manage_data_panel.html", {"campaigns": campaigns})


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
