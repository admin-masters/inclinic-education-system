# sharing_management/views.py
from __future__ import annotations

import json
import re
import urllib.parse
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password as django_check_password
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt

from .decorators import field_rep_required
from .forms import CollateralForm, ShareForm
from sharing_management.forms import CalendarCampaignCollateralForm

from .models import (
    CollateralTransaction,
    FieldRepSecurityProfile,
    SecurityQuestion,
    ShareLog,
    VideoTrackingLog,
)

from campaign_management.master_models import (
    MasterAuthUser,
    MasterCampaign,
    MasterCampaignFieldRep,
    MasterFieldRep,
)

from collateral_management.models import CampaignCollateral as CMCampaignCollateral
from collateral_management.models import Collateral
from collateral_management.models import CollateralMessage
from doctor_viewer.models import Doctor, DoctorEngagement
from shortlink_management.models import ShortLink
from shortlink_management.utils import generate_short_code

from sharing_management.services.transactions import (
    mark_downloaded_pdf,
    mark_pdf_progress,
    mark_video_event,
    mark_viewed,
    upsert_from_sharelog,
)

from utils.recaptcha import recaptcha_required

import logging
import re
from django.utils import timezone
from django.conf import settings

from django.db import connections
from django.db.utils import OperationalError
from django.contrib.auth.hashers import make_password
import os
import uuid

logger = logging.getLogger(__name__)

# Toggle if you want to disable later
SM_VERBOSE_LOGS = getattr(settings, "SHARING_MANAGEMENT_VERBOSE_LOGS", True)


def _smdbg(msg: str) -> None:
    """
    Sharing-management debug logger.
    Enabled when settings.DEBUG=True OR settings.SHARING_MGMT_DEBUG=True
    """
    try:
        from django.conf import settings
        if getattr(settings, "DEBUG", False) or getattr(settings, "SHARING_MGMT_DEBUG", False):
            print(f"[SMDBG] {msg}", flush=True)
    except Exception:
        # Never break runtime due to logging
        pass

def _fieldrep_dbg_enabled() -> bool:
    return bool(getattr(settings, "FIELDREP_DEBUG_LOGS", False) or os.environ.get("FIELDREP_DEBUG_LOGS") == "1")

def _dbg(request, msg: str, **kv) -> None:
    if not _fieldrep_dbg_enabled():
        return

    rid = getattr(request, "_fieldrep_rid", None) if request else None
    if not rid:
        rid = uuid.uuid4().hex[:10]
        if request:
            setattr(request, "_fieldrep_rid", rid)

    def _safe(v):
        try:
            s = repr(v)
        except Exception:
            s = "<unrepr>"
        if len(s) > 400:
            s = s[:400] + "...(truncated)"
        return s

    parts = " ".join([f"{k}={_safe(v)}" for k, v in kv.items()])
    line = f"[FIELDREP][{rid}] {msg}" + (f" | {parts}" if parts else "")
    print(line)


_CAMPAIGN_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_CAMPAIGN_HEX32_RE = re.compile(r"^[0-9a-fA-F]{32}$")

def _normalize_campaign_id(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    s = s.lower()
    if _CAMPAIGN_UUID_RE.match(s):
        return s.replace("-", "")
    if _CAMPAIGN_HEX32_RE.match(s):
        return s
    s2 = re.sub(r"[^0-9a-f]", "", s)
    if len(s2) == 32:
        return s2
    return s.replace("-", "")

def _get_security_questions_safe(request=None):
    """
    Fix for: (1054) Unknown column sharing_management_securityquestion.is_active
    If ORM fails due to missing column or manager filter, fallback to raw SQL.
    """
    table = "sharing_management_securityquestion"
    try:
        from .models import SecurityQuestion
        table = SecurityQuestion._meta.db_table
        # IMPORTANT: don't filter is_active here; just try a minimal projection
        rows = list(SecurityQuestion.objects.all().values_list("id", "question_txt"))
        _dbg(request, "SecurityQuestion ORM OK", table=table, count=len(rows))
        return rows
    except OperationalError as oe:
        _dbg(request, "SecurityQuestion ORM OperationalError", table=table, err=str(oe))
    except Exception as e:
        _dbg(request, "SecurityQuestion ORM error", table=table, err=str(e))

    # raw SQL fallback
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT id, question_txt FROM {table}")
            rows = cursor.fetchall()
        _dbg(request, "SecurityQuestion raw SQL OK", table=table, count=len(rows))
        return rows
    except Exception as e:
        _dbg(request, "SecurityQuestion raw SQL FAILED", table=table, err=str(e))
        return []

def _master_get_fieldrep(field_id: str, gmail_id: str, request=None):
    """
    Attempts to locate field rep in MASTER DB via master_models.
    """
    alias = _master_db_alias()
    try:
        from campaign_management.master_models import MasterFieldRep
    except Exception as e:
        _dbg(request, "IMPORT FAIL master_models.MasterFieldRep", err=str(e))
        return None

    qs = MasterFieldRep.objects.using(alias).select_related("user").filter(is_active=True)

    attempts = []
    if field_id and gmail_id:
        attempts.append(("brand_supplied_field_rep_id+email",
                         qs.filter(brand_supplied_field_rep_id__iexact=field_id, user__email__iexact=gmail_id)))
        attempts.append(("username+email",
                         qs.filter(user__username__iexact=field_id, user__email__iexact=gmail_id)))
    if gmail_id:
        attempts.append(("email-only", qs.filter(user__email__iexact=gmail_id)))

    for label, q in attempts:
        rep = q.first()
        _dbg(request, "MASTER fieldrep lookup", label=label, found=bool(rep), alias=alias,
             field_id=field_id, gmail=gmail_id,
             master_fieldrep_id=getattr(rep, "pk", None),
             master_user_id=getattr(rep, "user_id", None),
             master_brand_id=getattr(rep, "brand_id", None))
        if rep:
            return rep
    return None

def _master_is_assigned(master_rep, campaign_raw: str, request=None) -> bool:
    alias = _master_db_alias()
    if not master_rep or not campaign_raw:
        return False

    try:
        from campaign_management.master_models import MasterCampaignFieldRep
    except Exception as e:
        _dbg(request, "IMPORT FAIL MasterCampaignFieldRep", err=str(e))
        return False

    norm = _normalize_campaign_id(campaign_raw)
    candidates = []
    for c in [campaign_raw, norm, (campaign_raw or "").replace("-", ""), (campaign_raw or "").lower().replace("-", "")]:
        c = (c or "").strip()
        if c and c not in candidates:
            candidates.append(c)

    qs = MasterCampaignFieldRep.objects.using(alias).filter(field_rep_id=master_rep.pk, campaign_id__in=candidates)
    exists = qs.exists()

    # Extra debug samples
    if _fieldrep_dbg_enabled():
        rep_campaigns = list(
            MasterCampaignFieldRep.objects.using(alias)
            .filter(field_rep_id=master_rep.pk)
            .values_list("campaign_id", flat=True)[:20]
        )
        campaign_reps = list(
            MasterCampaignFieldRep.objects.using(alias)
            .filter(campaign_id__in=candidates)
            .values_list("field_rep_id", flat=True)[:20]
        )
        _dbg(request, "MASTER assignment check",
             alias=alias, campaign_raw=campaign_raw, norm=norm, candidates=candidates,
             exists=exists, master_fieldrep_id=master_rep.pk,
             rep_campaigns_sample=rep_campaigns, campaign_reps_sample=campaign_reps)
    return exists

def _ensure_portal_fieldrep_user(email: str, field_id: str, request=None):
    """
    Ensures there is a portal user (AUTH_USER_MODEL) for use in ShortLink.created_by, etc.
    Does not overwrite password if user exists.
    """
    UserModel = get_user_model()

    user = None
    # Try field_id lookup if field exists
    if field_id:
        try:
            user = UserModel.objects.filter(field_id=field_id, role="field_rep").first()
            _dbg(request, "PORTAL user lookup by field_id", found=bool(user), field_id=field_id)
        except Exception as e:
            _dbg(request, "PORTAL user lookup by field_id failed", err=str(e))

    if not user and email:
        try:
            user = UserModel.objects.filter(email__iexact=email, role="field_rep").first()
            _dbg(request, "PORTAL user lookup by email", found=bool(user), email=email)
        except Exception as e:
            _dbg(request, "PORTAL user lookup by email failed", err=str(e))

    if not user:
        base = (email.split("@")[0] if email and "@" in email else f"fieldrep_{field_id or uuid.uuid4().hex[:6]}").strip()
        base = (base or "fieldrep")[:140]
        username = base
        suffix = 0
        while UserModel.objects.filter(username=username).exists():
            suffix += 1
            username = f"{base}_{suffix}"[:150]

        pwd = UserModel.objects.make_random_password() if hasattr(UserModel.objects, "make_random_password") else uuid.uuid4().hex
        if hasattr(UserModel.objects, "create_user"):
            user = UserModel.objects.create_user(username=username, email=(email or "").lower(), password=pwd)
        else:
            user = UserModel(username=username, email=(email or "").lower())
            try:
                user.set_password(pwd)
            except Exception:
                pass
            user.save()

        _dbg(request, "PORTAL user created", portal_user_id=user.id, username=getattr(user, "username", None), email=getattr(user, "email", None))

    # Normalize fields
    changed = False
    if hasattr(user, "role") and getattr(user, "role", None) != "field_rep":
        user.role = "field_rep"
        changed = True
    if hasattr(user, "active") and not getattr(user, "active", True):
        user.active = True
        changed = True
    elif hasattr(user, "is_active") and not getattr(user, "is_active", True):
        user.is_active = True
        changed = True
    if field_id and hasattr(user, "field_id") and getattr(user, "field_id", "") != field_id:
        user.field_id = field_id
        changed = True

    if changed:
        user.save()
        _dbg(request, "PORTAL user updated", portal_user_id=user.id, field_id=getattr(user, "field_id", None), role=getattr(user, "role", None))

    return user


def _portal_sync_assignment(portal_user, brand_campaign_id: str, request=None):
    """
    Best-effort: ensures CampaignAssignment/FieldRepCampaign exist in portal DB if campaign exists there.
    """
    try:
        from campaign_management.models import Campaign, CampaignAssignment
        from admin_dashboard.models import FieldRepCampaign
    except Exception as e:
        _dbg(request, "PORTAL sync import failed", err=str(e))
        return False

    campaign_obj = Campaign.objects.filter(brand_campaign_id=brand_campaign_id).first()
    if not campaign_obj:
        campaign_obj = Campaign.objects.filter(id=brand_campaign_id).first()

    if not campaign_obj:
        _dbg(request, "PORTAL campaign not found", brand_campaign_id=brand_campaign_id)
        return False

    ca, ca_created = CampaignAssignment.objects.get_or_create(
        campaign=campaign_obj,
        field_rep=portal_user,
        defaults={"assigned_by": None},
    )
    frc, frc_created = FieldRepCampaign.objects.get_or_create(
        campaign=campaign_obj,
        field_rep=portal_user,
    )
    _dbg(request, "PORTAL assignment ensured",
         campaign_pk=campaign_obj.pk,
         portal_user_id=portal_user.id,
         ca_created=ca_created,
         frc_created=frc_created)
    return True

def _smdbg(request, msg: str, **kwargs):
    """
    Debug printer for sharing_management.
    DO NOT log passwords.
    """
    if not SM_VERBOSE_LOGS:
        return
    safe = {}
    for k, v in kwargs.items():
        lk = str(k).lower()
        if "password" in lk or "token" in lk or "secret" in lk:
            safe[k] = "***"
        else:
            safe[k] = v

    prefix = f"[SMDBG] {timezone.now().isoformat(timespec='seconds')}"
    if request is not None:
        prefix += f" path={getattr(request, 'path', '')} method={getattr(request, 'method', '')}"
    line = f"{prefix} :: {msg} :: {safe}"
    try:
        print(line)
    except Exception:
        pass
    try:
        logger.info(line)
    except Exception:
        pass


def _master_db_alias() -> str:
    """
    Best-effort master DB alias discovery.
    Prefer settings.MASTER_DB_ALIAS; fallback to common names.
    """
    alias = getattr(settings, "MASTER_DB_ALIAS", None)
    if alias:
        return alias
    for cand in ("master", "master_db", "MASTER"):
        if cand in getattr(settings, "DATABASES", {}):
            return cand
    # fallback: keep 'master' so it fails loudly if not configured
    return "master"


def _normalize_master_campaign_id(campaign_id: str) -> str:
    """
    MasterCampaign.id is stored dashless (32 hex) per your master_models.py.
    Incoming URLs often pass UUID with hyphens.
    """
    s = (campaign_id or "").strip().lower()
    return s.replace("-", "")


def _looks_like_uuid(val: str) -> bool:
    s = (val or "").strip()
    return bool(re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", s))


def _debug_master_fieldrep_lookup(request, field_id: str, gmail_id: str):
    """
    Returns: (rep or None, debug_dict)
    """
    debug = {}
    alias = _master_db_alias()
    debug["master_alias"] = alias

    try:
        from campaign_management.master_models import MasterFieldRep
    except Exception as e:
        _smdbg(request, "IMPORT_FAIL MasterFieldRep", error=str(e), alias=alias)
        return None, {"error": f"Import MasterFieldRep failed: {e}", **debug}

    fid = (field_id or "").strip()
    email = (gmail_id or "").strip().lower()

    _smdbg(request, "MASTER_LOOKUP begin", alias=alias, field_id=fid, gmail_id=email)

    try:
        base = MasterFieldRep.objects.using(alias).select_related("user").all()

        # Strict match (recommended)
        strict_qs = base.filter(
            is_active=True,
            brand_supplied_field_rep_id=fid,
            user__email__iexact=email,
        )
        debug["strict_count"] = strict_qs.count()
        rep = strict_qs.first()
        if rep:
            debug["match_type"] = "strict(field_id+email)"
            debug["master_fieldrep_id"] = getattr(rep, "id", None)
            debug["master_auth_user_id"] = getattr(rep, "user_id", None)
            debug["master_rep_email"] = getattr(getattr(rep, "user", None), "email", None)
            debug["master_rep_field_id"] = getattr(rep, "brand_supplied_field_rep_id", None)
            _smdbg(request, "MASTER_LOOKUP strict matched", **debug)
            return rep, debug

        # Diagnostics: email-only and field-only counts
        email_qs = base.filter(is_active=True, user__email__iexact=email)
        field_qs = base.filter(is_active=True, brand_supplied_field_rep_id=fid)

        debug["email_only_count"] = email_qs.count()
        debug["field_only_count"] = field_qs.count()

        sample_email = list(email_qs.values_list("id", "brand_supplied_field_rep_id")[:5])
        sample_field = list(field_qs.values_list("id", "user__email")[:5])
        debug["email_only_sample(id,field_id)"] = sample_email
        debug["field_only_sample(id,email)"] = sample_field

        _smdbg(request, "MASTER_LOOKUP strict NOT matched", **debug)
        return None, debug

    except Exception as e:
        _smdbg(request, "MASTER_LOOKUP exception", error=str(e), alias=alias)
        return None, {"error": str(e), **debug}


def _debug_master_campaign_assignment(request, master_fieldrep_id: int, campaign_param: str):
    """
    Returns: (is_assigned: bool, resolved_campaign_id_used: str|None, debug_dict)
    """
    debug = {}
    alias = _master_db_alias()
    debug["master_alias"] = alias
    raw = (campaign_param or "").strip()
    norm = _normalize_master_campaign_id(raw)

    debug["campaign_raw"] = raw
    debug["campaign_norm"] = norm
    debug["campaign_raw_looks_like_uuid"] = _looks_like_uuid(raw)

    try:
        from campaign_management.master_models import MasterCampaign, MasterCampaignFieldRep
    except Exception as e:
        _smdbg(request, "IMPORT_FAIL MasterCampaign/MasterCampaignFieldRep", error=str(e), alias=alias)
        return False, None, {"error": f"Import master models failed: {e}", **debug}

    try:
        # Check campaign existence (raw + normalized)
        exists_raw = MasterCampaign.objects.using(alias).filter(id=raw).exists() if raw else False
        exists_norm = MasterCampaign.objects.using(alias).filter(id=norm).exists() if norm else False
        debug["master_campaign_exists_raw"] = exists_raw
        debug["master_campaign_exists_norm"] = exists_norm

        # Assignment check using both candidate IDs
        candidates = []
        if raw:
            candidates.append(raw)
        if norm and norm != raw:
            candidates.append(norm)

        for cid in candidates:
            cnt = MasterCampaignFieldRep.objects.using(alias).filter(
                campaign_id=cid,
                field_rep_id=master_fieldrep_id,
            ).count()
            _smdbg(
                request,
                "MASTER_ASSIGNMENT check",
                field_rep_id=master_fieldrep_id,
                campaign_id=cid,
                link_count=cnt,
            )
            if cnt > 0:
                debug["assigned_using_campaign_id"] = cid
                return True, cid, debug

        # Extra diagnostic: list first few campaign_ids for the rep
        rep_campaigns = list(
            MasterCampaignFieldRep.objects.using(alias)
            .filter(field_rep_id=master_fieldrep_id)
            .values_list("campaign_id", flat=True)[:10]
        )
        debug["rep_campaign_ids_sample"] = rep_campaigns
        _smdbg(request, "MASTER_ASSIGNMENT not found", **debug)
        return False, None, debug

    except Exception as e:
        _smdbg(request, "MASTER_ASSIGNMENT exception", error=str(e), alias=alias, field_rep_id=master_fieldrep_id)
        return False, None, {"error": str(e), **debug}



# -----------------------------------------------------------------------------
# DB helpers
# -----------------------------------------------------------------------------

def _split_full_name(full_name: str) -> tuple[str, str]:
    full_name = (full_name or "").strip()
    if not full_name:
        return "", ""
    parts = [p for p in full_name.split() if p.strip()]
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _normalize_phone_e164(raw_phone: str, default_country_code: str = "91") -> str:
    digits = re.sub(r"\D", "", (raw_phone or ""))
    if SM_VERBOSE_LOGS:
        print(f"[SMDBG] _normalize_phone_e164 raw={raw_phone!r} digits={digits!r}")

    if not digits:
        return ""

    if digits.startswith("00"):
        digits = digits[2:]

    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if len(digits) == 10 and default_country_code:
        digits = f"{default_country_code}{digits}"

    if len(digits) < 8 or len(digits) > 15:
        return ""

    return f"+{digits}"



def _send_email(to_addr: str, subject: str, body: str) -> None:
    send_mail(
        subject=subject,
        message=body,
        from_email=getattr(settings, "EMAIL_HOST_USER", None),
        recipient_list=[to_addr],
        fail_silently=False,
    )


# -----------------------------------------------------------------------------
# Master DB lookup + sync to portal (default DB)
# -----------------------------------------------------------------------------
def _master_get_fieldrep_by_email(email: str) -> MasterFieldRep | None:
    email = (email or "").strip()
    if not email:
        return None
    return (
        MasterFieldRep.objects.using(_master_db_alias())
        .select_related("user", "brand")
        .filter(user__email__iexact=email, is_active=True)
        .first()
    )


def _master_get_fieldrep_by_field_id_and_email(field_id: str, email: str) -> MasterFieldRep | None:
    field_id = (field_id or "").strip()
    email = (email or "").strip()
    if not field_id or not email:
        return None
    return (
        MasterFieldRep.objects.using(_master_db_alias())
        .select_related("user", "brand")
        .filter(brand_supplied_field_rep_id=field_id, user__email__iexact=email, is_active=True)
        .first()
    )


def _master_get_campaign_ids_for_fieldrep(master_field_rep_id: int) -> list[str]:
    """
    Returns master campaign ids (32-char strings) assigned to the rep.
    These should match default DB Campaign.brand_campaign_id values.
    """
    if not master_field_rep_id:
        return []
    qs = (
        MasterCampaignFieldRep.objects.using(_master_db_alias())
        .filter(field_rep_id=master_field_rep_id)
        .values_list("campaign_id", flat=True)
    )
    return [str(x) for x in qs if x]


def _safe_set(obj, attr: str, value) -> bool:
    """
    Set obj.attr=value only if attr exists and value is truthy/non-empty.
    Returns True if a change was made.
    """
    if not hasattr(obj, attr):
        return False
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    current = getattr(obj, attr, None)
    if current == value:
        return False
    setattr(obj, attr, value)
    return True


def _ensure_portal_user_for_master_fieldrep(master_rep: MasterFieldRep, raw_password: str = ""):
    """
    Best-effort mirror user in DEFAULT DB (user_management.User) so:
      - ShortLink.created_by has a valid user
      - Doctor.rep can point to a user
      - any existing portal features expecting a User record continue to work

    This function is tolerant to field name differences in your custom user model.
    """
    try:
        from user_management.models import User as PortalUser  # your custom portal user

        email = (getattr(master_rep.user, "email", "") or "").lower().strip()
        field_id = (getattr(master_rep, "brand_supplied_field_rep_id", "") or "").strip()
        full_name = (getattr(master_rep, "full_name", "") or "").strip()
        first_name, last_name = _split_full_name(full_name)

        # Find existing
        user = None
        if field_id and hasattr(PortalUser, "field_id"):
            user = PortalUser.objects.filter(field_id=field_id).first()
        if not user and email:
            user = PortalUser.objects.filter(email__iexact=email).first()

        # Create if missing
        if not user:
            base_username = (email.split("@")[0] if email else f"fieldrep_{field_id or master_rep.id}")[:140]
            username = base_username or f"fieldrep_{master_rep.id}"
            suffix = 0
            while PortalUser.objects.filter(username=username).exists():
                suffix += 1
                username = f"{base_username}_{suffix}"[:150]

            # Try create_user if exists
            if hasattr(PortalUser.objects, "create_user"):
                user = PortalUser.objects.create_user(
                    username=username,
                    email=email or "",
                    password=raw_password or PortalUser.objects.make_random_password(),
                )
            else:
                user = PortalUser.objects.create(
                    username=username,
                    email=email or "",
                    password=make_password(raw_password or PortalUser.objects.make_random_password()),
                )

        changed = False
        changed |= _safe_set(user, "email", email)
        changed |= _safe_set(user, "first_name", first_name)
        changed |= _safe_set(user, "last_name", last_name)

        # Common custom fields in your project
        changed |= _safe_set(user, "role", "field_rep")
        changed |= _safe_set(user, "field_id", field_id)

        # Some code uses active=True, some uses is_active=True → try both if present
        if hasattr(user, "active"):
            if user.active is not True:
                user.active = True
                changed = True
        if hasattr(user, "is_active"):
            if user.is_active is not True:
                user.is_active = True
                changed = True

        if raw_password and hasattr(user, "set_password"):
            user.set_password(raw_password)
            changed = True

        if changed:
            user.save()

        # Optional: sync campaign assignment tables (best-effort)
        try:
            from campaign_management.models import Campaign, CampaignAssignment
            from admin_dashboard.models import FieldRepCampaign

            campaign_ids = _master_get_campaign_ids_for_fieldrep(int(master_rep.id))
            for bc_id in campaign_ids:
                c = Campaign.objects.filter(brand_campaign_id=bc_id).first()
                if not c:
                    continue
                CampaignAssignment.objects.get_or_create(
                    campaign=c,
                    field_rep=user,
                    defaults={"assigned_by": None},
                )
                FieldRepCampaign.objects.get_or_create(campaign=c, field_rep=user)
        except Exception:
            # do not hard-fail
            pass

        return user
    except Exception:
        return None


def find_or_create_short_link(collateral, user):
    from django.utils import timezone
    from shortlink_management.models import ShortLink
    from shortlink_management.utils import generate_short_code

    try:
        existing = ShortLink.objects.filter(
            resource_type="collateral",
            resource_id=getattr(collateral, "id", None),
            is_active=True,
        ).first()
        if existing:
            # minimal debug (no request object here)
            if SM_VERBOSE_LOGS:
                print(f"[SMDBG] find_or_create_short_link existing short_code={existing.short_code} resource_id={existing.resource_id}")
            return existing

        short_code = generate_short_code(length=8)
        obj = ShortLink.objects.create(
            short_code=short_code,
            resource_type="collateral",
            resource_id=getattr(collateral, "id", None),
            created_by=user,
            date_created=timezone.now(),
            is_active=True,
        )
        if SM_VERBOSE_LOGS:
            print(f"[SMDBG] find_or_create_short_link created short_code={obj.short_code} resource_id={obj.resource_id}")
        return obj
    except Exception as e:
        if SM_VERBOSE_LOGS:
            print(f"[SMDBG] find_or_create_short_link ERROR: {e}")
        raise



def get_brand_specific_message(collateral_id, collateral_name, collateral_link, brand_campaign_id=None):
    from collateral_management.models import CollateralMessage
    from campaign_management.models import CampaignCollateral as CampaignMgmtCampaignCollateral

    bc_id = (str(brand_campaign_id).strip() if brand_campaign_id else "")
    if SM_VERBOSE_LOGS:
        print(f"[SMDBG] get_brand_specific_message bc_id={bc_id!r} collateral_id={collateral_id!r}")

    try:
        if bc_id:
            custom_message = (
                CollateralMessage.objects.filter(
                    campaign__brand_campaign_id=bc_id,
                    collateral_id=collateral_id,
                    is_active=True,
                )
                .order_by("-id")
                .first()
            )
            if custom_message and custom_message.message:
                return custom_message.message.replace("$collateralLinks", collateral_link)
    except Exception as e:
        if SM_VERBOSE_LOGS:
            print(f"[SMDBG] get_brand_specific_message brand-specific lookup ERROR: {e}")

    # Legacy fallback
    try:
        campaign_collateral = (
            CampaignMgmtCampaignCollateral.objects.select_related("campaign")
            .filter(collateral_id=collateral_id)
            .order_by("-id")
            .first()
        )
        if campaign_collateral and getattr(campaign_collateral, "campaign", None):
            custom_message = (
                CollateralMessage.objects.filter(
                    campaign=campaign_collateral.campaign,
                    collateral_id=collateral_id,
                    is_active=True,
                )
                .order_by("-id")
                .first()
            )
            if custom_message and custom_message.message:
                return custom_message.message.replace("$collateralLinks", collateral_link)
    except Exception as e:
        if SM_VERBOSE_LOGS:
            print(f"[SMDBG] get_brand_specific_message legacy fallback ERROR: {e}")

    return (
        "Hello Doctor, please check this: "
        f"{collateral_link}"
    )



def _clear_google_session_keys(request: HttpRequest) -> None:
    google_session_keys = [
        "_auth_user_id",
        "_auth_user_backend",
        "_auth_user_hash",
        "user_id",
        "username",
        "email",
        "first_name",
        "last_name",
    ]
    for key in google_session_keys:
        request.session.pop(key, None)


# -----------------------------------------------------------------------------
# Tracking endpoint (kept)
# -----------------------------------------------------------------------------
@csrf_exempt
def doctor_view_log(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    event = str(data.get("event") or "").strip()
    value = data.get("value")

    engagement_id_raw = data.get("engagement_id")
    share_id = data.get("share_id") or request.session.get("share_id")

    if not engagement_id_raw or not event:
        return JsonResponse({"ok": False, "error": "engagement_id and event are required"}, status=400)

    try:
        engagement_id = int(engagement_id_raw)
    except Exception:
        return JsonResponse({"ok": False, "error": "engagement_id must be int"}, status=400)

    engagement = DoctorEngagement.objects.filter(id=engagement_id).select_related("short_link").first()
    if not engagement:
        return JsonResponse({"ok": False, "error": "DoctorEngagement not found"}, status=404)

    now = timezone.now()

    if event == "pdf_download":
        engagement.pdf_completed = True

    elif event == "page_scroll":
        try:
            page_number = int(data.get("page_number") or 1)
        except Exception:
            page_number = 1
        if page_number < 1:
            page_number = 1
        engagement.last_page_scrolled = max(int(engagement.last_page_scrolled or 1), page_number)

    elif event == "video_progress":
        try:
            pct = int(value)
        except Exception:
            pct = 0
        pct = max(0, min(100, pct))
        engagement.video_watch_percentage = max(int(engagement.video_watch_percentage or 0), pct)

    engagement.updated_at = now
    engagement.save(
        update_fields=[
            "last_page_scrolled",
            "pdf_completed",
            "video_watch_percentage",
            "status",
            "updated_at",
        ]
    )

    if share_id:
        try:
            sl = ShareLog.objects.get(id=share_id)
            mark_viewed(sl, sm_engagement_id=None)

            pdf_total_pages = 0
            try:
                pdf_total_pages = int(data.get("pdf_total_pages") or 0)
            except Exception:
                pdf_total_pages = 0

            mark_pdf_progress(
                sl,
                last_page=int(engagement.last_page_scrolled or 1),
                completed=bool(engagement.pdf_completed),
                dv_engagement_id=engagement.id,
                total_pages=pdf_total_pages,
                sm_engagement_id=None,
            )

            if engagement.pdf_completed:
                mark_downloaded_pdf(sl)

            if event == "video_progress":
                pct = int(engagement.video_watch_percentage or 0)
                mark_video_event(
                    sl,
                    status=pct,
                    percentage=pct,
                    event_id=0,
                    when=timezone.now(),
                )
        except ShareLog.DoesNotExist:
            pass
        except Exception as e:
            print("[doctor_view_log] error updating ShareLog/CollateralTransaction:", str(e))
            return JsonResponse({"ok": False, "error": "Failed to update transaction"}, status=500)

    return JsonResponse({"ok": True, "event": event})


# -----------------------------------------------------------------------------
# Core sharing (authenticated portal user) (kept)
# -----------------------------------------------------------------------------
def _resolve_master_fieldrep_id_from_portal_user(user) -> int | None:
    """
    Attempt to map portal user -> master field rep id (via email, then field_id).
    """
    try:
        email = (getattr(user, "email", "") or "").strip()
        field_id = (getattr(user, "field_id", "") or "").strip()

        rep = _master_get_fieldrep_by_email(email) if email else None
        if not rep and field_id and email:
            rep = _master_get_fieldrep_by_field_id_and_email(field_id, email)
        if rep:
            return int(rep.id)
    except Exception:
        pass
    return None


@field_rep_required
@recaptcha_required
def share_content(request):
    collateral_id = request.GET.get("collateral_id")
    initial = {}
    if collateral_id:
        initial["collateral"] = collateral_id

    brand_campaign_id = request.POST.get("brand_campaign_id") or request.GET.get("brand_campaign_id")

    # Auto-detect brand_campaign_id from collateral if not provided
    if not brand_campaign_id and collateral_id:
        try:
            cc = (
                CMCampaignCollateral.objects.filter(collateral_id=collateral_id)
                .select_related("campaign")
                .first()
            )
            if cc and cc.campaign:
                brand_campaign_id = cc.campaign.brand_campaign_id
        except Exception:
            pass

    if request.method == "POST":
        form = ShareForm(request.POST, user=request.user, brand_campaign_id=brand_campaign_id)
        if form.is_valid():
            collateral = form.cleaned_data["collateral"]
            if hasattr(collateral, "is_active") and not collateral.is_active:
                messages.error(request, "Selected collateral is inactive and cannot be shared.")
                return redirect("share_content")

            doctor_contact = form.cleaned_data["doctor_contact"].strip()
            share_channel = form.cleaned_data["share_channel"]
            message_text = form.cleaned_data["message_text"]

            short_link = find_or_create_short_link(collateral, request.user)
            short_url = request.build_absolute_uri(f"/shortlinks/go/{short_link.short_code}/")

            default_msg = f"Hello Doctor, please check this: {short_url}"
            full_msg = message_text.replace("$collateralLinks", short_url).strip() or default_msg

            try:
                if share_channel == "WhatsApp":
                    pass
                elif share_channel == "Email":
                    _send_email(
                        to_addr=doctor_contact,
                        subject="New material from your field-rep",
                        body=full_msg,
                    )
                else:
                    messages.error(request, "Unknown share channel")
                    return redirect("share_content")
            except Exception as exc:
                messages.error(request, f"Could not send: {exc}")
                return redirect("share_content")

            master_fieldrep_id = _resolve_master_fieldrep_id_from_portal_user(request.user)

            share_log = ShareLog.objects.create(
                short_link=short_link,
                collateral=collateral,
                field_rep_id=master_fieldrep_id,
                field_rep_email=(getattr(request.user, "email", "") or ""),
                doctor_identifier=doctor_contact,
                share_channel=share_channel,
                share_timestamp=timezone.now(),
                message_text=message_text,
                brand_campaign_id=str(brand_campaign_id or ""),
            )

            try:
                upsert_from_sharelog(
                    share_log,
                    brand_campaign_id=str(brand_campaign_id or ""),
                    doctor_name=None,
                    field_rep_unique_id=getattr(request.user, "employee_code", None)
                    or getattr(request.user, "field_id", None),
                    sent_at=share_log.share_timestamp,
                )
            except Exception:
                pass

            return redirect("share_success", share_log_id=share_log.id)
    else:
        form = ShareForm(user=request.user, initial=initial, brand_campaign_id=brand_campaign_id)
        if collateral_id:
            form.fields["collateral"].widget.attrs["hidden"] = True

    return render(request, "sharing_management/share_form.html", {"form": form})


@field_rep_required
def share_success(request, share_log_id):
    share_log = get_object_or_404(ShareLog, id=share_log_id)
    # If you want to restrict access to only the same field-rep, you can compare master ids:
    # master_id = _resolve_master_fieldrep_id_from_portal_user(request.user)
    # if master_id and share_log.field_rep_id and share_log.field_rep_id != master_id: ...

    wa_link = ""
    if share_log.share_channel == "WhatsApp":
        short_url = request.build_absolute_uri(f"/shortlinks/go/{share_log.short_link.short_code}/")
        msg_text = (
            share_log.message_text.replace("$collateralLinks", short_url)
            if share_log.message_text
            else f"Hello Doctor, please check this: {short_url}"
        )
        wa_link = f"https://wa.me/{share_log.doctor_identifier}?text={quote(msg_text)}"

    return render(request, "sharing_management/share_success.html", {"share_log": share_log, "wa_link": wa_link})


@field_rep_required
def list_share_logs(request):
    master_id = _resolve_master_fieldrep_id_from_portal_user(request.user)
    qs = ShareLog.objects.all().order_by("-share_timestamp")
    if master_id:
        qs = qs.filter(field_rep_id=master_id)

    paginator = Paginator(qs, 10)
    page_number = request.GET.get("page")
    logs = paginator.get_page(page_number)
    return render(request, "sharing_management/share_logs.html", {"logs": logs})


# -----------------------------------------------------------------------------
# Field Rep Registration (MASTER DB)
# -----------------------------------------------------------------------------
def fieldrep_email_registration(request):
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        brand_campaign_id = (request.POST.get("brand_campaign_id") or request.GET.get("campaign") or "").strip()
        redirect_url = f"/share/fieldrep-create-password/?email={urllib.parse.quote(email)}"
        if brand_campaign_id:
            redirect_url += f"&campaign={urllib.parse.quote(brand_campaign_id)}"
        return redirect(redirect_url)

    brand_campaign_id = request.GET.get("campaign")
    return render(request, "sharing_management/fieldrep_email_registration.html", {"brand_campaign_id": brand_campaign_id})


def _master_upsert_auth_user(*, email: str, first_name: str = "", last_name: str = "", raw_password: str = "") -> MasterAuthUser:
    """
    Create or update MasterAuthUser (auth_user in master DB).
    """
    db = _master_db_alias()
    email_norm = (email or "").strip().lower()
    if not email_norm:
        raise ValueError("Email required")

    # Try find by username (common pattern) then email
    user = (
        MasterAuthUser.objects.using(db)
        .filter(Q(username=email_norm) | Q(email__iexact=email_norm))
        .order_by("id")
        .first()
    )

    if not user:
        # Create unique username (max 150)
        base_username = email_norm[:150]
        username = base_username
        suffix = 0
        while MasterAuthUser.objects.using(db).filter(username=username).exists():
            suffix += 1
            username = f"{base_username[: (150 - (len(str(suffix)) + 1))]}_{suffix}"

        user = MasterAuthUser.objects.using(db).create(
            username=username,
            email=email_norm,
            first_name=(first_name or "")[:150],
            last_name=(last_name or "")[:150],
            password=make_password(raw_password or MasterAuthUser.password.field.default if hasattr(MasterAuthUser, "password") else ""),
            is_active=True,
            is_staff=False,
            is_superuser=False,
            date_joined=timezone.now(),
        )
    else:
        changed = False
        if first_name:
            changed |= _safe_set(user, "first_name", first_name[:150])
        if last_name:
            changed |= _safe_set(user, "last_name", last_name[:150])
        if email_norm:
            changed |= _safe_set(user, "email", email_norm)
        if raw_password:
            user.password = make_password(raw_password)
            changed = True
        if changed:
            user.save(using=db)

    return user


def _master_upsert_fieldrep(
    *,
    master_user: MasterAuthUser,
    master_campaign_id: str,
    full_name: str,
    phone_number: str,
    brand_supplied_field_rep_id: str,
    raw_password: str,
) -> MasterFieldRep:
    """
    Create/update MasterFieldRep for the given master auth user.
    """
    db = _master_db_alias()
    master_campaign_id = (master_campaign_id or "").strip()
    if not master_campaign_id:
        raise ValueError("master_campaign_id required")

    campaign = MasterCampaign.objects.using(db).select_related("brand").filter(id=master_campaign_id).first()
    if not campaign:
        raise ValueError(f"Master campaign not found: {master_campaign_id}")

    if not campaign.brand_id:
        raise ValueError("Master campaign brand_id is null; cannot create field rep without brand")

    rep = MasterFieldRep.objects.using(db).select_related("user", "brand").filter(user_id=master_user.id).first()

    if not rep:
        rep = MasterFieldRep.objects.using(db).create(
            user=master_user,
            brand=campaign.brand,
            full_name=(full_name or "").strip() or f"Field Rep {brand_supplied_field_rep_id or master_user.id}",
            phone_number=(phone_number or "").strip(),
            brand_supplied_field_rep_id=(brand_supplied_field_rep_id or "").strip(),
            is_active=True,
            password_hash="",
        )
    else:
        changed = False
        # If brand differs, align to campaign brand
        if rep.brand_id != campaign.brand_id:
            rep.brand = campaign.brand
            changed = True
        changed |= _safe_set(rep, "full_name", (full_name or "").strip())
        changed |= _safe_set(rep, "phone_number", (phone_number or "").strip())
        changed |= _safe_set(rep, "brand_supplied_field_rep_id", (brand_supplied_field_rep_id or "").strip())
        if changed:
            rep.save(using=db)

    # Set password hash in rep table (used by session auth)
    if raw_password:
        rep.password_hash = make_password(raw_password)
        rep.save(using=db)

    # Ensure campaign link
    MasterCampaignFieldRep.objects.using(db).get_or_create(
        campaign_id=master_campaign_id,
        field_rep_id=rep.id,
    )

    return rep


# ===========================
# DROP-IN REPLACEMENT: fieldrep_create_password
# ===========================
def fieldrep_create_password(request):
    email = request.GET.get("email") or request.POST.get("email")
    brand_campaign_id = request.GET.get("campaign") or request.POST.get("campaign")

    _dbg(request, "fieldrep_create_password ENTER", method=request.method, email=email, campaign=brand_campaign_id)

    security_questions = _get_security_questions_safe(request=request)

    if request.method == "POST":
        field_id = (request.POST.get("field_id") or "").strip()
        first_name = (request.POST.get("first_name") or "").strip()
        last_name = (request.POST.get("last_name") or "").strip()
        whatsapp_number = (request.POST.get("whatsapp_number", "") or "").strip()
        password = request.POST.get("password") or ""
        confirm_password = request.POST.get("confirm_password") or ""
        security_question_id = request.POST.get("security_question")
        security_answer = request.POST.get("security_answer")

        _dbg(request, "fieldrep_create_password POST",
             field_id=field_id, whatsapp_number=whatsapp_number,
             security_question_id=security_question_id,
             campaign=brand_campaign_id)

        if whatsapp_number and (not whatsapp_number.isdigit() or len(whatsapp_number) < 10 or len(whatsapp_number) > 15):
            return render(request, "sharing_management/fieldrep_create_password.html", {
                "email": email,
                "security_questions": security_questions,
                "brand_campaign_id": brand_campaign_id,
                "error": "Please enter a valid WhatsApp number (10-15 digits).",
            })

        if password != confirm_password:
            return render(request, "sharing_management/fieldrep_create_password.html", {
                "email": email,
                "security_questions": security_questions,
                "brand_campaign_id": brand_campaign_id,
                "error": "Passwords do not match.",
            })

        # Keep your existing registration (default DB) behavior
        try:
            success = register_field_representative(
                field_id=field_id,
                email=email,
                whatsapp_number=whatsapp_number,
                password=password,
                security_question_id=security_question_id,
                security_answer=security_answer,
            )
            _dbg(request, "register_field_representative result", success=success)
        except Exception as e:
            _dbg(request, "register_field_representative EXCEPTION", err=str(e))
            success = False

        if not success:
            return render(request, "sharing_management/fieldrep_create_password.html", {
                "email": email,
                "security_questions": security_questions,
                "brand_campaign_id": brand_campaign_id,
                "error": "Registration failed. Please try again.",
            })

        # BEST-EFFORT: also ensure portal user exists (needed later)
        try:
            _ensure_portal_fieldrep_user(email=email, field_id=field_id, request=request)
        except Exception as e:
            _dbg(request, "PORTAL user ensure failed", err=str(e))

        # BEST-EFFORT: sync portal assignment
        if brand_campaign_id:
            try:
                portal_user = _ensure_portal_fieldrep_user(email=email, field_id=field_id, request=request)
                _portal_sync_assignment(portal_user, brand_campaign_id, request=request)
            except Exception as e:
                _dbg(request, "PORTAL assignment sync failed", err=str(e))

        # Redirect to login
        redirect_url = "/share/fieldrep-login/"
        if brand_campaign_id:
            redirect_url += f"?campaign={brand_campaign_id}"
        _dbg(request, "fieldrep_create_password SUCCESS redirect", redirect_url=redirect_url)
        return redirect(redirect_url)

    return render(request, "sharing_management/fieldrep_create_password.html", {
        "email": email,
        "security_questions": security_questions,
        "brand_campaign_id": brand_campaign_id,
    })


# -----------------------------------------------------------------------------
# Field Rep Login / Forgot / Reset (MASTER DB)
# -----------------------------------------------------------------------------
def fieldrep_login(request):
    brand_campaign_id = (request.GET.get("campaign") or request.POST.get("campaign") or "").strip()

    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        password = request.POST.get("password") or ""

        rep = _master_get_fieldrep_by_email(email)
        if not rep:
            return render(
                request,
                "sharing_management/fieldrep_login.html",
                {"error": "Invalid email or password. Please try again.", "brand_campaign_id": brand_campaign_id},
            )

        ok = False
        try:
            ok = rep.check_password(password)
        except Exception:
            ok = False

        # fallback: master auth_user.password
        if not ok:
            try:
                ok = django_check_password(password, rep.user.password)
            except Exception:
                ok = False

        if not ok:
            return render(
                request,
                "sharing_management/fieldrep_login.html",
                {"error": "Invalid email or password. Please try again.", "brand_campaign_id": brand_campaign_id},
            )

        _clear_google_session_keys(request)

        request.session["field_rep_id"] = int(rep.id)  # MASTER fieldrep id
        request.session["field_rep_email"] = (rep.user.email or "").strip()
        request.session["field_rep_field_id"] = (rep.brand_supplied_field_rep_id or "").strip()
        if brand_campaign_id:
            request.session["brand_campaign_id"] = brand_campaign_id

        # sync portal user + assignments best effort
        _ensure_portal_user_for_master_fieldrep(rep)

        if brand_campaign_id:
            return redirect(f"/share/fieldrep-share-collateral/{brand_campaign_id}/")
        return redirect("fieldrep_share_collateral")

    return render(request, "sharing_management/fieldrep_login.html", {"brand_campaign_id": brand_campaign_id})


def fieldrep_forgot_password(request):
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        security_answer = (request.POST.get("security_answer") or "").strip()
        security_question_id = request.POST.get("security_question_id")

        rep = _master_get_fieldrep_by_email(email)
        if not rep:
            return render(request, "sharing_management/fieldrep_forgot_password.html", {"error": "Email not found."})

        profile = FieldRepSecurityProfile.objects.filter(master_field_rep_id=int(rep.id)).select_related("security_question").first()
        if not profile or not profile.security_question:
            return render(
                request,
                "sharing_management/fieldrep_forgot_password.html",
                {"error": "No security question set for this user. Please contact admin."},
            )

        # Step 1: show question
        if not security_answer:
            return render(
                request,
                "sharing_management/fieldrep_forgot_password.html",
                {
                    "email": email,
                    "security_question": profile.security_question.question_txt,
                    "security_question_id": profile.security_question.id,
                },
            )

        # Step 2: validate
        if str(profile.security_question.id) != str(security_question_id):
            return render(
                request,
                "sharing_management/fieldrep_forgot_password.html",
                {
                    "email": email,
                    "security_question": profile.security_question.question_txt,
                    "security_question_id": profile.security_question.id,
                    "error": "Invalid security question.",
                },
            )

        if profile.check_answer(security_answer):
            return redirect(f"/share/fieldrep-reset-password/?email={urllib.parse.quote(email)}")

        return render(
            request,
            "sharing_management/fieldrep_forgot_password.html",
            {
                "email": email,
                "security_question": profile.security_question.question_txt,
                "security_question_id": profile.security_question.id,
                "error": "Invalid security answer. Please try again.",
            },
        )

    return render(request, "sharing_management/fieldrep_forgot_password.html")


def fieldrep_reset_password(request):
    email = (request.GET.get("email") or request.POST.get("email") or "").strip()

    if request.method == "POST":
        password = request.POST.get("password") or ""
        confirm_password = request.POST.get("confirm_password") or ""

        if password != confirm_password:
            return render(
                request,
                "sharing_management/fieldrep_reset_password.html",
                {"email": email, "error": "Passwords do not match."},
            )

        rep = _master_get_fieldrep_by_email(email)
        if not rep:
            return render(
                request,
                "sharing_management/fieldrep_reset_password.html",
                {"email": email, "error": "Email not found."},
            )

        try:
            db = _master_db_alias()
            rep.password_hash = make_password(password)
            rep.save(using=db)

            rep.user.password = make_password(password)
            rep.user.save(using=db)

            # sync portal user best-effort
            portal_user = _ensure_portal_user_for_master_fieldrep(rep, raw_password=password)
            if portal_user and hasattr(portal_user, "set_password"):
                portal_user.set_password(password)
                portal_user.save()

            messages.success(request, "Password reset successfully! Please login with your new password.")
            return redirect("fieldrep_login")
        except Exception as e:
            return render(
                request,
                "sharing_management/fieldrep_reset_password.html",
                {"email": email, "error": f"Failed to reset password: {e}"},
            )

    return render(request, "sharing_management/fieldrep_reset_password.html", {"email": email})


# -----------------------------------------------------------------------------
# Field Rep Share Collateral (session-based) - DEFAULT DB collaterals
# -----------------------------------------------------------------------------
def fieldrep_share_collateral(request, brand_campaign_id=None):
    master_field_rep_id = request.session.get("field_rep_id")
    field_rep_email = request.session.get("field_rep_email")
    field_rep_field_id = request.session.get("field_rep_field_id")

    if brand_campaign_id is None:
        brand_campaign_id = (
            request.session.get("brand_campaign_id")
            or request.GET.get("campaign")
            or request.GET.get("brand_campaign_id")
        )
        brand_campaign_id = (brand_campaign_id or "").strip()

    if not master_field_rep_id:
        messages.error(request, "Please login first.")
        return redirect("fieldrep_login")

    # Fetch rep from master for validation + sync to portal user
    rep = None
    try:
        rep = (
            MasterFieldRep.objects.using(_master_db_alias())
            .select_related("user", "brand")
            .filter(id=int(master_field_rep_id), is_active=True)
            .first()
        )
    except Exception:
        rep = None

    if not rep:
        messages.error(request, "Field rep not found or inactive. Please login again.")
        return redirect("fieldrep_login")

    portal_user = _ensure_portal_user_for_master_fieldrep(rep)

    # Determine allowed campaign ids for this rep
    allowed_campaign_ids = _master_get_campaign_ids_for_fieldrep(int(rep.id))

    # If a campaign is specified, enforce it belongs to rep
    if brand_campaign_id:
        if brand_campaign_id not in allowed_campaign_ids:
            messages.error(request, "You are not assigned to this campaign.")
            return render(
                request,
                "sharing_management/fieldrep_share_collateral.html",
                {
                    "fieldrep_id": field_rep_field_id or "Unknown",
                    "fieldrep_email": field_rep_email,
                    "collaterals": [],
                    "brand_campaign_id": brand_campaign_id,
                    "doctors": [],
                },
            )
        campaign_ids_to_use = [brand_campaign_id]
    else:
        campaign_ids_to_use = allowed_campaign_ids

    # Collaterals filtered by campaign dates + is_active (DEFAULT DB)
    collaterals_list: list[dict] = []
    try:
        from django.db.models import Q as _Q

        current_date = timezone.now().date()
        if campaign_ids_to_use:
            cc_links = (
                CMCampaignCollateral.objects.filter(campaign__brand_campaign_id__in=campaign_ids_to_use)
                .filter(collateral__is_active=True)
                .filter(
                    _Q(start_date__lte=current_date, end_date__gte=current_date)
                    | _Q(start_date__isnull=True, end_date__isnull=True)
                )
                .select_related("collateral")
            )
            collaterals = [x.collateral for x in cc_links if x.collateral]
        else:
            collaterals = []

        # Deduplicate
        seen = set()
        unique_collaterals = []
        for c in collaterals:
            if c.id in seen:
                continue
            seen.add(c.id)
            unique_collaterals.append(c)

        for collateral in unique_collaterals:
            short_link = find_or_create_short_link(collateral, portal_user or request.user)
            collaterals_list.append(
                {
                    "id": collateral.id,
                    "name": getattr(collateral, "title", getattr(collateral, "name", "Untitled")),
                    "description": getattr(collateral, "description", ""),
                    "link": request.build_absolute_uri(f"/shortlinks/go/{short_link.short_code}/"),
                }
            )
    except Exception as e:
        print(f"[fieldrep_share_collateral] Error fetching collaterals: {e}")
        messages.error(request, "Error loading collaterals. Please try again.")
        collaterals_list = []

    # Doctors assigned to portal_user (DEFAULT DB)
    doctors = []
    try:
        if portal_user:
            doctors = Doctor.objects.filter(rep=portal_user).order_by("name")
    except Exception:
        doctors = []

    if request.method == "POST":
        # AJAX send
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.POST.get("ajax"):
            try:
                doctor_name = (request.POST.get("doctor_name") or "").strip()
                doctor_whatsapp = (request.POST.get("doctor_whatsapp") or "").strip()
                collateral_id = request.POST.get("collateral")

                if not collateral_id:
                    return JsonResponse({"success": False, "message": "Collateral ID is required"})

                if not str(collateral_id).isdigit():
                    return JsonResponse({"success": False, "message": "Invalid collateral ID"})

                collateral_id_int = int(collateral_id)
                selected_collateral = next((c for c in collaterals_list if c["id"] == collateral_id_int), None)
                if not selected_collateral:
                    return JsonResponse({"success": False, "message": "Selected collateral not found"})

                phone_e164 = _normalize_phone_e164(doctor_whatsapp)
                if not phone_e164:
                    return JsonResponse({"success": False, "message": "Please enter a valid WhatsApp number."})

                # Ensure doctor exists
                rep_user = portal_user
                if rep_user:
                    Doctor.objects.update_or_create(
                        rep=rep_user,
                        phone=re.sub(r"\D", "", phone_e164)[-10:],  # store last10
                        defaults={"name": doctor_name or "Doctor", "source": "manual"},
                    )

                # Create ShareLog in DEFAULT DB
                collateral_obj = Collateral.objects.get(id=collateral_id_int, is_active=True)
                short_link = find_or_create_short_link(collateral_obj, rep_user or request.user)

                sl = ShareLog.objects.create(
                    short_link=short_link,
                    collateral=collateral_obj,
                    field_rep_id=int(rep.id),
                    field_rep_email=(rep.user.email or ""),
                    doctor_identifier=phone_e164,
                    share_channel="WhatsApp",
                    share_timestamp=timezone.now(),
                    message_text="",
                    brand_campaign_id=(brand_campaign_id or ""),
                )

                # Upsert transaction best-effort
                try:
                    upsert_from_sharelog(
                        sl,
                        brand_campaign_id=(brand_campaign_id or ""),
                        doctor_name=doctor_name or None,
                        field_rep_unique_id=(rep.brand_supplied_field_rep_id or "") or None,
                        sent_at=sl.share_timestamp,
                    )
                except Exception:
                    pass

                message = get_brand_specific_message(
                    collateral_id_int,
                    selected_collateral["name"],
                    selected_collateral["link"],
                    brand_campaign_id=brand_campaign_id,
                )
                wa_number = re.sub(r"\D", "", phone_e164).lstrip("+")
                wa_url = f"https://wa.me/{wa_number}?text={urllib.parse.quote(message)}"

                return JsonResponse(
                    {
                        "success": True,
                        "message": f"Collateral shared successfully with {doctor_name or 'Doctor'}!",
                        "whatsapp_url": wa_url,
                    }
                )
            except Exception as e:
                return JsonResponse({"success": False, "message": f"Server error: {str(e)}"})

        # Non-AJAX fallback: redirect to WA
        doctor_name = (request.POST.get("doctor_name") or "").strip()
        doctor_whatsapp = (request.POST.get("doctor_whatsapp") or "").strip()
        collateral_id = request.POST.get("collateral") or ""
        if not collateral_id.isdigit():
            messages.error(request, "Please provide all required information.")
            return redirect("fieldrep_share_collateral")

        collateral_id_int = int(collateral_id)
        selected_collateral = next((c for c in collaterals_list if c["id"] == collateral_id_int), None)
        phone_e164 = _normalize_phone_e164(doctor_whatsapp)
        if selected_collateral and phone_e164:
            message = get_brand_specific_message(
                collateral_id_int,
                selected_collateral["name"],
                selected_collateral["link"],
                brand_campaign_id=brand_campaign_id,
            )
            wa_number = re.sub(r"\D", "", phone_e164).lstrip("+")
            wa_url = f"https://wa.me/{wa_number}?text={urllib.parse.quote(message)}"
            return redirect(wa_url)

        messages.error(request, "Please provide all required information.")
        return redirect("fieldrep_share_collateral")

    return render(
        request,
        "sharing_management/fieldrep_share_collateral.html",
        {
            "fieldrep_id": field_rep_field_id or "Unknown",
            "fieldrep_email": field_rep_email,
            "collaterals": collaterals_list,
            "brand_campaign_id": brand_campaign_id,
            "doctors": doctors,
        },
    )

# ===========================
# DROP-IN REPLACEMENT: fieldrep_gmail_login
# ===========================
def fieldrep_gmail_login(request):
    brand_campaign_id = request.GET.get("brand_campaign_id") or request.GET.get("campaign")

    _dbg(request, "fieldrep_gmail_login ENTER", method=request.method, campaign=brand_campaign_id, get_params=dict(request.GET))

    if request.method == "POST":
        if "register" in request.POST:
            messages.error(request, "Registration is not allowed from this login link. Please use the registration link.")
            return render(request, "sharing_management/fieldrep_gmail_login.html", {"brand_campaign_id": brand_campaign_id})

        field_id = (request.POST.get("field_id") or "").strip()
        gmail_id = (request.POST.get("gmail_id") or "").strip()
        brand_campaign_id = (request.POST.get("brand_campaign_id") or brand_campaign_id)

        _dbg(request, "fieldrep_gmail_login POST", field_id=field_id, gmail_id=gmail_id, campaign=brand_campaign_id)

        if not field_id or not gmail_id:
            messages.error(request, "Please provide both Field ID and Gmail ID.")
            return render(request, "sharing_management/fieldrep_gmail_login.html", {"brand_campaign_id": brand_campaign_id})

        # 1) Resolve rep from MASTER DB first (preferred)
        master_rep = None
        try:
            master_rep = _master_get_fieldrep(field_id=field_id, gmail_id=gmail_id, request=request)
        except Exception as e:
            _dbg(request, "MASTER lookup exception", err=str(e))
            master_rep = None

        # 2) If campaign provided, check assignment in MASTER DB (handles hyphen vs dashless)
        if brand_campaign_id and master_rep:
            assigned = _master_is_assigned(master_rep, brand_campaign_id, request=request)
            if not assigned:
                messages.error(request, "You are not assigned to this campaign.")
                _dbg(request, "BLOCKED: master assignment missing", master_fieldrep_id=master_rep.pk, campaign=brand_campaign_id)
                return render(request, "sharing_management/fieldrep_gmail_login.html", {"brand_campaign_id": brand_campaign_id})

        # 3) Ensure portal user exists (needed for shortlinks & other portal models)
        portal_user = _ensure_portal_fieldrep_user(email=gmail_id, field_id=field_id, request=request)

        # 4) Best-effort: sync portal assignment tables too (if portal Campaign exists)
        if brand_campaign_id:
            _portal_sync_assignment(portal_user, brand_campaign_id, request=request)

        # 5) Clear google/auth keys (kept behavior)
        google_session_keys = [
            "_auth_user_id", "_auth_user_backend", "_auth_user_hash",
            "user_id", "username", "email", "first_name", "last_name",
        ]
        for key in google_session_keys:
            request.session.pop(key, None)

        # 6) Session values (keep same keys your other views use)
        request.session["field_rep_id"] = str(getattr(master_rep, "user_id", "")) or str(portal_user.id)
        request.session["field_rep_email"] = gmail_id
        request.session["field_rep_field_id"] = field_id

        # helpful extra debug session keys
        request.session["master_fieldrep_id"] = str(getattr(master_rep, "pk", "")) if master_rep else ""
        request.session["brand_campaign_id"] = brand_campaign_id or ""

        _dbg(request, "LOGIN SUCCESS",
             portal_user_id=portal_user.id,
             session_field_rep_id=request.session.get("field_rep_id"),
             session_master_fieldrep_id=request.session.get("master_fieldrep_id"),
             campaign=brand_campaign_id)

        messages.success(request, f"Welcome back, {field_id}!")

        if brand_campaign_id:
            return redirect(f"/share/fieldrep-gmail-share-collateral/?brand_campaign_id={brand_campaign_id}")
        return redirect("fieldrep_gmail_share_collateral")

    return render(request, "sharing_management/fieldrep_gmail_login.html", {"brand_campaign_id": brand_campaign_id})


# ===========================
# DROP-IN REPLACEMENT: fieldrep_gmail_share_collateral (adds assignment debug)
# ===========================
def fieldrep_gmail_share_collateral(request, brand_campaign_id=None):
    """
    Field Rep "Gmail share" page.
    Despite the name, it ultimately prepares a WhatsApp message link.

    This version adds robust debugging + supports:
      - doctor_id (select existing doctor)
      - manual doctor entry (doctor_name + doctor_whatsapp)
      - collateral id coming from POST OR GET (?collateral=71)
      - AJAX/JSON submissions returning JsonResponse
    """
    import urllib.parse as _up
    import json as _json
    import re as _re
    from datetime import timedelta

    from django.contrib import messages
    from django.http import JsonResponse
    from django.shortcuts import redirect, render
    from django.utils import timezone

    # --- Session context ---
    field_rep_id = request.session.get("field_rep_id")
    field_rep_email = request.session.get("field_rep_email")
    field_rep_field_id = request.session.get("field_rep_field_id")

    if brand_campaign_id is None:
        brand_campaign_id = (
            request.GET.get("brand_campaign_id")
            or request.GET.get("campaign")
            or request.session.get("brand_campaign_id")
        )

    print(
        "fieldrep_gmail_share_collateral START "
        f"method={request.method} path={request.path} "
        f"GET={dict(request.GET)} "
        f"session(field_rep_id={field_rep_id}, field_rep_email={field_rep_email}, field_rep_field_id={field_rep_field_id}) "
        f"content_type={request.META.get('CONTENT_TYPE')} xrw={request.headers.get('x-requested-with')}"
    )

    if not field_rep_id:
        _smdbg("No session field_rep_id -> redirect to fieldrep_login")
        messages.error(request, "Please login first.")
        return redirect("fieldrep_login")

    # --- Resolve portal rep user (UMUser) ---
    try:
        from user_management.models import User as UMUser
    except Exception as e:
        _smdbg(f"ERROR importing UMUser: {e}")
        UMUser = None

    actual_user = None
    if UMUser:
        try:
            if field_rep_field_id:
                actual_user = UMUser.objects.filter(field_id=field_rep_field_id, role="field_rep").first()
            if not actual_user and field_rep_email:
                actual_user = UMUser.objects.filter(email__iexact=field_rep_email, role="field_rep").first()
            if not actual_user:
                # last resort: session id might be UMUser id (int)
                try:
                    actual_user = UMUser.objects.get(id=int(field_rep_id))
                except Exception:
                    actual_user = None
        except Exception as e:
            _smdbg(f"ERROR resolving actual_user: {e}")
            actual_user = None

    _smdbg(
        "Resolved actual_user="
        f"{getattr(actual_user, 'id', None)} "
        f"email={getattr(actual_user, 'email', None)} field_id={getattr(actual_user, 'field_id', None)}"
    )

    # --- Build collaterals list (same concept as your existing code) ---
    collaterals_list = []
    try:
        from django.db.models import Q as _Q
        from collateral_management.models import Collateral as CMCollateral, CampaignCollateral as CMCampaignCollateral2
        from campaign_management.models import CampaignCollateral as CampaignMgmtCC

        collaterals = []

        if brand_campaign_id and brand_campaign_id != "all":
            current_date = timezone.now().date()

            # campaign_management CC
            cc_links = CampaignMgmtCC.objects.filter(
                campaign__brand_campaign_id=brand_campaign_id
            ).filter(
                _Q(start_date__lte=current_date, end_date__gte=current_date)
                | _Q(start_date__isnull=True, end_date__isnull=True)
            ).select_related("collateral", "campaign")
            campaign_collaterals = [link.collateral for link in cc_links if getattr(link, "collateral", None)]

            # collateral_management CC
            collateral_links = CMCampaignCollateral2.objects.filter(
                campaign__brand_campaign_id=brand_campaign_id,
                collateral__is_active=True,
            ).filter(
                _Q(start_date__lte=current_date, end_date__gte=current_date)
                | _Q(start_date__isnull=True, end_date__isnull=True)
            ).select_related("collateral", "campaign")
            collateral_collaterals = [
                link.collateral for link in collateral_links
                if getattr(link, "collateral", None) and getattr(link.collateral, "is_active", True)
            ]

            # unique by id
            collaterals = list({c.id: c for c in (campaign_collaterals + collateral_collaterals) if hasattr(c, "id")}.values())
        else:
            collaterals = CMCollateral.objects.filter(is_active=True).order_by("-created_at")

        _smdbg(f"Collaterals fetched count={len(collaterals)} brand_campaign_id={brand_campaign_id}")

        for collateral in collaterals:
            try:
                if not actual_user:
                    continue

                short_link = find_or_create_short_link(collateral, actual_user)
                collaterals_list.append({
                    "id": collateral.id,
                    "name": getattr(collateral, "title", getattr(collateral, "name", "Untitled")),
                    "description": getattr(collateral, "description", ""),
                    "link": request.build_absolute_uri(f"/shortlinks/go/{short_link.short_code}/"),
                })
            except Exception as e:
                _smdbg(f"Collateral list build skip collateral_id={getattr(collateral, 'id', None)} err={e}")
                continue

        _smdbg(f"collaterals_list built count={len(collaterals_list)}")

    except Exception as e:
        _smdbg(f"ERROR fetching collaterals: {e}")
        collaterals_list = []
        messages.error(request, "Error loading collaterals. Please try again.")

    # --- Assigned doctors list (for UI + status) ---
    from doctor_viewer.models import Doctor
    from .models import ShareLog, CollateralTransaction

    assigned_doctors = Doctor.objects.filter(rep=actual_user) if actual_user else Doctor.objects.none()

    # Selected collateral (prefer GET param ?collateral=...)
    selected_collateral_id = (request.GET.get("collateral") or request.POST.get("collateral") or "").strip()
    if not selected_collateral_id and collaterals_list:
        selected_collateral_id = str(collaterals_list[0]["id"])

    # Build doctors status list (best-effort; never break page)
    doctors_with_status = []
    six_days_ago = timezone.now() - timedelta(days=6)

    for doctor in assigned_doctors:
        status = "not_sent"
        try:
            if selected_collateral_id:
                phone_val = doctor.phone or ""
                phone_clean = phone_val.replace("+", "").replace(" ", "").replace("-", "")
                possible_ids = [phone_val]
                if phone_clean and len(phone_clean) == 10:
                    possible_ids.extend([f"+91{phone_clean}", f"91{phone_clean}"])

                # ShareLog may or may not have collateral_id; keep it safe
                qs = ShareLog.objects.filter(doctor_identifier__in=possible_ids).order_by("-share_timestamp")
                try:
                    qs = qs.filter(collateral_id=selected_collateral_id)
                except Exception:
                    # model may not have collateral_id column
                    pass

                share_log = qs.first()

                if share_log:
                    engaged = CollateralTransaction.objects.filter(
                        field_rep_id=str(getattr(share_log, "field_rep_id", "")),
                        doctor_number=getattr(share_log, "doctor_identifier", ""),
                        collateral_id=getattr(share_log, "collateral_id", "") or selected_collateral_id,
                        has_viewed=True,
                    ).exists()
                    if engaged:
                        status = "opened"
                    else:
                        status = "reminder" if share_log.share_timestamp and share_log.share_timestamp < six_days_ago else "sent"
        except Exception as e:
            _smdbg(f"Doctor status calc error doctor_id={doctor.id} err={e}")

        doctors_with_status.append({
            "id": doctor.id,
            "name": doctor.name,
            "phone": doctor.phone,
            "status": status,
        })

    # --- POST handling ---
    if request.method == "POST":
        # Detect AJAX/JSON
        is_ajax = (
            request.headers.get("x-requested-with") == "XMLHttpRequest"
            or (request.META.get("CONTENT_TYPE") or "").startswith("application/json")
            or str(request.POST.get("ajax") or "").lower() in ("1", "true", "yes")
        )

        # Parse payload (form or json)
        payload = request.POST
        if (request.META.get("CONTENT_TYPE") or "").startswith("application/json"):
            try:
                payload = _json.loads((request.body or b"{}").decode("utf-8") or "{}")
            except Exception as e:
                _smdbg(f"ERROR parsing JSON body: {e}")
                payload = {}

        # Pull fields with fallbacks
        def _pget(key: str, default=""):
            try:
                if isinstance(payload, dict):
                    return (payload.get(key) or default)
                return (payload.get(key) or default)
            except Exception:
                return default

        doctor_id_raw = str(_pget("doctor_id") or _pget("doctor") or "").strip()
        doctor_name = str(_pget("doctor_name") or _pget("name") or "").strip()
        doctor_whatsapp = str(
            _pget("doctor_whatsapp")
            or _pget("doctor_phone")
            or _pget("doctor_contact")
            or _pget("whatsapp")
            or _pget("phone")
            or ""
        ).strip()

        collateral_id_str = str(
            _pget("collateral")
            or _pget("collateral_id")
            or request.GET.get("collateral")   # IMPORTANT: accept collateral from query string
            or ""
        ).strip()

        _smdbg(
            "POST received "
            f"is_ajax={is_ajax} "
            f"keys={list(payload.keys()) if hasattr(payload, 'keys') else type(payload)} "
            f"doctor_id={doctor_id_raw} doctor_name={doctor_name} doctor_whatsapp={doctor_whatsapp} "
            f"collateral_id_str={collateral_id_str}"
        )

        # If a doctor was selected by id, resolve it
        if doctor_id_raw and (not doctor_name or not doctor_whatsapp):
            try:
                did = int(doctor_id_raw)
                d = Doctor.objects.filter(id=did).first()
                if d:
                    doctor_name = doctor_name or (d.name or "")
                    doctor_whatsapp = doctor_whatsapp or (d.phone or "")
                    _smdbg(f"Resolved doctor from doctor_id={did} -> name={doctor_name} phone={doctor_whatsapp}")
            except Exception as e:
                _smdbg(f"ERROR resolving doctor_id={doctor_id_raw}: {e}")

        # Validate collateral
        if not collateral_id_str or not str(collateral_id_str).isdigit():
            msg = "Please select a valid collateral (collateral id missing)."
            _smdbg(f"POST validation failed: {msg}")
            if is_ajax:
                return JsonResponse({"success": False, "message": msg}, status=400)
            messages.error(request, msg)
            return redirect(request.get_full_path())

        collateral_id = int(collateral_id_str)

        # Find selected collateral in list (for name/description)
        selected_collateral = next((c for c in collaterals_list if c["id"] == collateral_id), None)
        if not selected_collateral:
            _smdbg(f"Selected collateral not found in collaterals_list for id={collateral_id}. Will try DB lookup.")
            selected_collateral = {"id": collateral_id, "name": "Collateral", "description": "", "link": ""}

        # Validate doctor details
        if not doctor_name or not doctor_whatsapp:
            msg = "Please fill doctor name and WhatsApp number (or select a doctor)."
            _smdbg(f"POST validation failed: {msg}")
            if is_ajax:
                return JsonResponse({"success": False, "message": msg}, status=400)
            messages.error(request, msg)
            return redirect(request.get_full_path())

        # Normalize phone to e164 (+91...)
        phone_e164 = _normalize_phone_e164(doctor_whatsapp)
        if not phone_e164:
            msg = f"Invalid WhatsApp number: {doctor_whatsapp}"
            _smdbg(f"POST validation failed: {msg}")
            if is_ajax:
                return JsonResponse({"success": False, "message": msg}, status=400)
            messages.error(request, "Please enter a valid WhatsApp number.")
            return redirect(request.get_full_path())

        # Ensure rep user exists
        rep_user = actual_user
        if not rep_user and UMUser and field_rep_email:
            rep_user = UMUser.objects.filter(email__iexact=field_rep_email).first()
        if not rep_user and UMUser:
            # very last resort: create minimal rep user to not block sharing
            try:
                rep_user = UMUser.objects.create_user(
                    username=f"field_rep_{field_rep_id}",
                    email=field_rep_email or f"field_rep_{field_rep_id}@example.com",
                    password=UMUser.objects.make_random_password(),
                    role="field_rep",
                    field_id=field_rep_field_id or "",
                )
                _smdbg(f"Created fallback rep_user id={rep_user.id}")
            except Exception as e:
                _smdbg(f"ERROR creating fallback rep_user: {e}")
                msg = "Unable to resolve field rep user for sharing."
                if is_ajax:
                    return JsonResponse({"success": False, "message": msg}, status=500)
                messages.error(request, msg)
                return redirect(request.get_full_path())

        # Save/Update Doctor under this rep
        try:
            phone_last10 = _re.sub(r"\D", "", phone_e164)[-10:]
            doctor_obj, created = Doctor.objects.update_or_create(
                rep=rep_user,
                phone=phone_last10,
                defaults={"name": doctor_name},
            )
            _smdbg(f"Doctor upsert ok id={doctor_obj.id} created={created} rep_user_id={rep_user.id} phone_last10={phone_last10}")
        except Exception as e:
            _smdbg(f"ERROR saving Doctor: {e}")
            if is_ajax:
                return JsonResponse({"success": False, "message": f"Failed to save doctor: {e}"}, status=500)
            messages.error(request, "Failed to save doctor. Please try again.")
            return redirect(request.get_full_path())

        # Build shortlink and log share (best effort)
        try:
            from collateral_management.models import Collateral as PortalCollateral
            collateral_obj = PortalCollateral.objects.get(id=collateral_id, is_active=True)
        except Exception as e:
            _smdbg(f"ERROR loading Collateral id={collateral_id}: {e}")
            msg = "Selected collateral not found or inactive."
            if is_ajax:
                return JsonResponse({"success": False, "message": msg}, status=404)
            messages.error(request, msg)
            return redirect(request.get_full_path())

        short_link = None
        try:
            short_link = find_or_create_short_link(collateral_obj, rep_user)
            short_url = request.build_absolute_uri(f"/shortlinks/go/{short_link.short_code}/")
            _smdbg(f"ShortLink ok short_code={short_link.short_code} short_url={short_url}")
        except Exception as e:
            _smdbg(f"ERROR creating short link: {e}")
            msg = "Failed to generate share link."
            if is_ajax:
                return JsonResponse({"success": False, "message": msg}, status=500)
            messages.error(request, msg)
            return redirect(request.get_full_path())

        # Try your existing share-log helper, else fallback ShareLog create
        try:
            from .utils.db_operations import log_manual_doctor_share
            log_manual_doctor_share(
                short_link_id=short_link.id,
                field_rep_id=rep_user.id,
                phone_e164=phone_e164,
                collateral_id=collateral_id,
            )
            _smdbg("log_manual_doctor_share OK")
        except Exception as e:
            _smdbg(f"log_manual_doctor_share failed (fallback to ShareLog). err={e}")
            try:
                # ShareLog schema differs across your revisions; keep it defensive
                kwargs = dict(
                    short_link=short_link,
                    field_rep=rep_user,
                    doctor_identifier=phone_e164,
                    share_channel="WhatsApp",
                    share_timestamp=timezone.now(),
                )
                # If ShareLog has collateral FK, include it
                try:
                    kwargs["collateral"] = collateral_obj
                except Exception:
                    pass
                ShareLog.objects.create(**kwargs)
                _smdbg("Fallback ShareLog create OK")
            except Exception as e2:
                _smdbg(f"Fallback ShareLog create FAILED err={e2}")

        # Build WA message
        try:
            message = get_brand_specific_message(
                collateral_id,
                selected_collateral.get("name") or getattr(collateral_obj, "title", "Collateral"),
                short_url,
                brand_campaign_id=brand_campaign_id,
            )
        except Exception as e:
            _smdbg(f"ERROR building brand message: {e}")
            message = f"Hello Doctor, please check this: {short_url}"

        wa_number = _re.sub(r"\D", "", phone_e164)
        wa_url = f"https://wa.me/{wa_number}?text={_up.quote(message)}"
        _smdbg(f"Returning WhatsApp URL: {wa_url[:120]}...")

        if is_ajax:
            return JsonResponse({
                "success": True,
                "message": "Prepared WhatsApp share link.",
                "whatsapp_url": wa_url,
                "doctor_id": doctor_obj.id,
            })

        return redirect(wa_url)

    # --- GET render ---
    return render(request, "sharing_management/fieldrep_gmail_share_collateral.html", {
        "fieldrep_id": field_rep_field_id or "Unknown",
        "fieldrep_email": field_rep_email,
        "collaterals": collaterals_list,
        "brand_campaign_id": brand_campaign_id,
        "doctors": doctors_with_status,
        "selected_collateral_id": selected_collateral_id,
    })


# -----------------------------------------------------------------------------
# Dashboard (Manage Collateral Panel) (DEFAULT DB collaterals)
# -----------------------------------------------------------------------------
@field_rep_required
@never_cache
def fieldrep_dashboard(request):
    campaign_filter = (request.GET.get("campaign") or "").strip()
    search_query = (request.GET.get("search") or "").strip()

    # Base: show all active campaign-collateral links
    qs = CMCampaignCollateral.objects.select_related("campaign", "collateral").filter(collateral__is_active=True)
    if campaign_filter:
        qs = qs.filter(campaign__brand_campaign_id=campaign_filter)

    # Build deduped collateral rows
    rows = []
    seen = set()
    for link in qs:
        c = link.collateral
        if not c or c.id in seen:
            continue
        seen.add(c.id)

        # If search_query present, only keep if campaign id matches
        if search_query:
            bc_id = getattr(link.campaign, "brand_campaign_id", "") or ""
            if search_query.lower() not in bc_id.lower():
                continue

        has_pdf = bool(getattr(c, "file", None))
        has_vid = bool(getattr(c, "vimeo_url", ""))

        final_url = c.file.url if has_pdf else (getattr(c, "vimeo_url", "") or "")

        rows.append(
            {
                "brand_id": getattr(link.campaign, "brand_campaign_id", "") if link.campaign else "",
                "item_name": getattr(c, "title", ""),
                "description": getattr(c, "description", ""),
                "url": final_url,
                "has_both": has_pdf and has_vid,
                "id": getattr(c, "id", None),
                "campaign_collateral_id": link.pk,
            }
        )

    campaign_id = campaign_filter or request.GET.get("campaign") or ""

    response = render(
        request,
        "sharing_management/fieldrep_dashboard.html",
        {
            "stats": [],  # not used by template
            "collaterals": rows,
            "search_query": search_query,
            "campaign_filter": campaign_filter,
            "brand_campaign_id": campaign_filter,
            "campaign_id": campaign_id,
        },
    )
    response["Cache-Control"] = "no-store, no-cache, max-age=0, must-revalidate"
    response["Pragma"] = "no-cache"
    return response


# -----------------------------------------------------------------------------
# Campaign detail (kept; adjust ShareLog filtering to master id if needed)
# -----------------------------------------------------------------------------
@field_rep_required
def fieldrep_campaign_detail(request, campaign_id):
    # NOTE: This endpoint is currently tied to your DEFAULT DB campaign ids.
    # If you want this to be master-only, you should refactor it separately.
    from campaign_management.models import CampaignCollateral as CampaignMgmtCC
    from campaign_management.models import CampaignAssignment

    rep_user = request.user
    get_object_or_404(CampaignAssignment, field_rep=rep_user, campaign_id=campaign_id)

    ccols = CampaignMgmtCC.objects.filter(campaign_id=campaign_id).select_related("collateral")
    col_ids = [cc.collateral_id for cc in ccols]

    # ShareLogs are now keyed by MASTER field rep id.
    master_rep_id = _resolve_master_fieldrep_id_from_portal_user(rep_user)

    shares = ShareLog.objects.filter(
        short_link__resource_type="collateral",
        short_link__resource_id__in=col_ids,
    ).select_related("short_link")

    if master_rep_id:
        shares = shares.filter(field_rep_id=master_rep_id)

    doctor_map = {}
    for s in shares:
        cid = s.short_link.resource_id
        doctor_map.setdefault(cid, {})[s.doctor_identifier] = s.short_link

    engagements = DoctorEngagement.objects.filter(
        short_link__resource_id__in=col_ids,
        short_link__resource_type="collateral",
    ).select_related("short_link")

    engagement_map = {e.short_link_id: e for e in engagements}

    rows = []
    for cc in ccols:
        col = cc.collateral
        cid = col.id
        doctor_statuses = []
        for doctor, short_link in doctor_map.get(cid, {}).items():
            eng = engagement_map.get(short_link.id)
            status = 0
            detail = ""
            if col.type == "pdf":
                if eng:
                    if eng.pdf_completed:
                        status = 2
                        detail = f"{eng.last_page_scrolled} (completed)"
                    elif eng.last_page_scrolled > 0:
                        status = 1
                        detail = f"{eng.last_page_scrolled} (partial)"
            elif col.type == "video":
                if eng:
                    if eng.video_watch_percentage >= 90:
                        status = 2
                        detail = f"{eng.video_watch_percentage}% (completed)"
                    elif eng.video_watch_percentage > 0:
                        status = 1
                        detail = f"{eng.video_watch_percentage}% (partial)"
            doctor_statuses.append({"doctor": doctor, "status": status, "detail": detail})
        rows.append({"collateral": col, "doctor_statuses": doctor_statuses})

    return render(request, "sharing_management/fieldrep_campaign_detail.html", {"rows": rows})


# -----------------------------------------------------------------------------
# Calendar edit (kept - DEFAULT DB)
# -----------------------------------------------------------------------------
def edit_collateral_dates(request, pk):
    collateral = get_object_or_404(Collateral, pk=pk)
    if request.method == "POST":
        form = CollateralForm(request.POST, request.FILES, instance=collateral)
        if form.is_valid():
            form.save()
            return redirect("collateral_list")
    else:
        form = CollateralForm(instance=collateral)
    return render(request, "collaterals/edit_collateral_dates.html", {"form": form, "collateral": collateral})


def edit_campaign_calendar(request):
    from campaign_management.models import Campaign  # DEFAULT DB
    from django.http import JsonResponse

    collateral_object = None
    brand_filter = request.GET.get("brand") or request.GET.get("campaign")
    if brand_filter:
        campaign_collaterals = (
            CMCampaignCollateral.objects.select_related("campaign", "collateral")
            .filter(campaign__brand_campaign_id=brand_filter)
        )
    else:
        campaign_collaterals = CMCampaignCollateral.objects.select_related("campaign", "collateral").all()

    edit_id = request.GET.get("id")
    if edit_id:
        try:
            existing_record = CMCampaignCollateral.objects.get(id=edit_id)
            collateral_object = existing_record.collateral
            if request.method == "POST":
                form = CalendarCampaignCollateralForm(request.POST, instance=existing_record)
                if form.is_valid():
                    saved_instance = form.save()
                    if request.headers.get("x-requested-with") == "XMLHttpRequest":
                        return JsonResponse(
                            {
                                "success": True,
                                "id": saved_instance.id,
                                "brand_campaign_id": saved_instance.campaign.brand_campaign_id,
                                "collateral_id": saved_instance.collateral_id,
                                "collateral_name": str(saved_instance.collateral),
                                "start_date": saved_instance.start_date.strftime("%Y-%m-%d") if saved_instance.start_date else "",
                                "end_date": saved_instance.end_date.strftime("%Y-%m-%d") if saved_instance.end_date else "",
                            }
                        )
                    return redirect(f"/share/edit-calendar/?id={edit_id}")
            else:
                form = CalendarCampaignCollateralForm(instance=existing_record)
        except CMCampaignCollateral.DoesNotExist:
            messages.error(request, "Record not found.")
            return redirect("edit_campaign_calendar")
    else:
        if request.method == "POST":
            collateral_id = request.POST.get("collateral")
            brand_campaign_id = (request.POST.get("campaign") or "").strip()
            if not collateral_id:
                messages.error(request, "Please select a collateral.")
                return redirect("edit_campaign_calendar")

            existing_qs = CMCampaignCollateral.objects.filter(collateral_id=collateral_id)
            if brand_campaign_id:
                existing_qs = existing_qs.filter(campaign__brand_campaign_id=brand_campaign_id)
            existing_record = existing_qs.first()

            if existing_record:
                form = CalendarCampaignCollateralForm(request.POST, instance=existing_record)
                if form.is_valid():
                    saved_instance = form.save()
                    if request.headers.get("x-requested-with") == "XMLHttpRequest":
                        return JsonResponse(
                            {
                                "success": True,
                                "id": saved_instance.id,
                                "brand_campaign_id": saved_instance.campaign.brand_campaign_id,
                                "collateral_id": saved_instance.collateral_id,
                                "collateral_name": str(saved_instance.collateral),
                                "start_date": saved_instance.start_date.strftime("%Y-%m-%d") if saved_instance.start_date else "",
                                "end_date": saved_instance.end_date.strftime("%Y-%m-%d") if saved_instance.end_date else "",
                            }
                        )
                    return redirect("edit_campaign_calendar")
            else:
                if not brand_campaign_id:
                    messages.error(request, "Brand Campaign ID is required to create a new campaign collateral.")
                    return redirect("edit_campaign_calendar")

                try:
                    campaign = Campaign.objects.get(brand_campaign_id=brand_campaign_id)
                except Campaign.DoesNotExist:
                    messages.error(request, f'Campaign with Brand Campaign ID "{brand_campaign_id}" not found.')
                    return redirect("edit_campaign_calendar")

                form = CalendarCampaignCollateralForm(request.POST)
                if form.is_valid():
                    instance = form.save(commit=False)
                    instance.campaign = campaign
                    instance.save()
                    return redirect("edit_campaign_calendar")

        initial = {}
        prefill_collateral_id = request.GET.get("collateral_id")
        prefill_brand = request.GET.get("brand") or request.GET.get("campaign")
        if prefill_brand:
            initial["campaign"] = prefill_brand
        if prefill_collateral_id:
            initial["collateral"] = prefill_collateral_id

        form_kwargs = {"initial": initial}
        if prefill_brand:
            form_kwargs["brand_campaign_id"] = prefill_brand

        form = CalendarCampaignCollateralForm(**form_kwargs)

    return render(
        request,
        "sharing_management/edit_calendar.html",
        {
            "form": form,
            "campaign_collaterals": campaign_collaterals,
            "collateral": collateral_object,
            "title": "Edit Calendar",
            "editing": bool(edit_id),
        },
    )


# -----------------------------------------------------------------------------
# Doctors list (kept)
# -----------------------------------------------------------------------------
@csrf_exempt
def get_doctor_status(doctor, collateral):
    share_log = ShareLog.objects.filter(
        doctor_identifier=doctor.phone,
        collateral=collateral,
    ).order_by("-share_timestamp").first()

    if not share_log:
        return "not_shared"

    engagement = DoctorEngagement.objects.filter(
        short_link__resource_id=collateral.id,
        short_link__resource_type="collateral",
        doctor=doctor,
    ).first()

    if engagement:
        return "viewed"

    six_days_ago = timezone.now() - timedelta(days=6)
    if share_log.share_timestamp <= six_days_ago:
        return "needs_reminder"

    return "shared"


def get_doctor_status_class(status):
    return {
        "not_shared": "btn-danger",
        "shared": "btn-warning",
        "needs_reminder": "btn-purple",
        "viewed": "btn-success",
    }.get(status, "btn-secondary")


def get_doctor_status_text(status):
    return {
        "not_shared": "Send Message",
        "shared": "Sent",
        "needs_reminder": "Send Reminder",
        "viewed": "Viewed",
    }.get(status, "Unknown")


def doctor_list(request, campaign_id=None):
    from campaign_management.models import CampaignAssignment

    user = request.user
    campaign = None
    if campaign_id:
        campaign = get_object_or_404(CampaignAssignment, id=campaign_id)

    collateral_id = request.GET.get("collateral") or request.POST.get("collateral")
    if not collateral_id and request.method == "GET":
        latest_collateral = Collateral.objects.filter(is_active=True).order_by("-created_at").first()
        if latest_collateral:
            collateral_id = latest_collateral.id

    collateral = None
    if collateral_id:
        collateral = get_object_or_404(Collateral, id=collateral_id)

    if campaign:
        doctors = Doctor.objects.filter(Q(rep=user) | Q(campaignassignment=campaign)).distinct()
    else:
        doctors = Doctor.objects.filter(rep=user)

    doctor_statuses = []
    if collateral:
        for doctor in doctors:
            status = get_doctor_status(doctor, collateral)
            doctor_statuses.append(
                {
                    "doctor": doctor,
                    "status": status,
                    "status_class": get_doctor_status_class(status),
                    "status_text": get_doctor_status_text(status),
                    "last_shared": ShareLog.objects.filter(
                        doctor_identifier=doctor.phone,
                        collateral=collateral,
                    ).order_by("-share_timestamp").first(),
                }
            )

    return render(
        request,
        "sharing_management/doctor_list.html",
        {
            "doctors": doctor_statuses if collateral else [],
            "collateral": collateral,
            "campaign": campaign,
            "all_collaterals": Collateral.objects.filter(is_active=True).order_by("-created_at"),
        },
    )


# -----------------------------------------------------------------------------
# Video tracking (kept)
# -----------------------------------------------------------------------------
def video_tracking(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    transaction_id = request.POST.get("collateral_sharing")
    user_id = request.POST.get("userId")
    video_status = request.POST.get("status")
    comment = "Video Viewed"

    if not (transaction_id and user_id and video_status):
        return HttpResponseBadRequest("Missing required parameters.")

    if video_status == "1":
        video_percentage = "1"
    elif video_status == "2":
        video_percentage = "2"
    elif video_status == "3":
        video_percentage = "3"
    else:
        return HttpResponseBadRequest("Invalid video status.")

    try:
        share_log = ShareLog.objects.get(id=transaction_id)
    except ShareLog.DoesNotExist:
        return HttpResponseBadRequest("Transaction not found in ShareLog table.")

    exists = VideoTrackingLog.objects.filter(
        share_log=share_log,
        user_id=user_id,
        video_percentage=video_percentage,
    ).exists()

    if exists:
        return JsonResponse({"status": "exists", "msg": "This video progress state has already been recorded."})

    video_log = VideoTrackingLog.objects.create(
        share_log=share_log,
        user_id=user_id,
        video_status=video_status,
        video_percentage=video_percentage,
        comment=comment,
    )

    try:
        sl = ShareLog.objects.get(id=video_log.share_log_id)
        pct = int(float(video_log.video_percentage)) if video_log.video_percentage else 0
        mark_video_event(
            sl,
            status=int(video_log.video_status),
            percentage=pct,
            event_id=video_log.id,
            when=getattr(video_log, "created_at", timezone.now()),
        )
    except ShareLog.DoesNotExist:
        pass
    except Exception:
        pass

    return JsonResponse({"status": "success", "msg": "New video tracking log inserted successfully."})


# -----------------------------------------------------------------------------
# Debug + delete collateral (kept)
# -----------------------------------------------------------------------------
def debug_collaterals(request):
    collaterals = Collateral.objects.all()[:20]
    UserModel = get_user_model()
    field_reps = UserModel.objects.all()[:10]

    html = "<h2>Debug Information</h2>"
    html += "<h3>Available Collaterals:</h3><ul>"
    for col in collaterals:
        html += f"<li>ID: {col.id}, Name: {getattr(col, 'title', 'N/A')}, Active: {getattr(col, 'is_active', False)}</li>"
    html += "</ul>"

    html += "<h3>Available Users:</h3><ul>"
    for rep in field_reps:
        html += f"<li>ID: {rep.id}, Email: {getattr(rep, 'email', '')}</li>"
    html += "</ul>"

    return HttpResponse(html)


@field_rep_required
def dashboard_delete_collateral(request, pk):
    if request.method == "POST":
        try:
            collateral = Collateral.objects.get(pk=pk, is_active=True)
            collateral.is_active = False
            collateral.save()
        except Collateral.DoesNotExist:
            messages.warning(request, "This collateral has already been deleted or does not exist.")
        except Exception as e:
            messages.error(request, f"Error deleting collateral: {str(e)}")

        campaign_filter = request.POST.get("campaign") or request.GET.get("campaign", "")
        if campaign_filter:
            return redirect(f"{reverse('fieldrep_dashboard')}?campaign={campaign_filter}")
        return redirect("fieldrep_dashboard")

    campaign_filter = request.GET.get("campaign", "")
    if campaign_filter:
        return redirect(f"{reverse('fieldrep_dashboard')}?campaign={campaign_filter}")
    return redirect("fieldrep_dashboard")
