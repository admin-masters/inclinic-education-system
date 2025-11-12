from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    ListView, CreateView, UpdateView, DeleteView, View
)

from campaign_management.models import Campaign
from collateral_management.models import CampaignCollateral
from sharing_management.models import ShareLog
from doctor_viewer.models import DoctorEngagement, Doctor
from .forms import FieldRepBulkUploadForm, FieldRepForm, DoctorForm
from user_management.models import User
from admin_dashboard.models import FieldRepCampaign
from utils.recaptcha import recaptcha_required
from sharing_management.models import VideoTrackingLog

# ─────────────────────────────────────────────────────────
# MIXIN
# ─────────────────────────────────────────────────────────
class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff
    
    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('admin:login')
        else:
            # If user is authenticated but not staff, redirect to login
            return redirect('admin:login')
    
    login_url = reverse_lazy("admin:login")
    
    def get_success_url(self):
        # After successful login, redirect to field reps page
        return reverse_lazy("admin-dashboard:fieldrep_list")

# ─────────────────────────────────────────────────────────
# DASHBOARD (unchanged)
# ─────────────────────────────────────────────────────────
@staff_member_required
def dashboard(request):
    shares = ShareLog.objects.values('short_link__resource_id').annotate(share_cnt=Count('id'))
    pdfs   = DoctorEngagement.objects.filter(pdf_completed=True)\
              .values('short_link__resource_id').annotate(pdf_impr=Count('id'))
    vids   = DoctorEngagement.objects.filter(video_watch_percentage__gte=90)\
              .values('short_link__resource_id').annotate(vid_comp=Count('id'))

    # New: VideoTrackingLog-based stats
    video_logs = VideoTrackingLog.objects.filter(video_percentage='3')\
        .values('share_log__collateral_id').annotate(vid_comp=Count('id'))
    video_log_map = {v['share_log__collateral_id']: v['vid_comp'] for v in video_logs}

    share_map = {s['short_link__resource_id']: s['share_cnt'] for s in shares}
    pdf_map   = {p['short_link__resource_id']: p['pdf_impr'] for p in pdfs}
    vid_map   = {v['short_link__resource_id']: v['vid_comp'] for v in vids}

    stats = []
    for c in Campaign.objects.all():
        coll_ids = list(
            CampaignCollateral.objects.filter(campaign=c).values_list('collateral_id', flat=True)
        )
        for coll_id in coll_ids:
            stats.append({
                'campaign': c,
                'collateral_id': coll_id,
                'shares': share_map.get(coll_id, 0),
                'pdf_completions': pdf_map.get(coll_id, 0),
                'video_completions_old': vid_map.get(coll_id, 0),
                'video_completions_new': video_log_map.get(coll_id, 0),
            })
    return render(request, 'admin_dashboard/dashboard.html', {'stats': stats})

# ─────────────────────────────────────────────────────────
# BULK‑UPLOAD (unchanged)
# ─────────────────────────────────────────────────────────
@staff_member_required
@recaptcha_required
def bulk_upload_fieldreps(request):
    if request.method == "POST":
        form = FieldRepBulkUploadForm(request.POST, request.FILES)
        if form.is_valid():
            created, updated, errors = form.save(request.user)
            messages.success(request, f"Created {created}, updated {updated}.")
            for err in errors:
                messages.warning(request, err)
            return redirect("admin_dashboard:bulk_upload")
    else:
        form = FieldRepBulkUploadForm()
    return render(request, "admin_dashboard/bulk_upload.html", {"form": form})

# ─────────────────────────────────────────────────────────
# FIELD‑REP CRUD (unchanged)
# ─────────────────────────────────────────────────────────
class FieldRepListView(StaffRequiredMixin, ListView):
    template_name = "admin_dashboard/fieldrep_list.html"
    context_object_name = "reps"
    paginate_by = 25

    def get_queryset(self):
        # Base queryset - only active field reps
        qs = User.objects.filter(role="field_rep", is_active=True).order_by("-id")
        
        # Get search query if any
        q = self.request.GET.get("q", "")
        
        # Get campaign filter from URL parameters
        campaign_param = self.request.GET.get("campaign") or self.request.GET.get("campaign_id")
        brand_campaign_id = self.request.GET.get("brand_campaign_id")

        # If no campaign parameter in URL, check session
        if not campaign_param and not brand_campaign_id and hasattr(self.request, 'session'):
            brand_campaign_id = self.request.session.get('brand_campaign_id')

        # If we have a campaign filter
        if campaign_param or brand_campaign_id:
            # If we have a brand_campaign_id, use it directly
            if brand_campaign_id:
                rep_ids = list(FieldRepCampaign.objects.filter(
                    campaign__brand_campaign_id=brand_campaign_id,
                    field_rep__is_active=True
                ).values_list("field_rep_id", flat=True))
            else:
                # Try to interpret as campaign ID
                try:
                    campaign_pk = int(campaign_param)
                    rep_ids = list(FieldRepCampaign.objects.filter(
                        campaign_id=campaign_pk,
                        field_rep__is_active=True
                    ).values_list("field_rep_id", flat=True))
                except (TypeError, ValueError):
                    # If not a number, try as brand_campaign_id
                    rep_ids = list(FieldRepCampaign.objects.filter(
                        campaign__brand_campaign_id=campaign_param,
                        field_rep__is_active=True
                    ).values_list("field_rep_id", flat=True))
            
            # If we found matching field reps, filter the queryset
            if rep_ids:
                qs = qs.filter(id__in=rep_ids)
            else:
                # If no field reps found for the campaign, return empty queryset
                return User.objects.none()

        # Apply search filter if any
        if q:
            qs = qs.filter(
                Q(field_id__icontains=q) |
                Q(email__icontains=q) |
                Q(phone_number__icontains=q) |
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q)
            )
            
        return qs.distinct()

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        rep_ids = [r.id for r in ctx["reps"]]
        
        # Get the current campaign filter
        campaign_id = self.request.GET.get("campaign_id")
        campaign = self.request.GET.get("campaign")
        brand_campaign_id = self.request.GET.get("brand_campaign_id")
        campaign_filter = campaign_id or campaign or brand_campaign_id
        
        # Get campaign data - if filtered by campaign, only show that campaign
        if campaign_filter:
            # If we have a campaign filter, only show campaigns that match the filter
            if campaign_id:
                # Filter by numeric campaign ID
                campaign_data = FieldRepCampaign.objects.filter(
                    field_rep_id__in=rep_ids,
                    campaign_id=campaign_id
                ).values("field_rep_id", "campaign__brand_campaign_id")
            elif brand_campaign_id:
                # Filter by brand campaign ID
                campaign_data = FieldRepCampaign.objects.filter(
                    field_rep_id__in=rep_ids,
                    campaign__brand_campaign_id=brand_campaign_id
                ).values("field_rep_id", "campaign__brand_campaign_id")
            else:
                # Filter by campaign parameter (could be either)
                try:
                    # Try as numeric ID first
                    campaign_pk = int(campaign)
                    campaign_data = FieldRepCampaign.objects.filter(
                        field_rep_id__in=rep_ids,
                        campaign_id=campaign_pk
                    ).values("field_rep_id", "campaign__brand_campaign_id")
                except (ValueError, TypeError):
                    # Try as brand campaign ID
                    campaign_data = FieldRepCampaign.objects.filter(
                        field_rep_id__in=rep_ids,
                        campaign__brand_campaign_id=campaign
                    ).values("field_rep_id", "campaign__brand_campaign_id")
        else:
            # No filter - show all campaigns for each rep
            campaign_data = FieldRepCampaign.objects.filter(field_rep_id__in=rep_ids).values(
                "field_rep_id", "campaign__brand_campaign_id"
            )
        
        # Create a dictionary to map rep_id to a list of brand_campaign_ids
        rep_campaigns = {}
        for item in campaign_data:
            rep_id = item["field_rep_id"]
            brand_campaign_id = item["campaign__brand_campaign_id"]
            if rep_id not in rep_campaigns:
                rep_campaigns[rep_id] = []
            rep_campaigns[rep_id].append(brand_campaign_id)
            
        # Add the brand_campaigns to each rep object
        for rep in ctx["reps"]:
            rep.brand_campaigns = ", ".join(rep_campaigns.get(rep.id, []))
            
        ctx["q"] = self.request.GET.get("q", "")
        ctx["campaign_filter"] = campaign_filter
        return ctx

class FieldRepCreateView(StaffRequiredMixin, CreateView):
    model         = User
    form_class    = FieldRepForm
    template_name = "admin_dashboard/fieldrep_form.html"
    success_url   = reverse_lazy("admin_dashboard:fieldrep_list")
    
    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        campaign_param = self.request.GET.get("campaign_id") or self.request.GET.get("campaign") or self.request.GET.get("brand_campaign_id")
        if campaign_param:
            ctx["campaign_param"] = campaign_param
        return ctx

    def form_valid(self, form):
        # Save the new field rep
        response = super().form_valid(form)
        messages.success(self.request, "Field representative created successfully!")

        # If a campaign context is present, create the assignment
        campaign_param = self.request.GET.get("campaign_id") or self.request.GET.get("campaign") or self.request.GET.get("brand_campaign_id")
        if campaign_param:
            campaign = None
            try:
                # Try to get campaign by numeric PK
                campaign_pk = int(campaign_param)
                campaign = get_object_or_404(Campaign, pk=campaign_pk)
            except (ValueError, TypeError):
                # If not a numeric PK, treat as brand_campaign_id
                campaign = get_object_or_404(Campaign, brand_campaign_id=campaign_param)
            
            if campaign:
                FieldRepCampaign.objects.get_or_create(field_rep=self.object, campaign=campaign)
                messages.success(self.request, f"Successfully assigned to campaign '{campaign.name}'.")

        return response

    def get_success_url(self):
        # preserve campaign filter from the incoming querystring so the list stays filtered
        base = reverse("admin_dashboard:fieldrep_list")
        campaign_param = self.request.GET.get("campaign_id") or self.request.GET.get("campaign") or self.request.GET.get("brand_campaign_id")
        if not campaign_param:
            return base
        # if numeric, use campaign_id, otherwise use brand_campaign_id
        try:
            int(campaign_param)
            return f"{base}?campaign_id={campaign_param}"
        except (TypeError, ValueError):
            return f"{base}?brand_campaign_id={campaign_param}"

class FieldRepUpdateView(StaffRequiredMixin, UpdateView):
    model         = User
    form_class    = FieldRepForm
    template_name = "admin_dashboard/fieldrep_form.html"
    success_url   = reverse_lazy("admin_dashboard:fieldrep_list")
    
    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        campaign_param = self.request.GET.get("campaign_id") or self.request.GET.get("campaign") or self.request.GET.get("brand_campaign_id")
        if campaign_param:
            ctx["campaign_param"] = campaign_param
        return ctx
    
    def form_valid(self, form):
        messages.success(self.request, "Field representative updated successfully!")
        return super().form_valid(form)

    def get_success_url(self):
        base = reverse("admin_dashboard:fieldrep_list")
        campaign_param = self.request.GET.get("campaign_id") or self.request.GET.get("campaign") or self.request.GET.get("brand_campaign_id")
        if not campaign_param:
            return base
        try:
            int(campaign_param)
            return f"{base}?campaign_id={campaign_param}"
        except (TypeError, ValueError):
            return f"{base}?brand_campaign_id={campaign_param}"

class FieldRepDeleteView(StaffRequiredMixin, DeleteView):
    model         = User
    template_name = "admin_dashboard/fieldrep_confirm_delete.html"
    success_url   = reverse_lazy("admin_dashboard:fieldrep_list")

    def delete(self, request, *args, **kw):
        self.object = self.get_object()
        DoctorEngagement.objects.filter(short_link__created_by=self.object).delete()
        return super().delete(request, *args, **kw)

    def get_success_url(self):
        # preserve campaign filter on delete as well
        base = reverse("admin_dashboard:fieldrep_list")
        campaign_param = self.request.GET.get("campaign_id") or self.request.GET.get("campaign") or self.request.GET.get("brand_campaign_id")
        if not campaign_param:
            return base
        try:
            int(campaign_param)
            return f"{base}?campaign_id={campaign_param}"
        except (TypeError, ValueError):
            return f"{base}?brand_campaign_id={campaign_param}"

# ─────────────────────────────────────────────────────────
# DOCTOR CRUD (list/create, edit, delete) – now using pk
# ─────────────────────────────────────────────────────────
class FieldRepDoctorView(StaffRequiredMixin, CreateView):
    """List + Create on one page."""
    template_name = "admin_dashboard/fieldrep_doctors.html"
    form_class    = DoctorForm

    # Grab the rep by primary key (pk) from URL
    def dispatch(self, request, *args, **kwargs):
        self.rep = get_object_or_404(User, pk=kwargs["pk"], role="field_rep")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.rep = self.rep
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("admin_dashboard:fieldrep_doctors", args=[self.rep.pk])

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx["rep"]     = self.rep
        ctx["doctors"] = self.rep.doctors.all()
        return ctx

class DoctorUpdateView(StaffRequiredMixin, UpdateView):
    model         = Doctor
    form_class    = DoctorForm
    template_name = "admin_dashboard/doctor_form.html"

    def get_success_url(self):
        return reverse("admin_dashboard:fieldrep_doctors", args=[self.kwargs["pk_rep"]])

class DoctorDeleteView(StaffRequiredMixin, DeleteView):
    model         = Doctor
    template_name = "admin_dashboard/doctor_confirm_delete.html"

    def get_success_url(self):
        return reverse("admin_dashboard:fieldrep_doctors", args=[self.kwargs["pk_rep"]])
