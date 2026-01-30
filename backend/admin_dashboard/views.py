import uuid
import string

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.hashers import make_password
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import IntegrityError, connection, connections, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from campaign_management.models import Campaign  # portal campaign still used by dashboard/bulk-upload
from campaign_management.master_models import (
    MasterAuthUser,
    MasterCampaign,
    MasterCampaignFieldRep,
    MasterFieldRep,
)
from collateral_management.models import CampaignCollateral
from doctor_viewer.models import Doctor, DoctorEngagement
from sharing_management.models import ShareLog, VideoTrackingLog
from user_management.models import User

from .forms import DoctorForm, FieldRepBulkUploadForm
from utils.recaptcha import recaptcha_required


MASTER_DB_ALIAS = getattr(settings, "MASTER_DB_ALIAS", "master")


# ─────────────────────────────────────────────────────────
# Campaign param helpers (canonicalize campaign context)
# ─────────────────────────────────────────────────────────

def _get_campaign_param_any(request):
    """
    Read campaign context from GET/POST first, then fall back to session.
    Always returns a STRING (or None).

    IMPORTANT: If your template has BOTH a hidden input and a <select name="campaign">,
    request.POST.get("campaign") returns only the first value. We therefore use
    getlist() and prefer the *last* non-empty value.
    """
    v = None

    # Prefer POST campaign values (handle duplicate campaign keys)
    if request.method == "POST" and hasattr(request, "POST"):
        vals = request.POST.getlist("campaign")
        vals = [str(x).strip() for x in vals if str(x).strip()]
        if vals:
            v = vals[-1]

    if not v:
        v = (
            request.GET.get("campaign_id")
            or request.GET.get("campaign")
            or request.GET.get("brand_campaign_id")
        )

    if not v and hasattr(request, "session"):
        v = request.session.get("brand_campaign_id")

    if v is None:
        return None

    s = str(v).strip()
    return s or None


def _normalize_master_campaign_id(brand_campaign_id: str | None) -> str | None:
    """
    Master DB stores campaign_id without hyphens (32 hex).
    Return 32-hex lowercase string when possible.
    """
    if not brand_campaign_id:
        return None
    raw = str(brand_campaign_id).strip()
    if not raw:
        return None

    hex32 = raw.replace("-", "").lower()
    if len(hex32) == 32 and all(ch in string.hexdigits for ch in hex32):
        return hex32.lower()
    return None


def _uuid_dashed_from_hex32(hex32: str) -> str:
    try:
        return str(uuid.UUID(hex=str(hex32)))
    except Exception:
        return str(hex32)


def _master_available() -> bool:
    try:
        _ = connections[MASTER_DB_ALIAS]
        return True
    except Exception:
        return False


def _master_campaign_dropdown_rows():
    """
    Dropdown rows for templates:
        [{"brand_campaign_id": "<dashed uuid>", "name": "<name>"}]
    Sourced from MASTER DB only (MasterCampaign).
    """
    if not _master_available():
        return []

    db = connections[MASTER_DB_ALIAS]
    try:
        rows = list(
            MasterCampaign.objects.using(MASTER_DB_ALIAS)
            .values("id", "name")
            .order_by("name")
        )
        out = []
        for r in rows:
            cid = r.get("id")
            out.append(
                {
                    "brand_campaign_id": _uuid_dashed_from_hex32(cid),
                    "name": r.get("name") or "",
                }
            )
        return out
    except Exception:
        # Raw SQL fallback (avoids any model field coercion)
        table = db.ops.quote_name(MasterCampaign._meta.db_table)
        id_col = db.ops.quote_name(MasterCampaign._meta.pk.column)  # usually "id"
        name_col = db.ops.quote_name("name")
        with db.cursor() as cursor:
            cursor.execute(f"SELECT {id_col}, {name_col} FROM {table} ORDER BY {name_col} ASC")
            return [
                {"brand_campaign_id": _uuid_dashed_from_hex32(cid), "name": name or ""}
                for (cid, name) in cursor.fetchall()
            ]


def _master_campaign_from_param(campaign_param: str | None) -> MasterCampaign | None:
    """
    campaign_param is expected to be a brand_campaign_id (uuid, dashed/undashed).
    Returns MasterCampaign (using MASTER_DB_ALIAS) or None.
    """
    if not campaign_param or not _master_available():
        return None

    master_campaign_id = _normalize_master_campaign_id(campaign_param)
    if not master_campaign_id:
        return None

    try:
        return MasterCampaign.objects.using(MASTER_DB_ALIAS).filter(id=master_campaign_id).first()
    except Exception:
        return None


def _master_rep_campaign_map(rep_ids, master_campaign_id: str | None = None):
    """
    Returns {rep_id: [<dashed uuid>, ...]}
    Optionally filtered by a single master_campaign_id (hex32).
    """
    if not rep_ids or not _master_available():
        return {}

    qs = MasterCampaignFieldRep.objects.using(MASTER_DB_ALIAS).filter(field_rep_id__in=rep_ids)
    if master_campaign_id:
        qs = qs.filter(campaign_id=str(master_campaign_id))

    rows = qs.values_list("field_rep_id", "campaign_id")
    out = {}
    for rep_id, cid in rows:
        if rep_id is None or cid is None:
            continue
        out.setdefault(int(rep_id), []).append(_uuid_dashed_from_hex32(str(cid)))
    return out


def _ensure_portal_user_for_master_rep(master_rep: MasterFieldRep) -> User:
    """
    Doctor module still uses portal User + Doctor models (default DB).
    To keep "Doctors" page working, we create/update a portal User as a mirror.

    This is best-effort and does NOT affect master CRUD flows.
    """
    email = (getattr(master_rep.user, "email", "") or "").strip()
    if not email:
        raise ValidationError("Master rep has no email; cannot map to portal user.")

    portal_user = User.objects.filter(email__iexact=email).first()
    if portal_user:
        dirty = []
        fn = (getattr(master_rep.user, "first_name", "") or "").strip()
        ln = (getattr(master_rep.user, "last_name", "") or "").strip()
        if fn and portal_user.first_name != fn:
            portal_user.first_name = fn
            dirty.append("first_name")
        if ln and portal_user.last_name != ln:
            portal_user.last_name = ln
            dirty.append("last_name")

        phone = (getattr(master_rep, "phone_number", "") or "").strip()
        if phone and getattr(portal_user, "phone_number", "") != phone:
            portal_user.phone_number = phone
            dirty.append("phone_number")

        field_id = (getattr(master_rep, "brand_supplied_field_rep_id", "") or "").strip()
        if field_id and getattr(portal_user, "field_id", "") != field_id:
            portal_user.field_id = field_id
            dirty.append("field_id")

        if getattr(portal_user, "role", "") != "field_rep":
            portal_user.role = "field_rep"
            dirty.append("role")

        if getattr(portal_user, "active", True) is False:
            portal_user.active = True
            dirty.append("active")

        if dirty:
            portal_user.save(update_fields=dirty)
        return portal_user

    # Create a new portal user
    base_username = email.split("@", 1)[0] or "fieldrep"
    username = base_username
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base_username}_{counter}"
        counter += 1

    portal_user = User(
        username=username,
        email=email,
        first_name=(getattr(master_rep.user, "first_name", "") or "").strip(),
        last_name=(getattr(master_rep.user, "last_name", "") or "").strip(),
        role="field_rep",
        active=True,
        phone_number=(getattr(master_rep, "phone_number", "") or "").strip(),
        field_id=(getattr(master_rep, "brand_supplied_field_rep_id", "") or "").strip(),
        password=make_password(None),
    )
    portal_user.save()
    return portal_user


# ─────────────────────────────────────────────────────────
# Forms (MASTER DB)
# ─────────────────────────────────────────────────────────

PHONE_VALIDATOR = RegexValidator(
    regex=r"^\+?[0-9]{7,20}$",
    message="Enter a valid phone number (digits, optional leading +).",
)

class MasterFieldRepForm(forms.ModelForm):
    """
    Create/Update a FieldRep in MASTER DB:
      - MasterAuthUser (auth_user) as `user`
      - MasterFieldRep (campaign_fieldrep) as the main model

    Also validates "email uniqueness per brand".
    """
    email = forms.EmailField(
        label="Gmail ID",
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )
    first_name = forms.CharField(
        label="First Name",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    last_name = forms.CharField(
        label="Last Name",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    phone_number = forms.CharField(
        label="Field Rep Number",
        required=False,
        validators=[PHONE_VALIDATOR],
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "+919876543210"}),
    )
    field_id = forms.CharField(
        label="Field ID",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    class Meta:
        model = MasterFieldRep
        fields = ("phone_number",)  # we map field_id -> brand_supplied_field_rep_id manually

    def __init__(self, *args, **kwargs):
        self.brand_id = kwargs.pop("brand_id", None)
        self.using = kwargs.pop("using", MASTER_DB_ALIAS)
        super().__init__(*args, **kwargs)

        # Pre-fill from related user + rep for Update
        if self.instance and getattr(self.instance, "pk", None):
            try:
                u = getattr(self.instance, "user", None)
                if u:
                    self.fields["email"].initial = (getattr(u, "email", "") or "").strip()
                    self.fields["first_name"].initial = (getattr(u, "first_name", "") or "").strip()
                    self.fields["last_name"].initial = (getattr(u, "last_name", "") or "").strip()
            except Exception:
                pass
            self.fields["field_id"].initial = (getattr(self.instance, "brand_supplied_field_rep_id", "") or "").strip()

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise ValidationError("Email is required.")

        # Determine brand_id
        brand_id = self.brand_id or getattr(self.instance, "brand_id", None)

        if not brand_id:
            # Create flow always passes brand_id (derived from campaign).
            return email

        qs = (
            MasterFieldRep.objects.using(self.using)
            .select_related("user")
            .filter(brand_id=brand_id, user__email__iexact=email)
        )
        if self.instance and getattr(self.instance, "pk", None):
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError("Field rep already exist with the same email try using different email.")

        return email

    def save(self, commit=True):
        if not _master_available():
            raise ValidationError("Master DB is not available.")

        using = self.using

        email = (self.cleaned_data.get("email") or "").strip().lower()
        first_name = (self.cleaned_data.get("first_name") or "").strip()
        last_name = (self.cleaned_data.get("last_name") or "").strip()
        phone_number = (self.cleaned_data.get("phone_number") or "").strip()
        field_id = (self.cleaned_data.get("field_id") or "").strip()

        rep = super().save(commit=False)

        # Map form fields -> MasterFieldRep
        rep.phone_number = phone_number
        rep.brand_supplied_field_rep_id = field_id

        full_name = (f"{first_name} {last_name}").strip()
        if not full_name:
            full_name = (getattr(rep, "full_name", "") or "").strip() or email.split("@", 1)[0]
        rep.full_name = full_name

        # Ensure is_active defaults to True on create
        if getattr(rep, "pk", None) is None:
            rep.is_active = True

        # Create/Update master auth_user
        if getattr(rep, "pk", None):
            u = rep.user
            u.username = email
            u.email = email
            u.first_name = first_name
            u.last_name = last_name
            if getattr(u, "is_active", True) is False:
                u.is_active = True
            u.save(using=using)
        else:
            brand_id = self.brand_id
            if not brand_id:
                raise ValidationError("Brand context missing. Please select a campaign to derive brand.")

            existing_user = MasterAuthUser.objects.using(using).filter(username=email).first()
            if existing_user:
                existing_rep = MasterFieldRep.objects.using(using).filter(user_id=existing_user.id).first()
                if existing_rep:
                    raise ValidationError("Field rep already exist with the same email try using different email.")
                u = existing_user
                u.email = email
                u.first_name = first_name
                u.last_name = last_name
                if getattr(u, "is_active", True) is False:
                    u.is_active = True
                u.save(using=using)
            else:
                u = MasterAuthUser(
                    username=email,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    is_staff=False,
                    is_superuser=False,
                    is_active=True,
                    date_joined=timezone.now(),
                    password=make_password(None),
                )
                u.save(using=using)

            rep.user_id = u.id
            rep.brand_id = brand_id

        if commit:
            rep.save(using=using)
        return rep


# ─────────────────────────────────────────────────────────
# MIXIN
# ─────────────────────────────────────────────────────────

class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = reverse_lazy("admin:login")

    def test_func(self):
        return bool(self.request.user.is_staff)

    def handle_no_permission(self):
        return redirect("admin:login")

    def get_success_url(self):
        return reverse_lazy("admin_dashboard:fieldrep_list")


# ─────────────────────────────────────────────────────────
# DASHBOARD (unchanged – PORTAL DB)
# ─────────────────────────────────────────────────────────

@staff_member_required
def dashboard(request):
    shares = ShareLog.objects.values("short_link__resource_id").annotate(share_cnt=Count("id"))
    pdfs = (
        DoctorEngagement.objects.filter(pdf_completed=True)
        .values("short_link__resource_id")
        .annotate(pdf_impr=Count("id"))
    )
    vids = (
        DoctorEngagement.objects.filter(video_watch_percentage__gte=90)
        .values("short_link__resource_id")
        .annotate(vid_comp=Count("id"))
    )

    video_logs = (
        VideoTrackingLog.objects.filter(video_percentage="3")
        .values("share_log__collateral_id")
        .annotate(vid_comp=Count("id"))
    )
    video_log_map = {v["share_log__collateral_id"]: v["vid_comp"] for v in video_logs}

    share_map = {s["short_link__resource_id"]: s["share_cnt"] for s in shares}
    pdf_map = {p["short_link__resource_id"]: p["pdf_impr"] for p in pdfs}
    vid_map = {v["short_link__resource_id"]: v["vid_comp"] for v in vids}

    stats = []
    for c in Campaign.objects.all():
        coll_ids = list(CampaignCollateral.objects.filter(campaign=c).values_list("collateral_id", flat=True))
        for coll_id in coll_ids:
            stats.append(
                {
                    "campaign": c,
                    "collateral_id": coll_id,
                    "shares": share_map.get(coll_id, 0),
                    "pdf_completions": pdf_map.get(coll_id, 0),
                    "video_completions_old": vid_map.get(coll_id, 0),
                    "video_completions_new": video_log_map.get(coll_id, 0),
                }
            )
    return render(request, "admin_dashboard/dashboard.html", {"stats": stats})


# ─────────────────────────────────────────────────────────
# BULK‑UPLOAD
# NOTE: Still uses existing FieldRepBulkUploadForm (portal),
# but mirrors created/updated reps into master DB best-effort.
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

            # Best-effort mirror to master
            if _master_available():
                campaign_param = _get_campaign_param_any(request)
                master_campaign = _master_campaign_from_param(campaign_param)
                brand_id = getattr(master_campaign, "brand_id", None) if master_campaign else None
                master_campaign_id = _normalize_master_campaign_id(campaign_param)

                def _mirror_one(portal_user: User):
                    email = (portal_user.email or "").strip().lower()
                    if not email or not brand_id:
                        return
                    with transaction.atomic(using=MASTER_DB_ALIAS):
                        mu, _ = MasterAuthUser.objects.using(MASTER_DB_ALIAS).get_or_create(
                            username=email,
                            defaults=dict(
                                email=email,
                                first_name=(portal_user.first_name or "").strip(),
                                last_name=(portal_user.last_name or "").strip(),
                                is_staff=False,
                                is_superuser=False,
                                is_active=bool(getattr(portal_user, "active", True)),
                                date_joined=timezone.now(),
                                password=make_password(None),
                            ),
                        )

                        dirty_u = []
                        if mu.email != email:
                            mu.email = email
                            dirty_u.append("email")
                        fn = (portal_user.first_name or "").strip()
                        ln = (portal_user.last_name or "").strip()
                        if fn and mu.first_name != fn:
                            mu.first_name = fn
                            dirty_u.append("first_name")
                        if ln and mu.last_name != ln:
                            mu.last_name = ln
                            dirty_u.append("last_name")
                        active = bool(getattr(portal_user, "active", True))
                        if mu.is_active != active:
                            mu.is_active = active
                            dirty_u.append("is_active")
                        if dirty_u:
                            mu.save(using=MASTER_DB_ALIAS, update_fields=dirty_u)

                        mrep = MasterFieldRep.objects.using(MASTER_DB_ALIAS).filter(user_id=mu.id).first()
                        if not mrep:
                            mrep = MasterFieldRep(
                                user_id=mu.id,
                                brand_id=brand_id,
                                full_name=(portal_user.get_full_name() or "").strip() or email.split("@", 1)[0],
                                phone_number=(getattr(portal_user, "phone_number", "") or "").strip(),
                                brand_supplied_field_rep_id=(getattr(portal_user, "field_id", "") or "").strip(),
                                is_active=active,
                            )
                            mrep.save(using=MASTER_DB_ALIAS)
                        else:
                            dirty_r = []
                            if mrep.brand_id != brand_id:
                                mrep.brand_id = brand_id
                                dirty_r.append("brand")
                            full_name = (portal_user.get_full_name() or "").strip() or email.split("@", 1)[0]
                            if mrep.full_name != full_name:
                                mrep.full_name = full_name
                                dirty_r.append("full_name")
                            phone = (getattr(portal_user, "phone_number", "") or "").strip()
                            if (mrep.phone_number or "") != phone:
                                mrep.phone_number = phone
                                dirty_r.append("phone_number")
                            fid = (getattr(portal_user, "field_id", "") or "").strip()
                            if (mrep.brand_supplied_field_rep_id or "") != fid:
                                mrep.brand_supplied_field_rep_id = fid
                                dirty_r.append("brand_supplied_field_rep_id")
                            if mrep.is_active != active:
                                mrep.is_active = active
                                dirty_r.append("is_active")
                            if dirty_r:
                                mrep.save(using=MASTER_DB_ALIAS, update_fields=dirty_r)

                        if master_campaign_id:
                            MasterCampaignFieldRep.objects.using(MASTER_DB_ALIAS).get_or_create(
                                campaign_id=master_campaign_id,
                                field_rep_id=mrep.id,
                            )

                for u in list(created) + list(updated):
                    try:
                        _mirror_one(u)
                    except Exception:
                        pass

            return redirect("admin_dashboard:bulk_upload")
    else:
        form = FieldRepBulkUploadForm()

        # Keep existing behaviour for portal bulk upload UI
        campaign_ref = _get_campaign_param_any(request)
        if campaign_ref:
            try:
                campaign_obj = Campaign.objects.filter(brand_campaign_id=str(campaign_ref)).first()
                if campaign_obj:
                    form.fields["campaign"].initial = campaign_obj
            except Exception:
                pass

    return render(request, "admin_dashboard/bulk_upload.html", {"form": form})


# ─────────────────────────────────────────────────────────
# FIELD‑REP CRUD (MASTER DB)
# ─────────────────────────────────────────────────────────

class FieldRepListView(StaffRequiredMixin, ListView):
    template_name = "admin_dashboard/fieldrep_list.html"
    context_object_name = "reps"
    paginate_by = 25

    def get_queryset(self):
        if not _master_available():
            messages.error(self.request, "Master DB is not available.")
            return MasterFieldRep.objects.none()

        qs = (
            MasterFieldRep.objects.using(MASTER_DB_ALIAS)
            .select_related("user")
            .filter(is_active=True, user__is_active=True)
            .order_by("-id")
        )

        q = (self.request.GET.get("q") or "").strip()
        campaign_param = _get_campaign_param_any(self.request)

        if campaign_param and hasattr(self.request, "session"):
            self.request.session["brand_campaign_id"] = str(campaign_param)

        master_campaign_id = _normalize_master_campaign_id(campaign_param)

        if campaign_param and not master_campaign_id and hasattr(self.request, "session"):
            self.request.session.pop("brand_campaign_id", None)

        if master_campaign_id:
            rep_ids = list(
                MasterCampaignFieldRep.objects.using(MASTER_DB_ALIAS)
                .filter(campaign_id=master_campaign_id)
                .values_list("field_rep_id", flat=True)
            )
            if rep_ids:
                qs = qs.filter(id__in=rep_ids)
            else:
                return MasterFieldRep.objects.none()

        if q:
            qs = qs.filter(
                Q(brand_supplied_field_rep_id__icontains=q)
                | Q(phone_number__icontains=q)
                | Q(full_name__icontains=q)
                | Q(user__email__icontains=q)
                | Q(user__first_name__icontains=q)
                | Q(user__last_name__icontains=q)
            )

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        reps = ctx.get("reps") or []
        rep_ids = [r.id for r in reps]

        campaign_param = _get_campaign_param_any(self.request) or ""
        master_campaign_id = _normalize_master_campaign_id(campaign_param)

        rep_campaigns = _master_rep_campaign_map(rep_ids, master_campaign_id if master_campaign_id else None)

        for rep in reps:
            rep.email = (getattr(rep.user, "email", "") or "").strip()
            rep.field_id = (getattr(rep, "brand_supplied_field_rep_id", "") or "").strip()

            vals = rep_campaigns.get(rep.id, [])
            seen = set()
            uniq = []
            for v in vals:
                if v and v not in seen:
                    seen.add(v)
                    uniq.append(v)
            rep.brand_campaigns = ", ".join(uniq)

        ctx["q"] = (self.request.GET.get("q") or "").strip()
        ctx["campaign_filter"] = campaign_param
        return ctx


class FieldRepCreateView(StaffRequiredMixin, CreateView):
    model = MasterFieldRep
    form_class = MasterFieldRepForm
    template_name = "admin_dashboard/fieldrep_form.html"

    def get_queryset(self):
        return MasterFieldRep.objects.using(MASTER_DB_ALIAS).select_related("user")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        campaign_param = _get_campaign_param_any(self.request)
        master_campaign = _master_campaign_from_param(campaign_param)
        brand_id = getattr(master_campaign, "brand_id", None) if master_campaign else None

        kwargs["brand_id"] = brand_id
        kwargs["using"] = MASTER_DB_ALIAS
        return kwargs

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        campaign_param = _get_campaign_param_any(self.request)
        ctx["campaign_param"] = campaign_param or ""
        ctx["campaigns"] = _master_campaign_dropdown_rows()
        return ctx

    def form_valid(self, form):
        campaign_param = _get_campaign_param_any(self.request)
        master_campaign_id = _normalize_master_campaign_id(campaign_param)

        try:
            with transaction.atomic(using=MASTER_DB_ALIAS):
                response = super().form_valid(form)

                if master_campaign_id:
                    MasterCampaignFieldRep.objects.using(MASTER_DB_ALIAS).get_or_create(
                        campaign_id=master_campaign_id,
                        field_rep_id=self.object.id,
                    )

        except ValidationError as e:
            form.add_error(None, e)
            return self.form_invalid(form)
        except IntegrityError:
            form.add_error("email", "Field rep already exist with the same email try using different email.")
            return self.form_invalid(form)
        except Exception:
            form.add_error(None, "Unable to create Field Rep due to a master DB error.")
            return self.form_invalid(form)

        return response

    def get_success_url(self):
        base = reverse("admin_dashboard:fieldrep_list")
        campaign_param = _get_campaign_param_any(self.request)
        return f"{base}?campaign={campaign_param}" if campaign_param else base


class FieldRepUpdateView(StaffRequiredMixin, UpdateView):
    model = MasterFieldRep
    form_class = MasterFieldRepForm
    template_name = "admin_dashboard/fieldrep_form.html"

    def get_queryset(self):
        return MasterFieldRep.objects.using(MASTER_DB_ALIAS).select_related("user")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["brand_id"] = getattr(self.get_object(), "brand_id", None)
        kwargs["using"] = MASTER_DB_ALIAS
        return kwargs

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        campaign_param = _get_campaign_param_any(self.request)
        ctx["campaign_param"] = campaign_param or ""
        ctx["campaigns"] = _master_campaign_dropdown_rows()
        return ctx

    def form_valid(self, form):
        campaign_param = _get_campaign_param_any(self.request)
        master_campaign_id = _normalize_master_campaign_id(campaign_param)

        try:
            with transaction.atomic(using=MASTER_DB_ALIAS):
                response = super().form_valid(form)

                if master_campaign_id:
                    MasterCampaignFieldRep.objects.using(MASTER_DB_ALIAS).get_or_create(
                        campaign_id=master_campaign_id,
                        field_rep_id=self.object.id,
                    )

        except ValidationError as e:
            form.add_error(None, e)
            return self.form_invalid(form)
        except IntegrityError:
            form.add_error("email", "Field rep already exist with the same email try using different email.")
            return self.form_invalid(form)
        except Exception:
            form.add_error(None, "Unable to update Field Rep due to a master DB error.")
            return self.form_invalid(form)

        return response

    def get_success_url(self):
        base = reverse("admin_dashboard:fieldrep_list")
        campaign_param = _get_campaign_param_any(self.request)
        return f"{base}?campaign={campaign_param}" if campaign_param else base


class FieldRepDeleteView(StaffRequiredMixin, DeleteView):
    model = MasterFieldRep
    template_name = "admin_dashboard/fieldrep_confirm_delete.html"

    def get_queryset(self):
        return MasterFieldRep.objects.using(MASTER_DB_ALIAS).select_related("user")

    def delete(self, request, *args, **kw):
        """
        Soft-delete in MASTER DB:
          - MasterFieldRep.is_active = False
          - MasterAuthUser.is_active = False
        """
        if not _master_available():
            messages.error(request, "Master DB is not available.")
            return redirect(self.get_success_url())

        self.object = self.get_object()
        try:
            with transaction.atomic(using=MASTER_DB_ALIAS):
                if getattr(self.object, "is_active", True):
                    self.object.is_active = False
                    self.object.save(using=MASTER_DB_ALIAS, update_fields=["is_active"])

                try:
                    u = self.object.user
                    if u and getattr(u, "is_active", True):
                        u.is_active = False
                        u.save(using=MASTER_DB_ALIAS, update_fields=["is_active"])
                except Exception:
                    pass

            messages.success(request, "Field Rep deactivated successfully.")
        except Exception:
            messages.error(request, "Unable to deactivate Field Rep due to a master DB error.")

        return redirect(self.get_success_url())

    def get_success_url(self):
        base = reverse("admin_dashboard:fieldrep_list")
        campaign_param = _get_campaign_param_any(self.request)
        return f"{base}?campaign={campaign_param}" if campaign_param else base


# ─────────────────────────────────────────────────────────
# DOCTOR CRUD (PORTAL DB) – Doctor model is portal-only
# ─────────────────────────────────────────────────────────

class FieldRepDoctorView(StaffRequiredMixin, CreateView):
    template_name = "admin_dashboard/fieldrep_doctors.html"
    form_class = DoctorForm

    def dispatch(self, request, *args, **kwargs):
        rep_pk = kwargs.get("pk") or kwargs.get("rep_id")

        self.master_rep = get_object_or_404(
            MasterFieldRep.objects.using(MASTER_DB_ALIAS).select_related("user"),
            pk=rep_pk,
        )

        self.portal_rep = _ensure_portal_user_for_master_rep(self.master_rep)

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.rep = self.portal_rep
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("admin_dashboard:fieldrep_doctors", args=[self.master_rep.pk])

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx["rep"] = self.master_rep
        ctx["doctors"] = self.portal_rep.doctors.all()
        return ctx


class DoctorUpdateView(StaffRequiredMixin, UpdateView):
    model = Doctor
    form_class = DoctorForm
    template_name = "admin_dashboard/doctor_form.html"

    def get_success_url(self):
        return reverse("admin_dashboard:fieldrep_doctors", args=[self.kwargs["pk_rep"]])


class DoctorDeleteView(StaffRequiredMixin, DeleteView):
    model = Doctor
    template_name = "admin_dashboard/doctor_confirm_delete.html"

    def get_success_url(self):
        return reverse("admin_dashboard:fieldrep_doctors", args=[self.kwargs["pk_rep"]])
