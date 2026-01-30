# admin_dashboard/views.py

from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.hashers import make_password
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import connection
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from campaign_management.models import Campaign, CampaignAssignment
from campaign_management.master_models import (
    MASTER_DB_ALIAS,
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


# ─────────────────────────────────────────────────────────
# Campaign param utilities
# ─────────────────────────────────────────────────────────
def _get_campaign_param(request) -> Optional[str]:
    """
    Single canonical way to read the campaign context across admin_dashboard.
    Treat it as a STRING identifier (brand_campaign_id) like the campaign module.
    """
    val = (
        request.POST.get("campaign")
        or request.GET.get("campaign_id")
        or request.GET.get("campaign")
        or request.GET.get("brand_campaign_id")
    )
    return str(val).strip() if val else None


def _campaign_dropdown_rows() -> List[Dict[str, str]]:
    """
    Returns list of dicts: [{"brand_campaign_id": "...", "name": "..."}, ...]
    Uses ORM first; falls back to raw SQL if UUID coercion issues exist.
    """
    try:
        rows = list(Campaign.objects.values("brand_campaign_id", "name").order_by("name"))
        return [
            {
                "brand_campaign_id": str(r.get("brand_campaign_id") or ""),
                "name": r.get("name") or "",
            }
            for r in rows
        ]
    except Exception:
        table = connection.ops.quote_name(Campaign._meta.db_table)
        bcid = connection.ops.quote_name("brand_campaign_id")
        name = connection.ops.quote_name("name")
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT {bcid}, {name} FROM {table} ORDER BY {name} ASC")
            return [
                {"brand_campaign_id": str(brand_campaign_id), "name": campaign_name or ""}
                for (brand_campaign_id, campaign_name) in cursor.fetchall()
            ]


def _campaign_pk_from_param(campaign_param: Optional[str]) -> Optional[int]:
    """
    Resolve the local DB PK for a campaign_param.
    - If numeric => treat as local pk
    - Else => treat as brand_campaign_id (string/uuid)
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

    # brand_campaign_id lookup via ORM; fallback raw SQL if UUID conversion explodes
    try:
        return (
            Campaign.objects.filter(brand_campaign_id=s)
            .values_list("pk", flat=True)
            .first()
        )
    except Exception:
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


def _normalize_brand_campaign_id(value: Optional[str]) -> Optional[str]:
    """
    Best-effort normalization for a campaign identifier to a dashed UUID string,
    used for session persistence and consistent filtering.
    """
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None

    if s.isdigit():
        # If local pk, convert to brand_campaign_id if possible
        try:
            bcid = Campaign.objects.filter(pk=int(s)).values_list("brand_campaign_id", flat=True).first()
            return str(bcid) if bcid else s
        except Exception:
            return s

    # If looks like UUID, normalize
    try:
        return str(uuid.UUID(s))
    except Exception:
        return s


def _master_campaign_id_from_any(value: Optional[str]) -> Optional[str]:
    """
    Convert a dashed UUID string (brand_campaign_id) to master campaign.id (hex32).
    Returns None if not UUID-like.
    """
    bcid = _normalize_brand_campaign_id(value)
    if not bcid:
        return None
    try:
        return uuid.UUID(str(bcid)).hex
    except Exception:
        return None


def _dashed_uuid_from_hex32(hex32: str) -> str:
    try:
        return str(uuid.UUID(hex=str(hex32)))
    except Exception:
        return str(hex32)


# ─────────────────────────────────────────────────────────
# Master DB sync helpers
# ─────────────────────────────────────────────────────────
def _master_unique_username(email: str) -> str:
    raw = (email or "").strip()
    candidate = (raw[:150] if raw else uuid.uuid4().hex[:12])

    if not MasterAuthUser.objects.using(MASTER_DB_ALIAS).filter(username=candidate).exists():
        return candidate

    local_part = (raw.split("@", 1)[0] or "user")[:140]
    for _ in range(10):
        cand = f"{local_part}_{uuid.uuid4().hex[:8]}"
        if not MasterAuthUser.objects.using(MASTER_DB_ALIAS).filter(username=cand).exists():
            return cand

    return uuid.uuid4().hex[:30]


def _master_find_user(email: str) -> Optional[MasterAuthUser]:
    email = (email or "").strip()
    if not email:
        return None

    # Prefer username=email (common pattern), fallback to email match
    obj = MasterAuthUser.objects.using(MASTER_DB_ALIAS).filter(username=email).first()
    if obj:
        return obj
    return MasterAuthUser.objects.using(MASTER_DB_ALIAS).filter(email=email).first()


def _master_upsert_user(local_user: User, old_email: Optional[str] = None) -> Optional[MasterAuthUser]:
    email = (local_user.email or "").strip()
    if not email:
        return None

    master_user = None
    if old_email and old_email.strip():
        master_user = _master_find_user(old_email.strip())

    if not master_user:
        master_user = _master_find_user(email)

    if not master_user:
        # create
        username = _master_unique_username(email)
        master_user = MasterAuthUser(
            username=username,
            email=email,
            first_name=getattr(local_user, "first_name", "") or "",
            last_name=getattr(local_user, "last_name", "") or "",
            is_staff=False,
            is_superuser=False,
            is_active=bool(getattr(local_user, "active", True)),
            password=make_password(None),
            date_joined=timezone.now(),
        )
        master_user.save(using=MASTER_DB_ALIAS)
        return master_user

    # update
    update_fields: List[str] = []

    if master_user.email != email:
        master_user.email = email
        update_fields.append("email")

    fn = getattr(local_user, "first_name", "") or ""
    ln = getattr(local_user, "last_name", "") or ""
    if fn and master_user.first_name != fn:
        master_user.first_name = fn
        update_fields.append("first_name")
    if ln and master_user.last_name != ln:
        master_user.last_name = ln
        update_fields.append("last_name")

    desired_active = bool(getattr(local_user, "active", True))
    if master_user.is_active != desired_active:
        master_user.is_active = desired_active
        update_fields.append("is_active")

    if update_fields:
        master_user.save(using=MASTER_DB_ALIAS, update_fields=update_fields)

    return master_user


def _master_upsert_fieldrep(
    master_user: MasterAuthUser,
    local_user: User,
    brand_id: Optional[str],
) -> Optional[MasterFieldRep]:
    if not master_user:
        return None

    fr = MasterFieldRep.objects.using(MASTER_DB_ALIAS).filter(user_id=master_user.id).first()
    email = (local_user.email or "").strip()

    full_name = (f"{getattr(local_user, 'first_name', '')} {getattr(local_user, 'last_name', '')}").strip()
    if not full_name:
        full_name = email.split("@", 1)[0] if email else ""

    phone = getattr(local_user, "phone_number", "") or ""
    supplied_id = getattr(local_user, "field_id", "") or ""
    active = bool(getattr(local_user, "active", True))

    if not fr:
        if not brand_id:
            # Can't create master FieldRep without a brand
            return None

        fr = MasterFieldRep(
            user_id=master_user.id,
            brand_id=str(brand_id),
            full_name=full_name or "",
            phone_number=phone,
            brand_supplied_field_rep_id=supplied_id,
            is_active=active,
        )
        fr.save(using=MASTER_DB_ALIAS)
        return fr

    update_fields: List[str] = []

    # only set brand if currently empty; avoid silently changing brand for existing reps
    if brand_id and not fr.brand_id:
        fr.brand_id = str(brand_id)
        update_fields.append("brand")

    if full_name and fr.full_name != full_name:
        fr.full_name = full_name
        update_fields.append("full_name")

    if fr.phone_number != phone:
        fr.phone_number = phone
        update_fields.append("phone_number")

    if fr.brand_supplied_field_rep_id != supplied_id:
        fr.brand_supplied_field_rep_id = supplied_id
        update_fields.append("brand_supplied_field_rep_id")

    if fr.is_active != active:
        fr.is_active = active
        update_fields.append("is_active")

    if update_fields:
        fr.save(using=MASTER_DB_ALIAS, update_fields=update_fields)

    return fr


def _master_link_fieldrep_to_campaign(master_fieldrep: MasterFieldRep, master_campaign_id: str) -> None:
    if not master_fieldrep or not master_campaign_id:
        return
    MasterCampaignFieldRep.objects.using(MASTER_DB_ALIAS).get_or_create(
        campaign_id=master_campaign_id,
        field_rep_id=master_fieldrep.id,
    )


def _sync_local_user_from_master(master_fr: MasterFieldRep) -> Optional[User]:
    """
    Ensure a local User exists for a master field rep (so existing portal features work).
    Matching key: email.
    """
    email = (getattr(master_fr.user, "email", "") or "").strip()
    if not email:
        return None

    full_name = (getattr(master_fr, "full_name", "") or "").strip()
    first_name = full_name
    last_name = ""
    if full_name and " " in full_name:
        parts = full_name.split()
        first_name = parts[0]
        last_name = " ".join(parts[1:])

    phone = getattr(master_fr, "phone_number", "") or ""
    supplied_id = getattr(master_fr, "brand_supplied_field_rep_id", "") or ""
    active = bool(getattr(master_fr, "is_active", True))

    # Find existing by email (assumed unique in your portal usage)
    u = User.objects.filter(email=email).first()
    if u:
        changed = False
        update_fields: List[str] = []

        if u.role != "field_rep":
            u.role = "field_rep"
            changed = True
            update_fields.append("role")

        if u.active != active:
            u.active = active
            changed = True
            update_fields.append("active")

        if u.phone_number != phone:
            u.phone_number = phone
            changed = True
            update_fields.append("phone_number")

        if u.field_id != supplied_id:
            u.field_id = supplied_id
            changed = True
            update_fields.append("field_id")

        # only fill names if empty locally
        if first_name and not u.first_name:
            u.first_name = first_name
            changed = True
            update_fields.append("first_name")
        if last_name and not u.last_name:
            u.last_name = last_name
            changed = True
            update_fields.append("last_name")

        if changed:
            u.save(update_fields=update_fields)
        return u

    # Create new local user with a safe unique username
    base = (email.split("@", 1)[0] or email)[:150]
    username = base
    i = 1
    while User.objects.filter(username=username).exists():
        suffix = f"_{i}"
        username = f"{base[:150 - len(suffix)]}{suffix}"
        i += 1

    return User.objects.create(
        username=username,
        email=email,
        first_name=first_name or "",
        last_name=last_name or "",
        phone_number=phone,
        field_id=supplied_id,
        role="field_rep",
        active=active,
    )


def _sync_fieldrep_to_master(local_user: User, campaign_param: Optional[str], old_email: Optional[str] = None) -> None:
    """
    Upsert master auth_user, master campaign_fieldrep, and master campaign_campaignfieldrep mapping.
    """
    master_campaign_id = _master_campaign_id_from_any(campaign_param)
    if not master_campaign_id:
        return

    # get master campaign -> brand_id
    master_campaign = MasterCampaign.objects.using(MASTER_DB_ALIAS).filter(pk=master_campaign_id).only("id", "brand_id").first()
    if not master_campaign:
        return

    brand_id = str(master_campaign.brand_id) if getattr(master_campaign, "brand_id", None) else None

    master_user = _master_upsert_user(local_user, old_email=old_email)
    if not master_user:
        return

    master_fr = _master_upsert_fieldrep(master_user, local_user, brand_id=brand_id)
    if not master_fr:
        return

    _master_link_fieldrep_to_campaign(master_fr, master_campaign_id)


def _deactivate_master_fieldrep_by_email(email: str, campaign_param: Optional[str]) -> None:
    """
    Used on delete: remove mappings (optionally for one campaign) and deactivate master user + fieldrep.
    """
    email = (email or "").strip()
    if not email:
        return

    master_user = _master_find_user(email)
    if not master_user:
        return

    master_fr = MasterFieldRep.objects.using(MASTER_DB_ALIAS).filter(user_id=master_user.id).first()
    if not master_fr:
        return

    master_campaign_id = _master_campaign_id_from_any(campaign_param) if campaign_param else None

    links = MasterCampaignFieldRep.objects.using(MASTER_DB_ALIAS).filter(field_rep_id=master_fr.id)
    if master_campaign_id:
        links = links.filter(campaign_id=master_campaign_id)
    links.delete()

    # deactivate (soft delete)
    master_fr.is_active = False
    master_fr.save(using=MASTER_DB_ALIAS, update_fields=["is_active"])

    master_user.is_active = False
    master_user.save(using=MASTER_DB_ALIAS, update_fields=["is_active"])


# ─────────────────────────────────────────────────────────
# MIXIN
# ─────────────────────────────────────────────────────────
class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return bool(getattr(self.request.user, "is_staff", False))

    def handle_no_permission(self):
        return redirect("admin:login")

    login_url = reverse_lazy("admin:login")

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
# BULK‑UPLOAD (kept as-is; local DB behavior unchanged)
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
                try:
                    campaign_obj = Campaign.objects.filter(brand_campaign_id=str(campaign_ref)).first()
                except Exception:
                    campaign_obj = None

            if campaign_obj:
                form.fields["campaign"].initial = campaign_obj

    return render(request, "admin_dashboard/bulk_upload.html", {"form": form})


# ─────────────────────────────────────────────────────────
# FIELD‑REP CRUD (local + master sync)
# ─────────────────────────────────────────────────────────
class FieldRepListView(StaffRequiredMixin, ListView):
    template_name = "admin_dashboard/fieldrep_list.html"
    context_object_name = "reps"
    paginate_by = 25

    def get_queryset(self):
        qs = User.objects.filter(role="field_rep", active=True).order_by("-id")
        q = (self.request.GET.get("q") or "").strip()

        # campaign filter (GET first, fallback session)
        campaign_filter = (
            self.request.GET.get("brand_campaign_id")
            or self.request.GET.get("campaign")
            or self.request.GET.get("campaign_id")
        )
        if not campaign_filter and hasattr(self.request, "session"):
            campaign_filter = self.request.session.get("brand_campaign_id")

        self._campaign_filter = campaign_filter
        self._master_email_to_fieldrep_id: Dict[str, int] = {}

        if campaign_filter:
            # persist normalized brand_campaign_id in session for redirect_to_fieldreps
            norm = _normalize_brand_campaign_id(campaign_filter)
            if norm and hasattr(self.request, "session"):
                self.request.session["brand_campaign_id"] = str(norm)

            # Prefer master mapping if campaign UUID-like
            master_campaign_id = _master_campaign_id_from_any(campaign_filter)
            if master_campaign_id:
                try:
                    master_rep_ids = list(
                        MasterCampaignFieldRep.objects.using(MASTER_DB_ALIAS)
                        .filter(campaign_id=master_campaign_id)
                        .values_list("field_rep_id", flat=True)
                    )

                    if not master_rep_ids:
                        return User.objects.none()

                    master_reps = (
                        MasterFieldRep.objects.using(MASTER_DB_ALIAS)
                        .select_related("user")
                        .filter(id__in=master_rep_ids, is_active=True)
                    )

                    emails: List[str] = []
                    for mr in master_reps:
                        email = (getattr(mr.user, "email", "") or "").strip()
                        if not email:
                            continue
                        emails.append(email)
                        self._master_email_to_fieldrep_id[email.lower()] = mr.id
                        _sync_local_user_from_master(mr)

                    if emails:
                        qs = qs.filter(email__in=emails)
                    else:
                        return User.objects.none()

                except Exception:
                    # If master query fails, fallback to local mapping
                    campaign_pk = _campaign_pk_from_param(campaign_filter)
                    if campaign_pk:
                        rep_ids = list(
                            FieldRepCampaign.objects.filter(campaign_id=campaign_pk)
                            .values_list("field_rep_id", flat=True)
                        )
                        qs = qs.filter(id__in=rep_ids) if rep_ids else User.objects.none()
                    else:
                        qs = User.objects.none()

            else:
                # Not UUID-like -> use local mapping only
                campaign_pk = _campaign_pk_from_param(campaign_filter)
                if campaign_pk:
                    rep_ids = list(
                        FieldRepCampaign.objects.filter(campaign_id=campaign_pk)
                        .values_list("field_rep_id", flat=True)
                    )
                    qs = qs.filter(id__in=rep_ids) if rep_ids else User.objects.none()
                else:
                    qs = User.objects.none()

        if q:
            qs = qs.filter(
                Q(field_id__icontains=q)
                | Q(email__icontains=q)
                | Q(phone_number__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )

        return qs.distinct()

    def get_context_data(self, **kw):
        ctx = super().get_context_data(**kw)
        reps: List[User] = list(ctx.get("reps") or [])
        rep_ids = [r.id for r in reps]

        campaign_filter = (
            self.request.GET.get("brand_campaign_id")
            or self.request.GET.get("campaign")
            or self.request.GET.get("campaign_id")
            or (self.request.session.get("brand_campaign_id") if hasattr(self.request, "session") else None)
        )

        ctx["q"] = self.request.GET.get("q", "")
        ctx["campaign_filter"] = str(campaign_filter) if campaign_filter else ""

        # Attach brand_campaigns string to each rep
        # If list is currently filtered by campaign, you can just show that campaign in the column.
        if campaign_filter:
            shown = _normalize_brand_campaign_id(campaign_filter) or str(campaign_filter)
            for rep in reps:
                rep.brand_campaigns = str(shown)
            return ctx

        # Otherwise show all campaigns for each rep.
        # Prefer master map if available (from get_queryset), else local join table.
        if getattr(self, "_master_email_to_fieldrep_id", None):
            try:
                master_ids = list(self._master_email_to_fieldrep_id.values())
                links = (
                    MasterCampaignFieldRep.objects.using(MASTER_DB_ALIAS)
                    .filter(field_rep_id__in=master_ids)
                    .values_list("field_rep_id", "campaign_id")
                )

                fr_to_campaigns: Dict[int, List[str]] = {}
                for fr_id, camp_id in links:
                    fr_to_campaigns.setdefault(int(fr_id), []).append(_dashed_uuid_from_hex32(str(camp_id)))

                for rep in reps:
                    fr_id = self._master_email_to_fieldrep_id.get((rep.email or "").lower())
                    vals = fr_to_campaigns.get(fr_id, []) if fr_id else []
                    # dedupe preserving order
                    seen = set()
                    uniq: List[str] = []
                    for v in vals:
                        sv = str(v)
                        if sv and sv not in seen:
                            seen.add(sv)
                            uniq.append(sv)
                    rep.brand_campaigns = ", ".join(uniq)

                return ctx

            except Exception:
                # fall back to local below
                pass

        # Local fallback: FieldRepCampaign join -> Campaign.brand_campaign_id
        campaign_data = (
            FieldRepCampaign.objects.filter(field_rep_id__in=rep_ids)
            .values("field_rep_id", "campaign__brand_campaign_id")
        )

        rep_campaigns: Dict[int, List[str]] = {}
        for item in campaign_data:
            rid = item.get("field_rep_id")
            bc = item.get("campaign__brand_campaign_id")
            if not rid or not bc:
                continue
            rep_campaigns.setdefault(rid, []).append(str(bc))

        for rep in reps:
            vals = rep_campaigns.get(rep.id, [])
            seen = set()
            uniq: List[str] = []
            for v in vals:
                if v and v not in seen:
                    seen.add(v)
                    uniq.append(v)
            rep.brand_campaigns = ", ".join(uniq)

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
        ctx["campaigns"] = _campaign_dropdown_rows()
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)

        campaign_param = _get_campaign_param(self.request)
        if campaign_param:
            # local mappings (portal DB)
            campaign_pk = _campaign_pk_from_param(campaign_param)
            if campaign_pk:
                CampaignAssignment.objects.get_or_create(field_rep=self.object, campaign_id=campaign_pk)
                FieldRepCampaign.objects.get_or_create(field_rep=self.object, campaign_id=campaign_pk)
            else:
                messages.warning(self.request, f"Campaign '{campaign_param}' not found in portal DB.")

            # master mappings
            try:
                _sync_fieldrep_to_master(self.object, campaign_param)
            except Exception as e:
                messages.warning(self.request, f"Master DB sync failed: {e}")

        return response

    def get_success_url(self):
        base = reverse("admin_dashboard:fieldrep_list")
        campaign_param = _get_campaign_param(self.request)
        if not campaign_param:
            return base

        # keep consistent with your templates that pass ?campaign=...
        return f"{base}?campaign={campaign_param}"


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
        old_email = (self.get_object().email or "").strip()
        response = super().form_valid(form)

        campaign_param = _get_campaign_param(self.request)
        if campaign_param:
            campaign_pk = _campaign_pk_from_param(campaign_param)
            if campaign_pk:
                CampaignAssignment.objects.get_or_create(field_rep=self.object, campaign_id=campaign_pk)
                FieldRepCampaign.objects.get_or_create(field_rep=self.object, campaign_id=campaign_pk)

            try:
                _sync_fieldrep_to_master(self.object, campaign_param, old_email=old_email)
            except Exception as e:
                messages.warning(self.request, f"Master DB sync failed: {e}")

        return response

    def get_success_url(self):
        base = reverse("admin_dashboard:fieldrep_list")
        campaign_param = _get_campaign_param(self.request)
        if not campaign_param:
            return base
        return f"{base}?campaign={campaign_param}"


class FieldRepDeleteView(StaffRequiredMixin, DeleteView):
    model = User
    template_name = "admin_dashboard/fieldrep_confirm_delete.html"
    success_url = reverse_lazy("admin_dashboard:fieldrep_list")

    def delete(self, request, *args, **kw):
        self.object = self.get_object()

        # local cleanup
        DoctorEngagement.objects.filter(short_link__created_by=self.object).delete()

        # master cleanup (best-effort)
        try:
            campaign_param = _get_campaign_param(request)
            _deactivate_master_fieldrep_by_email(self.object.email, campaign_param)
        except Exception:
            pass

        return super().delete(request, *args, **kw)

    def get_success_url(self):
        base = reverse("admin_dashboard:fieldrep_list")
        campaign_param = _get_campaign_param(self.request)
        if not campaign_param:
            return base
        return f"{base}?campaign={campaign_param}"


# ─────────────────────────────────────────────────────────
# DOCTOR CRUD (list/create, edit, delete)
# ─────────────────────────────────────────────────────────
class FieldRepDoctorView(StaffRequiredMixin, CreateView):
    """List + Create on one page."""
    template_name = "admin_dashboard/fieldrep_doctors.html"
    form_class = DoctorForm

    def dispatch(self, request, *args, **kwargs):
        # support both URL kwarg styles: pk and rep_id
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
