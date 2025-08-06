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
        qs = User.objects.filter(role="field_rep").order_by("-id")
        q  = self.request.GET.get("q", "")
        if q:
            qs = qs.filter(
                Q(field_id__icontains=q) |
                Q(email__icontains=q)    |
                Q(phone_number__icontains=q)
            )
        return qs

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        rep_ids = [r.id for r in ctx["reps"]]
        brands  = FieldRepCampaign.objects.filter(field_rep_id__in=rep_ids)\
                     .values_list("field_rep_id", "campaign__name")
        brand_map = {}
        for rep_id, brand in brands:
            brand_map.setdefault(rep_id, set()).add(brand)
        ctx["brand_map"] = {k: ", ".join(v) for k, v in brand_map.items()}
        ctx["q"] = self.request.GET.get("q", "")
        return ctx

class FieldRepCreateView(StaffRequiredMixin, CreateView):
    form_class    = FieldRepForm
    template_name = "admin_dashboard/fieldrep_form.html"
    success_url   = reverse_lazy("admin_dashboard:fieldrep_list")

class FieldRepUpdateView(StaffRequiredMixin, UpdateView):
    model         = User
    form_class    = FieldRepForm
    template_name = "admin_dashboard/fieldrep_form.html"
    success_url   = reverse_lazy("admin_dashboard:fieldrep_list")

class FieldRepDeleteView(StaffRequiredMixin, DeleteView):
    model         = User
    template_name = "admin_dashboard/fieldrep_confirm_delete.html"
    success_url   = reverse_lazy("admin_dashboard:fieldrep_list")

    def delete(self, request, *args, **kw):
        self.object = self.get_object()
        DoctorEngagement.objects.filter(short_link__created_by=self.object).delete()
        return super().delete(request, *args, **kw)

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
