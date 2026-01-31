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


# -----------------------------------------------------------------------------
# DB helpers
# -----------------------------------------------------------------------------
def _master_db_alias() -> str:
    return getattr(settings, "MASTER_DB_ALIAS", "master")


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


def find_or_create_short_link(collateral: Collateral, user) -> ShortLink:
    existing = ShortLink.objects.filter(
        resource_type="collateral",
        resource_id=collateral.id,
        is_active=True,
    ).first()
    if existing:
        return existing

    short_code = generate_short_code(length=8)
    return ShortLink.objects.create(
        short_code=short_code,
        resource_type="collateral",
        resource_id=collateral.id,
        created_by=user,
        date_created=timezone.now(),
        is_active=True,
    )


def get_brand_specific_message(collateral_id, collateral_name, collateral_link, brand_campaign_id=None):
    bc_id = (str(brand_campaign_id).strip() if brand_campaign_id else "")
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


def fieldrep_create_password(request):
    email = (request.GET.get("email") or request.POST.get("email") or "").strip()
    brand_campaign_id = (request.GET.get("campaign") or request.POST.get("campaign") or "").strip()

    try:
        security_questions = (
            SecurityQuestion.objects.filter(is_active=True)
            .values_list("id", "question_txt")
        )
    except Exception:
        security_questions = []

    if request.method == "POST":
        field_id = (request.POST.get("field_id") or "").strip()
        first_name = (request.POST.get("first_name") or "").strip()
        last_name = (request.POST.get("last_name") or "").strip()
        whatsapp_number = (request.POST.get("whatsapp_number") or "").strip()

        password = request.POST.get("password") or ""
        confirm_password = request.POST.get("confirm_password") or ""
        security_question_id = request.POST.get("security_question")
        security_answer = (request.POST.get("security_answer") or "").strip()

        if whatsapp_number and (not whatsapp_number.isdigit() or len(whatsapp_number) < 10 or len(whatsapp_number) > 15):
            return render(
                request,
                "sharing_management/fieldrep_create_password.html",
                {
                    "email": email,
                    "security_questions": security_questions,
                    "brand_campaign_id": brand_campaign_id,
                    "error": "Please enter a valid WhatsApp number (10-15 digits).",
                },
            )

        if password != confirm_password:
            return render(
                request,
                "sharing_management/fieldrep_create_password.html",
                {
                    "email": email,
                    "security_questions": security_questions,
                    "brand_campaign_id": brand_campaign_id,
                    "error": "Passwords do not match.",
                },
            )

        if not brand_campaign_id:
            return render(
                request,
                "sharing_management/fieldrep_create_password.html",
                {
                    "email": email,
                    "security_questions": security_questions,
                    "brand_campaign_id": brand_campaign_id,
                    "error": "Brand Campaign ID is required.",
                },
            )

        try:
            # 1) master auth user
            master_user = _master_upsert_auth_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
                raw_password=password,
            )

            # 2) master field rep (+ campaign link)
            full_name = f"{first_name} {last_name}".strip() or (email.split("@")[0] if email else "")
            master_rep = _master_upsert_fieldrep(
                master_user=master_user,
                master_campaign_id=brand_campaign_id,
                full_name=full_name,
                phone_number=whatsapp_number,
                brand_supplied_field_rep_id=field_id,
                raw_password=password,
            )

            # 3) store security Q/A in DEFAULT DB
            if security_question_id and security_answer:
                try:
                    q_obj = SecurityQuestion.objects.filter(id=security_question_id, is_active=True).first()
                except Exception:
                    q_obj = None

                prof, _ = FieldRepSecurityProfile.objects.get_or_create(master_field_rep_id=int(master_rep.id))
                prof.email = (email or "").lower()
                prof.security_question = q_obj
                prof.security_answer_hash = make_password(security_answer)
                prof.save()

            # 4) sync to portal (default DB) best-effort
            _ensure_portal_user_for_master_fieldrep(master_rep, raw_password=password)

        except Exception as e:
            return render(
                request,
                "sharing_management/fieldrep_create_password.html",
                {
                    "email": email,
                    "security_questions": security_questions,
                    "brand_campaign_id": brand_campaign_id,
                    "error": f"Registration failed: {e}",
                },
            )

        redirect_url = "/share/fieldrep-login/"
        if brand_campaign_id:
            redirect_url += f"?campaign={urllib.parse.quote(brand_campaign_id)}"
        return redirect(redirect_url)

    return render(
        request,
        "sharing_management/fieldrep_create_password.html",
        {
            "email": email,
            "security_questions": security_questions,
            "brand_campaign_id": brand_campaign_id,
        },
    )


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


# -----------------------------------------------------------------------------
# Field Rep Gmail login/share (MASTER DB reps, DEFAULT DB collaterals)
# -----------------------------------------------------------------------------
def fieldrep_gmail_login(request):
    brand_campaign_id = (request.GET.get("brand_campaign_id") or request.GET.get("campaign") or "").strip()

    if request.method == "POST":
        if "register" in request.POST:
            messages.error(request, "Registration is not allowed from this login link. Please use the registration link.")
            return render(request, "sharing_management/fieldrep_gmail_login.html", {"brand_campaign_id": brand_campaign_id})

        field_id = (request.POST.get("field_id") or "").strip()
        gmail_id = (request.POST.get("gmail_id") or "").strip()
        brand_campaign_id = (request.POST.get("brand_campaign_id") or brand_campaign_id or "").strip()

        if not field_id or not gmail_id:
            messages.error(request, "Please provide both Field ID and Gmail ID.")
            return render(request, "sharing_management/fieldrep_gmail_login.html", {"brand_campaign_id": brand_campaign_id})

        rep = _master_get_fieldrep_by_field_id_and_email(field_id, gmail_id)
        if not rep:
            messages.error(request, "Invalid Field ID or Gmail ID. Please check and try again.")
            return render(request, "sharing_management/fieldrep_gmail_login.html", {"brand_campaign_id": brand_campaign_id})

        # Optional: enforce assignment to campaign if campaign provided
        if brand_campaign_id:
            assigned = MasterCampaignFieldRep.objects.using(_master_db_alias()).filter(
                campaign_id=brand_campaign_id, field_rep_id=int(rep.id)
            ).exists()
            if not assigned:
                messages.error(request, "You are not assigned to this campaign.")
                return render(request, "sharing_management/fieldrep_gmail_login.html", {"brand_campaign_id": brand_campaign_id})

        _clear_google_session_keys(request)

        request.session["field_rep_id"] = int(rep.id)  # MASTER fieldrep id
        request.session["field_rep_email"] = (rep.user.email or "").strip()
        request.session["field_rep_field_id"] = (rep.brand_supplied_field_rep_id or "").strip()

        messages.success(request, f"Welcome back, {rep.brand_supplied_field_rep_id or rep.id}!")

        _ensure_portal_user_for_master_fieldrep(rep)

        if brand_campaign_id:
            return redirect(f"/share/fieldrep-gmail-share-collateral/?brand_campaign_id={urllib.parse.quote(brand_campaign_id)}")
        return redirect("fieldrep_gmail_share_collateral")

    return render(request, "sharing_management/fieldrep_gmail_login.html", {"brand_campaign_id": brand_campaign_id})


def fieldrep_gmail_share_collateral(request, brand_campaign_id=None):
    import urllib.parse as _up

    master_field_rep_id = request.session.get("field_rep_id")
    field_rep_email = request.session.get("field_rep_email")
    field_rep_field_id = request.session.get("field_rep_field_id")

    if brand_campaign_id is None:
        brand_campaign_id = (request.GET.get("brand_campaign_id") or "").strip()

    if not master_field_rep_id:
        messages.error(request, "Please login first.")
        return redirect("fieldrep_login")

    rep = (
        MasterFieldRep.objects.using(_master_db_alias())
        .select_related("user", "brand")
        .filter(id=int(master_field_rep_id), is_active=True)
        .first()
    )
    if not rep:
        messages.error(request, "Field rep not found or inactive. Please login again.")
        return redirect("fieldrep_login")

    portal_user = _ensure_portal_user_for_master_fieldrep(rep)

    allowed_campaign_ids = _master_get_campaign_ids_for_fieldrep(int(rep.id))
    if brand_campaign_id and brand_campaign_id not in allowed_campaign_ids:
        messages.error(request, "You are not assigned to this campaign.")
        brand_campaign_id = ""  # fall back to all assigned

    campaign_ids_to_use = [brand_campaign_id] if brand_campaign_id else allowed_campaign_ids

    # Collaterals list
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

        seen = set()
        for c in collaterals:
            if c.id in seen:
                continue
            seen.add(c.id)
            short_link = find_or_create_short_link(c, portal_user or request.user)
            collaterals_list.append(
                {
                    "id": c.id,
                    "name": getattr(c, "title", getattr(c, "name", "Untitled")),
                    "description": getattr(c, "description", ""),
                    "link": request.build_absolute_uri(f"/shortlinks/go/{short_link.short_code}/"),
                }
            )
    except Exception as e:
        print(f"[fieldrep_gmail_share_collateral] Error fetching collaterals: {e}")
        collaterals_list = []
        messages.error(request, "Error loading collaterals. Please try again.")

    # Assigned doctors from DEFAULT DB
    assigned_doctors = Doctor.objects.filter(rep=portal_user) if portal_user else Doctor.objects.none()

    selected_collateral_id = (request.GET.get("collateral") or "").strip()
    if not selected_collateral_id and collaterals_list:
        selected_collateral_id = str(collaterals_list[0]["id"])

    doctors_with_status = []
    six_days_ago = timezone.now() - timedelta(days=6)

    for doctor in assigned_doctors:
        status = "not_sent"
        if selected_collateral_id:
            phone_val = doctor.phone or ""
            phone_clean = re.sub(r"\D", "", phone_val)
            possible_ids = [phone_val]
            if phone_clean and len(phone_clean) == 10:
                possible_ids.extend([f"+91{phone_clean}", f"91{phone_clean}", phone_clean])

            share_log = (
                ShareLog.objects.filter(
                    doctor_identifier__in=possible_ids,
                    collateral_id=int(selected_collateral_id),
                    field_rep_id=int(rep.id),
                )
                .order_by("-share_timestamp")
                .first()
            )
            if share_log:
                engaged = CollateralTransaction.objects.filter(
                    field_rep_id=int(rep.id),
                    doctor_number=share_log.doctor_identifier,
                    collateral_id=share_log.collateral_id or int(selected_collateral_id),
                    has_viewed=True,
                ).exists()

                if engaged:
                    status = "opened"
                else:
                    status = "reminder" if share_log.share_timestamp and share_log.share_timestamp < six_days_ago else "sent"

        doctors_with_status.append(
            {"id": doctor.id, "name": doctor.name, "phone": doctor.phone, "status": status}
        )

    if request.method == "POST":
        doctor_id = request.POST.get("doctor_id")
        doctor_name = (request.POST.get("doctor_name") or "").strip()
        doctor_whatsapp = (request.POST.get("doctor_whatsapp") or "").strip()
        collateral_id_str = (request.POST.get("collateral") or "").strip()

        if not collateral_id_str.isdigit():
            messages.error(request, "Please select a valid collateral.")
            return redirect(request.path)

        collateral_id = int(collateral_id_str)
        selected_collateral = next((c for c in collaterals_list if c["id"] == collateral_id), None)
        if not selected_collateral:
            messages.error(request, "Selected collateral not found.")
            return redirect(request.path)

        # If doctor_id is provided, prefer that doctor
        if doctor_id and str(doctor_id).isdigit() and portal_user:
            d = Doctor.objects.filter(id=int(doctor_id), rep=portal_user).first()
            if d:
                doctor_name = doctor_name or d.name
                doctor_whatsapp = doctor_whatsapp or d.phone

        if doctor_name and doctor_whatsapp:
            phone_e164 = _normalize_phone_e164(doctor_whatsapp)
            if not phone_e164:
                messages.error(request, "Please enter a valid WhatsApp number.")
                return redirect(request.path)

            # store doctor under rep
            if portal_user:
                Doctor.objects.update_or_create(
                    rep=portal_user,
                    phone=re.sub(r"\D", "", phone_e164)[-10:],
                    defaults={"name": doctor_name},
                )

            collateral_obj = Collateral.objects.get(id=collateral_id, is_active=True)
            short_link = find_or_create_short_link(collateral_obj, portal_user or request.user)

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
                collateral_id,
                selected_collateral["name"],
                selected_collateral["link"],
                brand_campaign_id=brand_campaign_id,
            )
            wa_number = re.sub(r"\D", "", phone_e164).lstrip("+")
            wa_url = f"https://wa.me/{wa_number}?text={_up.quote(message)}"
            return redirect(wa_url)

        messages.error(request, "Please fill all required fields.")
        return redirect(request.path)

    return render(
        request,
        "sharing_management/fieldrep_gmail_share_collateral.html",
        {
            "fieldrep_id": field_rep_field_id or "Unknown",
            "fieldrep_email": field_rep_email,
            "collaterals": collaterals_list,
            "brand_campaign_id": brand_campaign_id,
            "doctors": doctors_with_status,
            "selected_collateral_id": selected_collateral_id,
        },
    )


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
