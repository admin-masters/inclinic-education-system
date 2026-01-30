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

from django.db import connection
from campaign_management.models import CampaignAssignment


def _get_campaign_param(request):
    """
    Single canonical way to read the campaign context across admin_dashboard.
    Treat it as a STRING identifier (brand_campaign_id) like the campaign module.
    """
    return (
        request.POST.get("campaign")
        or request.GET.get("campaign_id")
        or request.GET.get("campaign")
        or request.GET.get("brand_campaign_id")
    )


def _campaign_dropdown_rows():
    """
    Returns a list of dicts: [{"brand_campaign_id": "...", "name": "..."}, ...]
    Uses ORM values() first; falls back to raw SQL if there are UUID coercion issues.
    """
    try:
        return list(
            Campaign.objects.values("brand_campaign_id", "name").order_by("name")
        )
    except Exception:
        table = connection.ops.quote_name(Campaign._meta.db_table)
        bcid = connection.ops.quote_name("brand_campaign_id")
        name = connection.ops.quote_name("name")
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT {bcid}, {name} FROM {table} ORDER BY {name} ASC")
            return [
                {"brand_campaign_id": str(brand_campaign_id), "name": campaign_name}
                for (brand_campaign_id, campaign_name) in cursor.fetchall()
            ]


def _campaign_pk_from_param(campaign_param):
    """
    Resolve the DB PK for a campaign_param.
    - If numeric => treat as pk
    - Else => treat as brand_campaign_id
    """
    if not campaign_param:
        return None
    campaign_param = str(campaign_param).strip()
    if not campaign_param:
        return None

    if campaign_param.isdigit():
        try:
            return int(campaign_param)
        except ValueError:
            return None

    # brand_campaign_id lookup
    try:
        return (
            Campaign.objects.filter(brand_campaign_id=campaign_param)
            .values_list("pk", flat=True)
            .first()
        )
    except Exception:
        # fallback raw SQL
        table = connection.ops.quote_name(Campaign._meta.db_table)
        pk_col = connection.ops.quote_name(Campaign._meta.pk.column)
        bcid = connection.ops.quote_name("brand_campaign_id")
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {pk_col} FROM {table} WHERE {bcid}=%s LIMIT 1",
                [campaign_param],
            )
            row = cursor.fetchone()
        return row[0] if row else None


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
        return reverse_lazy("admin_dashboard:fieldrep_list")

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
            created, updated, campaign_assignments, errors = form.save(request.user)
            for err in errors:
                messages.warning(request, err)
            return redirect("admin_dashboard:bulk_upload")
    else:
        form = FieldRepBulkUploadForm()
        # Pre-select campaign if provided in URL
        campaign_ref = (
                request.GET.get("campaign_id")
                or request.GET.get("campaign")
                or request.GET.get("brand_campaign_id")
        )

        if campaign_ref:
            campaign_obj = None
            try:
                campaign_obj = Campaign.objects.get(pk=int(campaign_ref))
            except (TypeError, ValueError, Campaign.DoesNotExist):
                campaign_obj = Campaign.objects.filter(brand_campaign_id=str(campaign_ref)).first()

            if campaign_obj:
                form.fields["campaign"].initial = campaign_obj

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
        qs = User.objects.filter(role="field_rep", active=True).order_by("-id")

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
                print(f"DEBUG: Admin dashboard filtering by brand_campaign_id: {brand_campaign_id}")
                rep_ids = list(FieldRepCampaign.objects.filter(
                    campaign__brand_campaign_id=brand_campaign_id,
                    field_rep__active=True
                ).values_list("field_rep_id", flat=True))
                print(f"DEBUG: Found rep_ids: {rep_ids}")
            else:
                # Try to interpret as campaign ID or brand_campaign_id
                try:
                    campaign_pk = int(campaign_param)
                    rep_ids = list(FieldRepCampaign.objects.filter(
                        campaign_id=campaign_pk,
                        field_rep__active=True
                    ).values_list("field_rep_id", flat=True))
                except (TypeError, ValueError):
                    # If not a number, try as brand_campaign_id
                    rep_ids = list(FieldRepCampaign.objects.filter(
                        campaign__brand_campaign_id=campaign_param,
                        field_rep__active=True
                    ).values_list("field_rep_id", flat=True))

            # If we found matching field reps, filter the queryset
            if rep_ids:
                qs = qs.filter(id__in=rep_ids)
                print(f"DEBUG: Filtered queryset to {qs.count()} field reps")
            else:
                # If no field reps found for the campaign, return empty queryset
                print("DEBUG: No rep_ids found, returning empty queryset")
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

        # Current filter (could be numeric PK, UUID, etc.)
        campaign_id = self.request.GET.get("campaign_id")
        campaign = self.request.GET.get("campaign")
        brand_campaign_id = self.request.GET.get("brand_campaign_id")
        campaign_filter = campaign_id or campaign or brand_campaign_id

        # Persist filter in session (optional but useful if you use redirect_to_fieldreps)
        if campaign_filter and hasattr(self.request, "session"):
            self.request.session["brand_campaign_id"] = str(campaign_filter)

        # Build campaign_data depending on filter
        if campaign_filter:
            if campaign_id:
                campaign_data = FieldRepCampaign.objects.filter(
                    field_rep_id__in=rep_ids,
                    campaign_id=campaign_id
                ).values("field_rep_id", "campaign__brand_campaign_id")

            elif brand_campaign_id:
                campaign_data = FieldRepCampaign.objects.filter(
                    field_rep_id__in=rep_ids,
                    campaign__brand_campaign_id=brand_campaign_id
                ).values("field_rep_id", "campaign__brand_campaign_id")

            else:
                # campaign param could be numeric PK or brand_campaign_id/UUID
                try:
                    campaign_pk = int(campaign)
                    campaign_data = FieldRepCampaign.objects.filter(
                        field_rep_id__in=rep_ids,
                        campaign_id=campaign_pk
                    ).values("field_rep_id", "campaign__brand_campaign_id")
                except (ValueError, TypeError):
                    campaign_data = FieldRepCampaign.objects.filter(
                        field_rep_id__in=rep_ids,
                        campaign__brand_campaign_id=campaign
                    ).values("field_rep_id", "campaign__brand_campaign_id")
        else:
            campaign_data = FieldRepCampaign.objects.filter(
                field_rep_id__in=rep_ids
            ).values("field_rep_id", "campaign__brand_campaign_id")

        # Map rep_id -> list of campaign ids (as STRINGS)
        rep_campaigns = {}
        for item in campaign_data:
            rep_id = item.get("field_rep_id")
            bc_id = item.get("campaign__brand_campaign_id")

            if not rep_id or not bc_id:
                continue

            # ✅ CRITICAL FIX: always stringify (handles uuid.UUID and normal strings)
            rep_campaigns.setdefault(rep_id, []).append(str(bc_id))

        # Attach comma-separated campaigns to each rep (dedupe, preserve order)
        for rep in ctx["reps"]:
            vals = rep_campaigns.get(rep.id, [])
            seen = set()
            uniq = []
            for v in vals:
                if v and v not in seen:
                    seen.add(v)
                    uniq.append(v)
            rep.brand_campaigns = ", ".join(uniq)

        ctx["q"] = self.request.GET.get("q", "")
        ctx["campaign_filter"] = str(campaign_filter) if campaign_filter else ""
        return ctx


class FieldRepCreateView(StaffRequiredMixin, CreateView):
    model = User
    form_class = FieldRepForm
    template_name = "admin_dashboard/fieldrep_form.html"
    success_url = reverse_lazy("admin_dashboard:fieldrep_list")

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)

        campaign_param = _get_campaign_param(self.request)
        if campaign_param:
            ctx["campaign_param"] = campaign_param

        # IMPORTANT: don't instantiate Campaign objects here
        ctx["campaigns"] = _campaign_dropdown_rows()
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)

        campaign_param = _get_campaign_param(self.request)
        if campaign_param:
            campaign_pk = _campaign_pk_from_param(campaign_param)

            if campaign_pk:
                # Create BOTH mappings (same behavior as bulk upload):contentReference[oaicite:9]{index=9}
                CampaignAssignment.objects.get_or_create(
                    field_rep=self.object,
                    campaign_id=campaign_pk,
                )
                FieldRepCampaign.objects.get_or_create(
                    field_rep=self.object,
                    campaign_id=campaign_pk,
                )
            else:
                messages.warning(
                    self.request,
                    f"Campaign '{campaign_param}' not found in portal DB. Create/import the campaign first."
                )

        return response

    def get_success_url(self):
        # preserve campaign filter from the incoming querystring so the list stays filtered
        base = reverse("admin_dashboard:fieldrep_list")
        campaign_param = (
            self.request.POST.get("campaign")
            or self.request.GET.get("campaign_id")
            or self.request.GET.get("campaign")
            or self.request.GET.get("brand_campaign_id")
        )
        if not campaign_param:
            return base
        # if numeric, use campaign_id, otherwise use brand_campaign_id
        try:
            int(campaign_param)
            return f"{base}?campaign_id={campaign_param}"
        except (TypeError, ValueError):
            return f"{base}?brand_campaign_id={campaign_param}"

class FieldRepUpdateView(StaffRequiredMixin, UpdateView):
    model = User
    form_class = FieldRepForm
    template_name = "admin_dashboard/fieldrep_form.html"
    success_url = reverse_lazy("admin_dashboard:fieldrep_list")

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        campaign_param = _get_campaign_param(self.request)
        if campaign_param:
            ctx["campaign_param"] = campaign_param
        ctx["campaigns"] = _campaign_dropdown_rows()
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)

        campaign_param = _get_campaign_param(self.request)
        if campaign_param:
            campaign_pk = _campaign_pk_from_param(campaign_param)
            if campaign_pk:
                CampaignAssignment.objects.get_or_create(
                    field_rep=self.object,
                    campaign_id=campaign_pk,
                )
                FieldRepCampaign.objects.get_or_create(
                    field_rep=self.object,
                    campaign_id=campaign_pk,
                )
        return response

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
