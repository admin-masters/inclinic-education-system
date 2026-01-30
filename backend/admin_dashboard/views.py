# admin_dashboard/views.py

import uuid
import string

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.hashers import make_password
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import connection, connections, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from campaign_management.models import Campaign, CampaignAssignment
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

from .forms import DoctorForm, FieldRepBulkUploadForm, FieldRepForm
from .models import FieldRepCampaign
from utils.recaptcha import recaptcha_required


MASTER_DB_ALIAS = getattr(settings, "MASTER_DB_ALIAS", "master")


# ─────────────────────────────────────────────────────────
# Campaign param helpers (canonicalize campaign context)
# ─────────────────────────────────────────────────────────

import uuid
from django.db import connection
from django.db import models as dj_models

def _get_campaign_param_any(request):
    """
    Read campaign context from GET/POST first, then fall back to session.
    Always returns a STRING (or None).
    """
    v = (
        request.POST.get("campaign")
        or request.GET.get("campaign_id")
        or request.GET.get("campaign")
        or request.GET.get("brand_campaign_id")
    )
    if not v and hasattr(request, "session"):
        v = request.session.get("brand_campaign_id")

    if v is None:
        return None

    s = str(v).strip()
    return s or None


def _resolve_campaign_pk(campaign_param):
    """
    Convert campaign_param -> Campaign.pk safely.

    - Numeric strings => Campaign.pk
    - Otherwise => treat as brand_campaign_id (supports dashed/undashed UUID strings)
    - NEVER raises ValueError; returns None if it cannot resolve.
    """
    if not campaign_param:
        return None

    s = str(campaign_param).strip()
    if not s:
        return None

    if s.isdigit():
        try:
            return int(s)
        except ValueError:
            return None

    # Resolve via brand_campaign_id
    try:
        field = Campaign._meta.get_field("brand_campaign_id")

        # If model uses UUIDField, only accept valid UUID input
        if isinstance(field, dj_models.UUIDField):
            try:
                u = uuid.UUID(s)
            except Exception:
                return None
            return (
                Campaign.objects.filter(brand_campaign_id=u)
                .values_list("pk", flat=True)
                .first()
            )

        # CharField/TextField case (supports both dashed and dashless)
        candidates = {s, s.replace("-", "")}
        try:
            u = uuid.UUID(s)
            candidates.add(str(u))
            candidates.add(u.hex)
        except Exception:
            pass

        return (
            Campaign.objects.filter(brand_campaign_id__in=list(candidates))
            .values_list("pk", flat=True)
            .first()
        )

    except Exception:
        # Absolute fallback: raw SQL (no Python UUID coercion)
        table = connection.ops.quote_name(Campaign._meta.db_table)
        pk_col = connection.ops.quote_name(Campaign._meta.pk.column)
        bcid_col = connection.ops.quote_name("brand_campaign_id")

        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {pk_col} FROM {table} WHERE {bcid_col}=%s LIMIT 1",
                [s],
            )
            row = cursor.fetchone()
        return row[0] if row else None


def _rep_campaign_map(rep_ids, campaign_pk=None):
    """
    Raw SQL join to avoid UUID coercion issues when reading campaign.brand_campaign_id.
    Returns {rep_id: [brand_campaign_id, ...]}
    """
    if not rep_ids:
        return {}

    frc_table = connection.ops.quote_name(FieldRepCampaign._meta.db_table)
    camp_table = connection.ops.quote_name(Campaign._meta.db_table)

    rep_col = connection.ops.quote_name("field_rep_id")
    frc_campaign_col = connection.ops.quote_name("campaign_id")

    camp_pk_col = connection.ops.quote_name(Campaign._meta.pk.column)
    camp_bcid_col = connection.ops.quote_name("brand_campaign_id")

    placeholders = ", ".join(["%s"] * len(rep_ids))
    sql = (
        f"SELECT frc.{rep_col}, c.{camp_bcid_col} "
        f"FROM {frc_table} AS frc "
        f"INNER JOIN {camp_table} AS c ON c.{camp_pk_col} = frc.{frc_campaign_col} "
        f"WHERE frc.{rep_col} IN ({placeholders})"
    )
    params = list(rep_ids)

    if campaign_pk:
        sql += f" AND frc.{frc_campaign_col} = %s"
        params.append(int(campaign_pk))

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    out = {}
    for rep_id, bcid in rows:
        if rep_id is None or bcid is None:
            continue
        out.setdefault(int(rep_id), []).append(str(bcid))

    return out


def _brand_campaign_id_from_param(campaign_param: str | None) -> str | None:
    """
    If campaign_param is numeric => treat as local Campaign.pk and return its brand_campaign_id.
    Else => return as string.
    """
    if not campaign_param:
        return None
    s = str(campaign_param).strip()
    if not s:
        return None

    if s.isdigit():
        try:
            pk = int(s)
        except ValueError:
            return None
        bcid = Campaign.objects.filter(pk=pk).values_list("brand_campaign_id", flat=True).first()
        return str(bcid) if bcid else None

    return s


def _normalize_master_campaign_id(brand_campaign_id: str | None) -> str | None:
    """
    Master DB stores campaign_id in join table without hyphens (32 hex).
    Return 32-hex lowercase string when possible.
    """
    if not brand_campaign_id:
        return None
    raw = str(brand_campaign_id).strip()
    if not raw:
        return None

    # Remove hyphens
    hex32 = raw.replace("-", "").lower()

    # Validate length & hex-ness
    if len(hex32) == 32 and all(ch in string.hexdigits for ch in hex32):
        return hex32.lower()

    return None


def _uuid_dashed_from_hex32(hex32: str) -> str:
    """
    Convert 'f44996be19374f5e95ae5f1bb333b66c' => 'f44996be-1937-4f5e-95ae-5f1bb333b66c'
    Best-effort; returns input if conversion fails.
    """
    try:
        return str(uuid.UUID(hex=str(hex32)))
    except Exception:
        return str(hex32)


def _campaign_dropdown_rows():
    """
    Returns list of dicts: [{"brand_campaign_id": "...", "name": "..."}, ...]
    Always strings for brand_campaign_id (prevents UUID join / template issues).
    """
    try:
        return list(Campaign.objects.values("brand_campaign_id", "name").order_by("name"))
    except Exception:
        # Fallback raw SQL
        table = connection.ops.quote_name(Campaign._meta.db_table)
        bcid = connection.ops.quote_name("brand_campaign_id")
        name = connection.ops.quote_name("name")
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT {bcid}, {name} FROM {table} ORDER BY {name} ASC")
            return [{"brand_campaign_id": str(x), "name": y} for (x, y) in cursor.fetchall()]


def _campaign_pk_from_param(campaign_param):
    """
    Resolve local DB PK for a campaign_param.
    - If numeric => pk
    - Else => brand_campaign_id lookup
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

    try:
        return (
            Campaign.objects.filter(brand_campaign_id=campaign_param)
            .values_list("pk", flat=True)
            .first()
        )
    except Exception:
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
# Master DB sync helpers (FieldRep + mapping)
# ─────────────────────────────────────────────────────────

def _master_available() -> bool:
    try:
        _ = connections[MASTER_DB_ALIAS]
        return True
    except Exception:
        return False


def _master_get_campaign(master_campaign_id: str) -> MasterCampaign | None:
    try:
        return MasterCampaign.objects.using(MASTER_DB_ALIAS).filter(id=master_campaign_id).first()
    except Exception:
        return None


def _master_upsert_auth_user_from_portal_user(portal_user: User) -> MasterAuthUser | None:
    """
    Create/update auth_user on master using portal user's email as username.
    """
    email = (portal_user.email or "").strip()
    if not email:
        return None

    username = email
    if len(username) > 150:
        # Keep it deterministic-ish but within length.
        username = (email[:140] + "-" + uuid.uuid4().hex[:9])

    try:
        qs = MasterAuthUser.objects.using(MASTER_DB_ALIAS).filter(username=username)
        master_user = qs.first()

        if master_user:
            dirty_fields = []
            if (master_user.email or "") != email:
                master_user.email = email
                dirty_fields.append("email")

            # Optional: keep names in sync if you ever store them in portal User
            fn = (portal_user.first_name or "").strip()
            ln = (portal_user.last_name or "").strip()
            if fn and master_user.first_name != fn:
                master_user.first_name = fn
                dirty_fields.append("first_name")
            if ln and master_user.last_name != ln:
                master_user.last_name = ln
                dirty_fields.append("last_name")

            # Keep active in sync
            is_active = bool(getattr(portal_user, "active", True))
            if master_user.is_active != is_active:
                master_user.is_active = is_active
                dirty_fields.append("is_active")

            if dirty_fields:
                master_user.save(using=MASTER_DB_ALIAS, update_fields=dirty_fields)

            return master_user

        # Create
        master_user = MasterAuthUser(
            username=username,
            email=email,
            first_name=(portal_user.first_name or "").strip(),
            last_name=(portal_user.last_name or "").strip(),
            is_staff=False,
            is_superuser=False,
            is_active=bool(getattr(portal_user, "active", True)),
            date_joined=timezone.now(),
            password=make_password(None),  # unusable password unless you set one later
        )
        master_user.save(using=MASTER_DB_ALIAS)
        return master_user

    except Exception:
        return None


def _master_upsert_fieldrep(
    *,
    portal_user: User,
    master_user: MasterAuthUser,
    master_campaign: MasterCampaign | None,
) -> MasterFieldRep | None:
    """
    Create/update campaign_fieldrep row in master DB.
    Brand is derived from master_campaign.brand_id (preferred).
    """
    if not master_user:
        return None

    # Determine brand_id
    brand_id = getattr(master_campaign, "brand_id", None) if master_campaign else None
    if not brand_id:
        # If no campaign context, try to find an existing rep by email/field_id and reuse its brand
        try:
            existing = (
                MasterFieldRep.objects.using(MASTER_DB_ALIAS)
                .select_related("user")
                .filter(user_id=master_user.id)
                .first()
            )
            if existing and getattr(existing, "brand_id", None):
                brand_id = existing.brand_id
        except Exception:
            brand_id = None

    if not brand_id:
        # Cannot create a master fieldrep row without brand (in your schema this FK is required).
        return None

    full_name = (portal_user.get_full_name() or "").strip()
    if not full_name:
        full_name = (portal_user.first_name or "").strip()
    if not full_name:
        # last fallback: use email local-part
        full_name = (portal_user.email or "Field Rep").split("@", 1)[0]

    phone = (getattr(portal_user, "phone_number", "") or "").strip()
    field_id = (getattr(portal_user, "field_id", "") or "").strip()

    try:
        rep = MasterFieldRep.objects.using(MASTER_DB_ALIAS).filter(user_id=master_user.id).first()
        if rep:
            dirty = []
            if rep.brand_id != brand_id:
                rep.brand_id = brand_id
                dirty.append("brand")
            if rep.full_name != full_name:
                rep.full_name = full_name
                dirty.append("full_name")
            if (rep.phone_number or "") != phone:
                rep.phone_number = phone
                dirty.append("phone_number")
            if (rep.brand_supplied_field_rep_id or "") != field_id:
                rep.brand_supplied_field_rep_id = field_id
                dirty.append("brand_supplied_field_rep_id")

            is_active = bool(getattr(portal_user, "active", True))
            if rep.is_active != is_active:
                rep.is_active = is_active
                dirty.append("is_active")

            if dirty:
                rep.save(using=MASTER_DB_ALIAS, update_fields=dirty)
            return rep

        # Create
        rep = MasterFieldRep(
            user_id=master_user.id,
            brand_id=brand_id,
            full_name=full_name,
            phone_number=phone,
            brand_supplied_field_rep_id=field_id,
            is_active=bool(getattr(portal_user, "active", True)),
        )
        rep.save(using=MASTER_DB_ALIAS)
        return rep

    except Exception:
        return None


def _master_link_rep_to_campaign(master_campaign_id: str, master_fieldrep: MasterFieldRep) -> None:
    """
    Ensure campaign_campaignfieldrep row exists in master.
    """
    if not master_campaign_id or not master_fieldrep:
        return
    try:
        MasterCampaignFieldRep.objects.using(MASTER_DB_ALIAS).get_or_create(
            campaign_id=master_campaign_id,
            field_rep_id=master_fieldrep.id,
        )
    except Exception:
        return


def _sync_fieldrep_to_master(request, portal_user: User, campaign_param: str | None) -> None:
    """
    Best-effort sync to master DB.
    Does NOT break portal flow if master DB is unavailable.
    """
    if not _master_available():
        return

    bcid = _brand_campaign_id_from_param(campaign_param)
    master_campaign_id = _normalize_master_campaign_id(bcid) if bcid else None
    master_campaign = _master_get_campaign(master_campaign_id) if master_campaign_id else None

    try:
        with transaction.atomic(using=MASTER_DB_ALIAS):
            master_user = _master_upsert_auth_user_from_portal_user(portal_user)
            if not master_user:
                messages.warning(request, "Master sync: could not create/update master auth_user (missing email).")
                return

            master_rep = _master_upsert_fieldrep(
                portal_user=portal_user,
                master_user=master_user,
                master_campaign=master_campaign,
            )
            if not master_rep:
                messages.warning(
                    request,
                    "Master sync: could not create/update master FieldRep (brand missing; add via a campaign context).",
                )
                return

            if master_campaign_id:
                _master_link_rep_to_campaign(master_campaign_id, master_rep)

    except Exception:
        # Do not block portal operations
        messages.warning(request, "Master sync: failed due to a master DB error.")


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
# DASHBOARD (unchanged)
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
# BULK‑UPLOAD (unchanged except campaign param normalization)
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

        campaign_ref = _get_campaign_param_any(request)
        if campaign_ref:
            campaign_obj = None
            # Try as local pk first
            if str(campaign_ref).isdigit():
                try:
                    campaign_obj = Campaign.objects.get(pk=int(campaign_ref))
                except Exception:
                    campaign_obj = None
            if not campaign_obj:
                campaign_obj = Campaign.objects.filter(brand_campaign_id=str(campaign_ref)).first()

            if campaign_obj:
                form.fields["campaign"].initial = campaign_obj

    return render(request, "admin_dashboard/bulk_upload.html", {"form": form})


# ─────────────────────────────────────────────────────────
# FIELD‑REP CRUD
# ─────────────────────────────────────────────────────────

class FieldRepListView(StaffRequiredMixin, ListView):
    template_name = "admin_dashboard/fieldrep_list.html"
    context_object_name = "reps"
    paginate_by = 25

    def get_queryset(self):
        qs = User.objects.filter(role="field_rep", active=True).order_by("-id")
        q = self.request.GET.get("q", "")

        campaign_param = _get_campaign_param_any(self.request)
        campaign_pk = _resolve_campaign_pk(campaign_param)

        # If we had a filter (especially from session) but it's invalid, clear it so
        # /admin_dashboard/fieldreps/ doesn't keep crashing.
        if campaign_param and not campaign_pk and hasattr(self.request, "session"):
            self.request.session.pop("brand_campaign_id", None)

        if campaign_pk:
            rep_ids = list(
                FieldRepCampaign.objects.filter(
                    campaign_id=campaign_pk,
                    field_rep__active=True
                ).values_list("field_rep_id", flat=True)
            )
            if rep_ids:
                qs = qs.filter(id__in=rep_ids)
            else:
                return User.objects.none()

        if q:
            qs = qs.filter(
                Q(field_id__icontains=q)
                | Q(email__icontains=q)
                | Q(phone_number__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        reps = ctx.get("reps") or []
        rep_ids = [r.id for r in reps]

        campaign_param = _get_campaign_param_any(self.request)
        campaign_pk = _resolve_campaign_pk(campaign_param)

        # Persist filter (so your dashboard redirect can keep it)
        if campaign_param and hasattr(self.request, "session"):
            self.request.session["brand_campaign_id"] = str(campaign_param)

        rep_campaigns = _rep_campaign_map(rep_ids, campaign_pk if campaign_pk else None)

        for rep in reps:
            vals = rep_campaigns.get(rep.id, [])
            # dedupe while preserving order
            seen = set()
            uniq = []
            for v in vals:
                if v and v not in seen:
                    seen.add(v)
                    uniq.append(v)
            rep.brand_campaigns = ", ".join(uniq)

        ctx["q"] = self.request.GET.get("q", "")
        ctx["campaign_filter"] = campaign_param or ""
        return ctx



class FieldRepCreateView(StaffRequiredMixin, CreateView):
    model         = User
    form_class    = FieldRepForm
    template_name = "admin_dashboard/fieldrep_form.html"
    success_url   = reverse_lazy("admin_dashboard:fieldrep_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["campaign_param"] = (
            self.request.POST.get("campaign")
            or self.request.GET.get("campaign_id")
            or self.request.GET.get("campaign")
            or self.request.GET.get("brand_campaign_id")
        )
        return kwargs

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        campaign_param = (
            self.request.POST.get("campaign")
            or self.request.GET.get("campaign_id")
            or self.request.GET.get("campaign")
            or self.request.GET.get("brand_campaign_id")
        )
        if campaign_param:
            ctx["campaign_param"] = campaign_param
        ctx["campaigns"] = Campaign.objects.all().order_by("name")
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)

        campaign_param = (
            self.request.POST.get("campaign")
            or self.request.GET.get("campaign_id")
            or self.request.GET.get("campaign")
            or self.request.GET.get("brand_campaign_id")
        )
        if campaign_param:
            campaign = None
            try:
                campaign_pk = int(campaign_param)
                campaign = get_object_or_404(Campaign, pk=campaign_pk)
            except (ValueError, TypeError):
                campaign = get_object_or_404(Campaign, brand_campaign_id=campaign_param)

            if campaign:
                FieldRepCampaign.objects.get_or_create(field_rep=self.object, campaign=campaign)

        return response

    def get_success_url(self):
        base = reverse("admin_dashboard:fieldrep_list")
        campaign_param = (
            self.request.POST.get("campaign")
            or self.request.GET.get("campaign_id")
            or self.request.GET.get("campaign")
            or self.request.GET.get("brand_campaign_id")
        )
        if not campaign_param:
            return base
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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["campaign_param"] = (
            self.request.POST.get("campaign")
            or self.request.GET.get("campaign_id")
            or self.request.GET.get("campaign")
            or self.request.GET.get("brand_campaign_id")
        )
        return kwargs

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        campaign_param = (
            self.request.POST.get("campaign")
            or self.request.GET.get("campaign_id")
            or self.request.GET.get("campaign")
            or self.request.GET.get("brand_campaign_id")
        )
        if campaign_param:
            ctx["campaign_param"] = campaign_param
        ctx["campaigns"] = Campaign.objects.all().order_by("name")
        return ctx

    def form_valid(self, form):
        # email uniqueness per brand is validated inside FieldRepForm.clean_email()
        response = super().form_valid(form)

        # Optional: if a campaign is selected during edit, ensure mapping exists
        campaign_param = (
            self.request.POST.get("campaign")
            or self.request.GET.get("campaign_id")
            or self.request.GET.get("campaign")
            or self.request.GET.get("brand_campaign_id")
        )
        if campaign_param:
            try:
                campaign_pk = int(campaign_param)
                campaign = get_object_or_404(Campaign, pk=campaign_pk)
            except (ValueError, TypeError):
                campaign = get_object_or_404(Campaign, brand_campaign_id=campaign_param)

            FieldRepCampaign.objects.get_or_create(field_rep=self.object, campaign=campaign)

        return response

    def get_success_url(self):
        base = reverse("admin_dashboard:fieldrep_list")
        campaign_param = (
            self.request.GET.get("campaign_id")
            or self.request.GET.get("campaign")
            or self.request.GET.get("brand_campaign_id")
        )
        if not campaign_param:
            return base
        try:
            int(campaign_param)
            return f"{base}?campaign_id={campaign_param}"
        except (TypeError, ValueError):
            return f"{base}?brand_campaign_id={campaign_param}"


class FieldRepDeleteView(StaffRequiredMixin, DeleteView):
    model = User
    template_name = "admin_dashboard/fieldrep_confirm_delete.html"
    success_url = reverse_lazy("admin_dashboard:fieldrep_list")

    def delete(self, request, *args, **kw):
        self.object = self.get_object()
        DoctorEngagement.objects.filter(short_link__created_by=self.object).delete()

        # Best-effort: deactivate master FieldRep + master auth_user
        if _master_available():
            try:
                email = (self.object.email or "").strip()
                if email:
                    # our master upsert uses username=email; deactivate both
                    mu = MasterAuthUser.objects.using(MASTER_DB_ALIAS).filter(username=email).first()
                    if mu and mu.is_active:
                        mu.is_active = False
                        mu.save(using=MASTER_DB_ALIAS, update_fields=["is_active"])

                    if mu:
                        mr = MasterFieldRep.objects.using(MASTER_DB_ALIAS).filter(user_id=mu.id).first()
                        if mr and mr.is_active:
                            mr.is_active = False
                            mr.save(using=MASTER_DB_ALIAS, update_fields=["is_active"])
            except Exception:
                pass

        return super().delete(request, *args, **kw)

    def get_success_url(self):
        base = reverse("admin_dashboard:fieldrep_list")
        campaign_param = _get_campaign_param_any(self.request)
        if not campaign_param:
            return base
        try:
            int(str(campaign_param))
            return f"{base}?campaign_id={campaign_param}"
        except Exception:
            return f"{base}?brand_campaign_id={campaign_param}"


# ─────────────────────────────────────────────────────────
# DOCTOR CRUD (list/create/edit/delete) — unchanged, but dispatch supports pk or rep_id
# ─────────────────────────────────────────────────────────

class FieldRepDoctorView(StaffRequiredMixin, CreateView):
    template_name = "admin_dashboard/fieldrep_doctors.html"
    form_class = DoctorForm

    def dispatch(self, request, *args, **kwargs):
        rep_pk = kwargs.get("pk") or kwargs.get("rep_id")
        self.rep = get_object_or_404(User, pk=rep_pk, role="field_rep")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.rep = self.rep
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("admin_dashboard:fieldrep_doctors", args=[self.rep.pk])

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        ctx["rep"] = self.rep
        ctx["doctors"] = self.rep.doctors.all()
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
