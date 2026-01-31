# sharing_management/views.py
from __future__ import annotations

import csv
import json
import re
import urllib.parse
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, Max, Q
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model

from .decorators import field_rep_required
from .forms import ShareForm, CollateralForm
from sharing_management.forms import CalendarCampaignCollateralForm

from .models import ShareLog, VideoTrackingLog, FieldRepresentative, CollateralTransaction
from doctor_viewer.models import Doctor, DoctorEngagement
from campaign_management.models import Campaign, CampaignAssignment
from admin_dashboard.models import FieldRepCampaign

from collateral_management.models import Collateral
from collateral_management.models import CampaignCollateral as CMCampaignCollateral

from shortlink_management.models import ShortLink
from shortlink_management.utils import generate_short_code

from sharing_management.services.transactions import (
    upsert_from_sharelog,
    mark_viewed,
    mark_pdf_progress,
    mark_downloaded_pdf,
    mark_video_event,
)

from utils.recaptcha import recaptcha_required

from .utils.db_operations import (
    register_field_representative,
    validate_forgot_password,
    get_security_question_by_email,
    authenticate_field_representative,
    reset_field_representative_password,
)

# ---------------------------------------------------------------------
# Tracking endpoint (kept)
# ---------------------------------------------------------------------
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
    engagement.save(update_fields=[
        "last_page_scrolled",
        "pdf_completed",
        "video_watch_percentage",
        "status",
        "updated_at",
    ])

    # Update CollateralTransaction using ShareLog (best effort)
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


# ---------------------------------------------------------------------
# Portal sync helper (kept)
# ---------------------------------------------------------------------
def _sync_fieldrep_to_campaign_portal(
    *,
    brand_campaign_id: str,
    email: str,
    field_id: str = "",
    first_name: str = "",
    last_name: str = "",
    raw_password: str = "",
):
    """
    Ensure the Field Rep is visible in the Field Rep Portal for the specified brand campaign.

    Fail-safe: do not break registration/login flows if portal sync fails.
    """
    try:
        if not brand_campaign_id or not email:
            return

        from campaign_management.models import Campaign, CampaignAssignment
        from admin_dashboard.models import FieldRepCampaign
        from user_management.models import User  # portal user model

        campaign_obj = Campaign.objects.filter(brand_campaign_id=brand_campaign_id).first()
        if not campaign_obj:
            return

        user = User.objects.filter(email__iexact=email).first()
        if user:
            if getattr(user, "role", None) != "field_rep":
                return
        else:
            base_username = (email.split("@")[0] or email).strip()[:140]
            username_candidate = base_username or email[:140]
            suffix = 0
            while User.objects.filter(username=username_candidate).exists():
                suffix += 1
                username_candidate = f"{base_username}_{suffix}"[:150]

            user = User.objects.create_user(
                username=username_candidate,
                email=email.lower(),
                password=raw_password or User.objects.make_random_password(),
            )
            user.role = "field_rep"
            user.is_active = True
            user.field_id = field_id or user.field_id
            user.first_name = first_name or user.first_name
            user.last_name = last_name or user.last_name
            user.save()

        changed = False
        if field_id and not getattr(user, "field_id", None):
            user.field_id = field_id
            changed = True
        if first_name and not getattr(user, "first_name", ""):
            user.first_name = first_name
            changed = True
        if last_name and not getattr(user, "last_name", ""):
            user.last_name = last_name
            changed = True
        if changed:
            user.save()

        CampaignAssignment.objects.get_or_create(
            campaign=campaign_obj,
            field_rep=user,
            defaults={"assigned_by": None},
        )
        FieldRepCampaign.objects.get_or_create(
            campaign=campaign_obj,
            field_rep=user,
        )

    except Exception as e:
        print(f"Portal sync error: {e}")


def _send_email(to_addr: str, subject: str, body: str) -> None:
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[to_addr],
        fail_silently=False,
    )


def find_or_create_short_link(collateral, user):
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


def get_or_create_fieldrep_user(field_rep_id, field_rep_email, field_rep_field_id):
    """
    Ensure a user_management.User exists for field reps when the flow uses session-based auth.
    """
    from user_management.models import User
    from django.contrib.auth.hashers import make_password

    user = None

    if field_rep_field_id:
        user = User.objects.filter(field_id=field_rep_field_id, role="field_rep").first()

    if not user and field_rep_email:
        user = User.objects.filter(email=field_rep_email, role="field_rep").first()

    if not user and field_rep_field_id and field_rep_email:
        user = User.objects.create(
            username=f"fieldrep_{field_rep_field_id}",
            email=field_rep_email,
            field_id=field_rep_field_id,
            role="field_rep",
            password=make_password("defaultpass123"),
            is_active=True,
        )

    return user


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


def build_wa_link(share_log, request):
    if share_log.share_channel != "WhatsApp":
        return ""

    short_url = request.build_absolute_uri(f"/shortlinks/go/{share_log.short_link.short_code}/")
    msg_text = (
        share_log.message_text.replace("$collateralLinks", short_url)
        if share_log.message_text
        else f"Hello Doctor, please check this: {short_url}"
    )
    return f"https://wa.me/{share_log.doctor_identifier}?text={quote(msg_text)}"


from collateral_management.models import CollateralMessage
from campaign_management.models import CampaignCollateral as CampaignMgmtCampaignCollateral


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

    # Legacy fallback
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

    return (
        "Hello Doctor, IAP's latest expert module— Mini CME on Managing Drug-Resistant Infections in Pediatrics "
        "Strategies for using cefixime, cephalosporins, and carbapenems in complex cases, by Dr. Shekhar Biswas, "
        "covers strategies for using cefixime, cephalosporins, and carbapenems in complex pediatric cases. The presentation "
        "dives into understanding drug resistance, clinical evidence, and advanced therapeutic approaches to tackle multi-drug-resistant "
        "pathogens, along with antibiotic stewardship and infection control measures.\n\n"
        f"View it here: {collateral_link}\n\n"
        "This content is shared with you under a distribution license obtained from IAP by Alkem Laboratories Ltd."
    )


# ---------------------------------------------------------------------
# Core sharing (kept)
# ---------------------------------------------------------------------
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
            cc = CMCampaignCollateral.objects.filter(collateral_id=collateral_id).select_related("campaign").first()
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
                    pass  # frontend handles opening WA
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

            share_log = ShareLog.objects.create(
                short_link=short_link,
                field_rep=request.user,
                doctor_identifier=doctor_contact,
                share_channel=share_channel,
                share_timestamp=timezone.now(),
                message_text=message_text,
            )

            try:
                upsert_from_sharelog(
                    share_log,
                    brand_campaign_id=str(brand_campaign_id or ""),
                    doctor_name=None,
                    field_rep_unique_id=getattr(request.user, "employee_code", None),
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
    share_log = get_object_or_404(ShareLog, id=share_log_id, field_rep=request.user)
    wa_link = build_wa_link(share_log, request)
    return render(request, "sharing_management/share_success.html", {"share_log": share_log, "wa_link": wa_link})


@field_rep_required
def list_share_logs(request):
    logs_list = ShareLog.objects.filter(field_rep=request.user).order_by("-share_timestamp")
    paginator = Paginator(logs_list, 10)
    page_number = request.GET.get("page")
    logs = paginator.get_page(page_number)
    return render(request, "sharing_management/share_logs.html", {"logs": logs})


# ---------------------------------------------------------------------
# Dashboard (kept)
# ---------------------------------------------------------------------
@field_rep_required
@never_cache
def fieldrep_dashboard(request):
    rep = request.user
    assigned = CampaignAssignment.objects.filter(field_rep=rep).select_related("campaign")
    campaign_ids = [a.campaign_id for a in assigned]

    share_cnts = (
        ShareLog.objects.filter(
            field_rep=rep,
            short_link__resource_type="collateral",
            short_link__resource_id__in=CMCampaignCollateral.objects.filter(
                campaign_id__in=campaign_ids
            ).values_list("collateral_id", flat=True),
        )
        .values("short_link__resource_id")
        .annotate(cnt=Count("id"))
    )
    share_map = {r["short_link__resource_id"]: r["cnt"] for r in share_cnts}

    pdf_cnts = (
        DoctorEngagement.objects.filter(
            short_link__resource_type="collateral",
            last_page_scrolled__gt=0,
            short_link__resource_id__in=CMCampaignCollateral.objects.filter(
                campaign_id__in=campaign_ids
            ).values_list("collateral_id", flat=True),
        )
        .values("short_link__resource_id")
        .annotate(cnt=Count("id"))
    )
    pdf_map = {r["short_link__resource_id"]: r["cnt"] for r in pdf_cnts}

    vid_cnts = (
        DoctorEngagement.objects.filter(
            video_watch_percentage__gte=90,
            short_link__resource_type="collateral",
            short_link__resource_id__in=CMCampaignCollateral.objects.filter(
                campaign_id__in=campaign_ids
            ).values_list("collateral_id", flat=True),
        )
        .values("short_link__resource_id")
        .annotate(cnt=Count("id"))
    )
    vid_map = {r["short_link__resource_id"]: r["cnt"] for r in vid_cnts}

    stats = []
    for a in assigned:
        campaign = a.campaign
        campaign_collaterals = CMCampaignCollateral.objects.filter(campaign=campaign)
        collateral_ids = [cc.collateral_id for cc in campaign_collaterals]

        shares = sum(share_map.get(cid, 0) for cid in collateral_ids)
        pdfs = sum(pdf_map.get(cid, 0) for cid in collateral_ids)
        videos = sum(vid_map.get(cid, 0) for cid in collateral_ids)

        stats.append({"campaign": campaign, "shares": shares, "pdfs": pdfs, "videos": videos})

    campaign_filter = request.GET.get("campaign", "").strip()

    if campaign_filter:
        all_ccs = CMCampaignCollateral.objects.filter(
            campaign__brand_campaign_id=campaign_filter,
            collateral__is_active=True,
        ).select_related("collateral", "campaign")
    else:
        all_ccs = CMCampaignCollateral.objects.filter(
            campaign_id__in=campaign_ids,
            collateral__is_active=True,
        ).select_related("collateral", "campaign")

    all_collaterals = [cc.collateral for cc in all_ccs]

    search_query = request.GET.get("search", "").strip()
    if search_query:
        filtered = []
        for c in all_collaterals:
            cc = CMCampaignCollateral.objects.filter(collateral=c).select_related("campaign").first()
            campaign = cc.campaign if cc else None
            brand_id = campaign.brand_campaign_id if campaign else ""
            if search_query.lower() not in brand_id.lower():
                continue
            filtered.append(c)
        all_collaterals = filtered

    collaterals = []
    for c in all_collaterals:
        cc = CMCampaignCollateral.objects.filter(collateral=c).select_related("campaign").first()
        campaign = cc.campaign if cc else None

        has_pdf = bool(getattr(c, "file", None))
        has_vid = bool(getattr(c, "vimeo_url", ""))

        viewer_url = None
        if has_pdf and has_vid:
            try:
                sl = (
                    ShortLink.objects.filter(resource_type="collateral", resource_id=getattr(c, "id", None), is_active=True)
                    .order_by("-date_created")
                    .first()
                )
                if sl:
                    viewer_url = reverse("resolve_shortlink", args=[sl.short_code])
            except Exception:
                viewer_url = None

        final_url = viewer_url or (c.file.url if has_pdf else (getattr(c, "vimeo_url", "") or ""))

        collaterals.append({
            "brand_id": campaign.brand_campaign_id if campaign else "",
            "item_name": getattr(c, "title", ""),
            "description": getattr(c, "description", ""),
            "url": final_url,
            "has_both": has_pdf and has_vid,
            "id": getattr(c, "id", None),
            "campaign_collateral_id": cc.pk if cc else None,
        })

    campaign_id = request.GET.get("campaign", campaign_filter)

    response = render(
        request,
        "sharing_management/fieldrep_dashboard.html",
        {
            "stats": stats,
            "collaterals": collaterals,
            "search_query": search_query,
            "campaign_filter": campaign_filter,
            "brand_campaign_id": campaign_filter,
            "campaign_id": campaign_id,
        },
    )
    response["Cache-Control"] = "no-store, no-cache, max-age=0, must-revalidate"
    response["Pragma"] = "no-cache"
    return response


@field_rep_required
def fieldrep_campaign_detail(request, campaign_id):
    rep = request.user
    get_object_or_404(CampaignAssignment, field_rep=rep, campaign_id=campaign_id)

    from campaign_management.models import CampaignCollateral as CampaignMgmtCC

    ccols = CampaignMgmtCC.objects.filter(campaign_id=campaign_id).select_related("collateral")
    col_ids = [cc.collateral_id for cc in ccols]

    shares = ShareLog.objects.filter(
        field_rep=rep,
        short_link__resource_type="collateral",
        short_link__resource_id__in=col_ids,
    ).select_related("short_link")

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


# ---------------------------------------------------------------------
# Calendar edit (kept)
# ---------------------------------------------------------------------
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
    from django.http import JsonResponse
    from collateral_management.models import CampaignCollateral as CMCampaignCollateral

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
                        return JsonResponse({
                            "success": True,
                            "id": saved_instance.id,
                            "brand_campaign_id": saved_instance.campaign.brand_campaign_id,
                            "collateral_id": saved_instance.collateral_id,
                            "collateral_name": str(saved_instance.collateral),
                            "start_date": saved_instance.start_date.strftime("%Y-%m-%d") if saved_instance.start_date else "",
                            "end_date": saved_instance.end_date.strftime("%Y-%m-%d") if saved_instance.end_date else "",
                        })
                    return redirect(f"/share/edit-calendar/?id={edit_id}")
            else:
                form = CalendarCampaignCollateralForm(instance=existing_record)
        except CMCampaignCollateral.DoesNotExist:
            messages.error(request, "Record not found.")
            return redirect("edit_campaign_calendar")
    else:
        if request.method == "POST":
            collateral_id = request.POST.get("collateral")
            brand_campaign_id = request.POST.get("campaign", "").strip()
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
                        return JsonResponse({
                            "success": True,
                            "id": saved_instance.id,
                            "brand_campaign_id": saved_instance.campaign.brand_campaign_id,
                            "collateral_id": saved_instance.collateral_id,
                            "collateral_name": str(saved_instance.collateral),
                            "start_date": saved_instance.start_date.strftime("%Y-%m-%d") if saved_instance.start_date else "",
                            "end_date": saved_instance.end_date.strftime("%Y-%m-%d") if saved_instance.end_date else "",
                        })
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

    return render(request, "sharing_management/edit_calendar.html", {
        "form": form,
        "campaign_collaterals": campaign_collaterals,
        "collateral": collateral_object,
        "title": "Edit Calendar",
        "editing": bool(edit_id),
    })


# ---------------------------------------------------------------------
# Field rep registration/login (kept; prefilled redirects removed)
# ---------------------------------------------------------------------
def fieldrep_email_registration(request):
    if request.method == "POST":
        email = request.POST.get("email")
        brand_campaign_id = request.POST.get("brand_campaign_id") or request.GET.get("campaign")
        redirect_url = f"/share/fieldrep-create-password/?email={email}"
        if brand_campaign_id:
            redirect_url += f"&campaign={brand_campaign_id}"
        return redirect(redirect_url)

    brand_campaign_id = request.GET.get("campaign")
    return render(request, "sharing_management/fieldrep_email_registration.html", {"brand_campaign_id": brand_campaign_id})


def fieldrep_create_password(request):
    email = request.GET.get("email") or request.POST.get("email")
    brand_campaign_id = request.GET.get("campaign") or request.POST.get("campaign")

    try:
        from .models import SecurityQuestion
        security_questions = SecurityQuestion.objects.all().values_list("id", "question_txt")
    except Exception:
        security_questions = []

    if request.method == "POST":
        field_id = request.POST.get("field_id")
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        whatsapp_number = request.POST.get("whatsapp_number", "").strip()
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")
        security_question_id = request.POST.get("security_question")
        security_answer = request.POST.get("security_answer")

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

        success = register_field_representative(
            field_id=field_id,
            email=email,
            whatsapp_number=whatsapp_number,
            password=password,
            security_question_id=security_question_id,
            security_answer=security_answer,
        )
        if not success:
            return render(request, "sharing_management/fieldrep_create_password.html", {
                "email": email,
                "security_questions": security_questions,
                "brand_campaign_id": brand_campaign_id,
                "error": "Registration failed. Please try again.",
            })

        # create portal user record best effort (kept behavior)
        try:
            from .utils.db_operations import register_user_management_user
            register_user_management_user(
                email=email,
                username=email,
                password=password,
                security_answers=[(security_question_id, security_answer)],
            )
        except Exception:
            pass

        # local assign (kept)
        if brand_campaign_id:
            field_rep_user = get_user_model().objects.filter(email__iexact=email, role="field_rep", active=True).first()
            campaign = Campaign.objects.filter(brand_campaign_id=brand_campaign_id).first()
            if field_rep_user and campaign:
                FieldRepCampaign.objects.get_or_create(field_rep=field_rep_user, campaign=campaign)

        _sync_fieldrep_to_campaign_portal(
            brand_campaign_id=brand_campaign_id,
            email=email,
            field_id=field_id or "",
            first_name=first_name or "",
            last_name=last_name or "",
            raw_password=password or "",
        )

        redirect_url = "/share/fieldrep-login/"
        if brand_campaign_id:
            redirect_url += f"?campaign={brand_campaign_id}"
        return redirect(redirect_url)

    return render(request, "sharing_management/fieldrep_create_password.html", {
        "email": email,
        "security_questions": security_questions,
        "brand_campaign_id": brand_campaign_id,
    })


def fieldrep_login(request):
    brand_campaign_id = request.GET.get("campaign") or request.POST.get("campaign")

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user_id, field_id, user_email = authenticate_field_representative(email, password)

        # Fallback: portal user (kept)
        if not user_id:
            try:
                from user_management.models import User
                portal_user = User.objects.filter(email__iexact=email, role="field_rep", active=True).first()
                if portal_user and portal_user.check_password(password):
                    user_id = portal_user.id
                    field_id = portal_user.field_id or ""
                    user_email = portal_user.email
            except Exception:
                pass

        if not user_id:
            return render(request, "sharing_management/fieldrep_login.html", {
                "error": "Invalid email or password. Please try again.",
                "brand_campaign_id": brand_campaign_id,
            })

        # Clear google/auth keys (kept)
        google_session_keys = [
            "_auth_user_id", "_auth_user_backend", "_auth_user_hash",
            "user_id", "username", "email", "first_name", "last_name"
        ]
        for key in google_session_keys:
            request.session.pop(key, None)

        request.session["field_rep_id"] = user_id
        request.session["field_rep_email"] = user_email
        request.session["field_rep_field_id"] = field_id
        if brand_campaign_id:
            request.session["brand_campaign_id"] = brand_campaign_id

        # ✅ Prefilled flows removed → treat ALL reps the same here
        if brand_campaign_id:
            return redirect(f"/share/fieldrep-share-collateral/{brand_campaign_id}/")
        return redirect("fieldrep_share_collateral")

    return render(request, "sharing_management/fieldrep_login.html", {"brand_campaign_id": brand_campaign_id})


def fieldrep_forgot_password(request):
    if request.method == "POST":
        email = request.POST.get("email")
        security_answer = request.POST.get("security_answer")
        security_question_id = request.POST.get("security_question_id")

        if not security_answer:
            question_id, question_text = get_security_question_by_email(email)
            if question_id and question_text:
                return render(request, "sharing_management/fieldrep_forgot_password.html", {
                    "email": email,
                    "security_question": question_text,
                    "security_question_id": question_id,
                })
            return render(request, "sharing_management/fieldrep_forgot_password.html", {
                "error": "Email not found or no security question set.",
            })

        is_valid = validate_forgot_password(email, security_question_id, security_answer)
        if is_valid:
            return redirect(f"/share/fieldrep-reset-password/?email={email}")

        return render(request, "sharing_management/fieldrep_forgot_password.html", {
            "email": email,
            "security_question": request.POST.get("security_question"),
            "security_question_id": security_question_id,
            "error": "Invalid security answer. Please try again.",
        })

    return render(request, "sharing_management/fieldrep_forgot_password.html")


def fieldrep_reset_password(request):
    email = request.GET.get("email") or request.POST.get("email")
    if request.method == "POST":
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        if password != confirm_password:
            return render(request, "sharing_management/fieldrep_reset_password.html", {
                "email": email,
                "error": "Passwords do not match.",
            })

        success = reset_field_representative_password(email, password)
        if success:
            messages.success(request, "Password reset successfully! Please login with your new password.")
            return redirect("fieldrep_login")

        return render(request, "sharing_management/fieldrep_reset_password.html", {
            "email": email,
            "error": "Failed to reset password. Please try again.",
        })

    return render(request, "sharing_management/fieldrep_reset_password.html", {"email": email})


# ---------------------------------------------------------------------
# Field rep share collateral (kept)
# ---------------------------------------------------------------------
def fieldrep_share_collateral(request, brand_campaign_id=None):
    field_rep_id = request.session.get("field_rep_id")
    field_rep_email = request.session.get("field_rep_email")
    field_rep_field_id = request.session.get("field_rep_field_id")

    if brand_campaign_id is None:
        brand_campaign_id = request.session.get("brand_campaign_id") or request.GET.get("campaign") or request.GET.get("brand_campaign_id")

    if not field_rep_id:
        messages.error(request, "Please login first.")
        return redirect("fieldrep_login")

    fieldrep_user = get_or_create_fieldrep_user(field_rep_id, field_rep_email, field_rep_field_id)

    # Collaterals filtered by campaign dates + is_active
    collaterals_list = []
    try:
        from django.db.models import Q as _Q

        if brand_campaign_id:
            current_date = timezone.now().date()
            cc_links = CMCampaignCollateral.objects.filter(
                campaign__brand_campaign_id=brand_campaign_id
            ).filter(
                _Q(start_date__lte=current_date, end_date__gte=current_date) |
                _Q(start_date__isnull=True, end_date__isnull=True)
            ).select_related("collateral")

            collaterals = [link.collateral for link in cc_links if link.collateral and getattr(link.collateral, "is_active", False)]
        else:
            collaterals = Collateral.objects.none()

        for collateral in collaterals:
            short_link = find_or_create_short_link(collateral, fieldrep_user)
            collaterals_list.append({
                "id": collateral.id,
                "name": collateral.title,
                "description": collateral.description,
                "link": request.build_absolute_uri(f"/shortlinks/go/{short_link.short_code}/"),
            })
    except Exception as e:
        print(f"Error fetching collaterals: {e}")
        messages.error(request, "Error loading collaterals. Please try again.")
        collaterals_list = []

    # Doctors assigned to rep_user (if exists)
    doctors = []
    try:
        from user_management.models import User as UMUser
        rep_user = None
        if field_rep_field_id:
            rep_user = UMUser.objects.filter(field_id=field_rep_field_id, role="field_rep").first()
        if not rep_user and field_rep_email:
            rep_user = UMUser.objects.filter(email=field_rep_email, role="field_rep").first()
        if rep_user:
            doctors = Doctor.objects.filter(rep=rep_user).order_by("name")
    except Exception:
        doctors = []

    if request.method == "POST":
        # AJAX send
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.POST.get("ajax"):
            try:
                doctor_name = request.POST.get("doctor_name")
                doctor_whatsapp = request.POST.get("doctor_whatsapp")
                collateral_id = request.POST.get("collateral")
                if not collateral_id:
                    return JsonResponse({"success": False, "message": "Collateral ID is required"})

                collateral_id = int(collateral_id)
                selected_collateral = next((c for c in collaterals_list if c["id"] == collateral_id), None)
                if not selected_collateral or not doctor_whatsapp:
                    return JsonResponse({"success": False, "message": "Please provide all required information."})

                # Ensure doctor exists/assigned
                from user_management.models import User as UMUser
                rep_user = UMUser.objects.filter(field_id=field_rep_field_id, role="field_rep").first() or fieldrep_user
                if not rep_user:
                    return JsonResponse({"success": False, "message": "Unable to resolve field rep user"})

                doctor, _created = Doctor.objects.update_or_create(
                    rep=rep_user,
                    phone=doctor_whatsapp,
                    defaults={"name": doctor_name, "source": "manual"},
                )

                # Log share (existing helper may exist; if not, ShareLog fallback can be used)
                try:
                    from .utils.db_operations import log_manual_doctor_share
                    collateral_obj = Collateral.objects.get(id=collateral_id, is_active=True)
                    short_link = find_or_create_short_link(collateral_obj, fieldrep_user)

                    log_manual_doctor_share(
                        short_link_id=short_link.id,
                        field_rep_id=field_rep_id,
                        phone_e164=doctor_whatsapp,
                        collateral_id=collateral_id,
                    )
                except Exception:
                    pass

                message = get_brand_specific_message(
                    collateral_id,
                    selected_collateral["name"],
                    selected_collateral["link"],
                    brand_campaign_id=brand_campaign_id,
                )
                wa_url = f"https://wa.me/91{doctor_whatsapp}?text={urllib.parse.quote(message)}"

                return JsonResponse({
                    "success": True,
                    "message": f"Collateral shared successfully with {doctor_name}!",
                    "whatsapp_url": wa_url,
                    "doctor_id": doctor.id,
                })
            except Exception as e:
                return JsonResponse({"success": False, "message": f"Server error: {str(e)}"})

        # Non-AJAX fallback: just redirect to WA
        doctor_name = request.POST.get("doctor_name")
        doctor_whatsapp = request.POST.get("doctor_whatsapp")
        collateral_id = int(request.POST.get("collateral"))
        selected_collateral = next((c for c in collaterals_list if c["id"] == collateral_id), None)

        if selected_collateral and doctor_whatsapp:
            message = get_brand_specific_message(
                collateral_id,
                selected_collateral["name"],
                selected_collateral["link"],
                brand_campaign_id=brand_campaign_id,
            )
            wa_url = f"https://wa.me/91{doctor_whatsapp}?text={urllib.parse.quote(message)}"
            return redirect(wa_url)

        messages.error(request, "Please provide all required information.")
        return redirect("fieldrep_share_collateral")

    return render(request, "sharing_management/fieldrep_share_collateral.html", {
        "fieldrep_id": field_rep_field_id or "Unknown",
        "fieldrep_email": field_rep_email,
        "collaterals": collaterals_list,
        "brand_campaign_id": brand_campaign_id,
        "doctors": doctors,
    })


# ---------------------------------------------------------------------
# Fieldrep gmail login/share (kept; prefilled redirects removed)
# ---------------------------------------------------------------------
def fieldrep_gmail_login(request):
    brand_campaign_id = request.GET.get("brand_campaign_id") or request.GET.get("campaign")

    if request.method == "POST":
        if "register" in request.POST:
            messages.error(request, "Registration is not allowed from this login link. Please use the registration link.")
            return render(request, "sharing_management/fieldrep_gmail_login.html", {"brand_campaign_id": brand_campaign_id})

        field_id = (request.POST.get("field_id") or "").strip()
        gmail_id = (request.POST.get("gmail_id") or "").strip()
        brand_campaign_id = (request.POST.get("brand_campaign_id") or brand_campaign_id)

        if not field_id or not gmail_id:
            messages.error(request, "Please provide both Field ID and Gmail ID.")
            return render(request, "sharing_management/fieldrep_gmail_login.html", {"brand_campaign_id": brand_campaign_id})

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, field_id, email
                    FROM sharing_management_fieldrepresentative
                    WHERE field_id = %s AND email = %s AND is_active = 1
                    LIMIT 1
                """, [field_id, gmail_id])
                result = cursor.fetchone()

            if not result:
                messages.error(request, "Invalid Field ID or Gmail ID. Please check and try again.")
                return render(request, "sharing_management/fieldrep_gmail_login.html", {"brand_campaign_id": brand_campaign_id})

            user_id, field_id_db, email = result

            google_session_keys = [
                "_auth_user_id", "_auth_user_backend", "_auth_user_hash",
                "user_id", "username", "email", "first_name", "last_name",
            ]
            for key in google_session_keys:
                request.session.pop(key, None)

            request.session["field_rep_id"] = user_id
            request.session["field_rep_email"] = email
            request.session["field_rep_field_id"] = field_id_db

            messages.success(request, f"Welcome back, {field_id_db}!")

            # ✅ Prefilled flows removed → always go to the gmail share page
            if brand_campaign_id:
                return redirect(f"/share/fieldrep-gmail-share-collateral/?brand_campaign_id={brand_campaign_id}")
            return redirect("fieldrep_gmail_share_collateral")

        except Exception as e:
            print(f"Error in Gmail login: {e}")
            messages.error(request, "Login failed. Please try again.")

    return render(request, "sharing_management/fieldrep_gmail_login.html", {"brand_campaign_id": brand_campaign_id})


def fieldrep_gmail_share_collateral(request, brand_campaign_id=None):
    """
    Kept exactly as your current behavior: this page prepares a WhatsApp message (despite name).
    """
    import urllib.parse as _up

    field_rep_id = request.session.get("field_rep_id")
    field_rep_email = request.session.get("field_rep_email")
    field_rep_field_id = request.session.get("field_rep_field_id")

    if brand_campaign_id is None:
        brand_campaign_id = request.GET.get("brand_campaign_id")

    if not field_rep_id:
        messages.error(request, "Please login first.")
        return redirect("fieldrep_login")

    # Build collaterals list (mostly same logic)
    collaterals_list = []
    try:
        from collateral_management.models import Collateral as CMCollateral, CampaignCollateral as CMCampaignCollateral2
        from campaign_management.models import CampaignCollateral as CampaignMgmtCC
        from django.db.models import Q as _Q
        from user_management.models import User as UMUser

        collaterals = []

        if brand_campaign_id and brand_campaign_id != "all":
            current_date = timezone.now().date()

            cc_links = CampaignMgmtCC.objects.filter(
                campaign__brand_campaign_id=brand_campaign_id
            ).filter(
                _Q(start_date__lte=current_date, end_date__gte=current_date) |
                _Q(start_date__isnull=True, end_date__isnull=True)
            ).select_related("collateral", "campaign")
            campaign_collaterals = [link.collateral for link in cc_links if link.collateral]

            collateral_links = CMCampaignCollateral2.objects.filter(
                campaign__brand_campaign_id=brand_campaign_id,
                collateral__is_active=True,
            ).filter(
                _Q(start_date__lte=current_date, end_date__gte=current_date) |
                _Q(start_date__isnull=True, end_date__isnull=True)
            ).select_related("collateral", "campaign")
            collateral_collaterals = [link.collateral for link in collateral_links if link.collateral and getattr(link.collateral, "is_active", True)]

            collaterals = list({c.id: c for c in (campaign_collaterals + collateral_collaterals) if hasattr(c, "id")}.values())
        else:
            collaterals = CMCollateral.objects.filter(is_active=True).order_by("-created_at")

        # Rep user
        actual_user = None
        if field_rep_field_id:
            actual_user = UMUser.objects.filter(field_id=field_rep_field_id, role="field_rep").first()
        if not actual_user and field_rep_email:
            actual_user = UMUser.objects.filter(email=field_rep_email, role="field_rep").first()
        if not actual_user:
            # fallback: session id might be UMUser id
            try:
                actual_user = UMUser.objects.get(id=int(field_rep_id))
            except Exception:
                actual_user = None

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
            except Exception:
                continue
    except Exception as e:
        print(f"Error fetching collaterals: {e}")
        collaterals_list = []
        messages.error(request, "Error loading collaterals. Please try again.")

    # Assigned doctors + status (kept similar)
    from user_management.models import User as UMUser
    actual_user = None
    if field_rep_field_id:
        actual_user = UMUser.objects.filter(field_id=field_rep_field_id, role="field_rep").first()
    if not actual_user and field_rep_email:
        actual_user = UMUser.objects.filter(email=field_rep_email, role="field_rep").first()
    if not actual_user:
        try:
            actual_user = UMUser.objects.get(id=int(field_rep_id))
        except Exception:
            actual_user = None

    assigned_doctors = Doctor.objects.filter(rep=actual_user) if actual_user else Doctor.objects.none()

    selected_collateral_id = (request.GET.get("collateral") or "").strip()
    if not selected_collateral_id and collaterals_list:
        selected_collateral_id = str(collaterals_list[0]["id"])

    doctors_with_status = []
    six_days_ago = timezone.now() - timedelta(days=6)
    for doctor in assigned_doctors:
        status = "not_sent"
        if selected_collateral_id:
            phone_val = doctor.phone or ""
            phone_clean = phone_val.replace("+", "").replace(" ", "").replace("-", "")
            possible_ids = [phone_val]
            if phone_clean and len(phone_clean) == 10:
                possible_ids.extend([f"+91{phone_clean}", f"91{phone_clean}"])

            share_log = (
                ShareLog.objects.filter(
                    doctor_identifier__in=possible_ids,
                    collateral_id=selected_collateral_id,
                )
                .order_by("-share_timestamp")
                .first()
            )
            if share_log:
                engaged = CollateralTransaction.objects.filter(
                    field_rep_id=str(share_log.field_rep_id),
                    doctor_number=share_log.doctor_identifier,
                    collateral_id=share_log.collateral_id,
                    has_viewed=True,
                ).exists()
                if engaged:
                    status = "opened"
                else:
                    status = "reminder" if share_log.share_timestamp and share_log.share_timestamp < six_days_ago else "sent"

        doctors_with_status.append({
            "id": doctor.id,
            "name": doctor.name,
            "phone": doctor.phone,
            "status": status,
        })

    if request.method == "POST":
        doctor_id = request.POST.get("doctor_id")
        doctor_name = request.POST.get("doctor_name")
        doctor_whatsapp = request.POST.get("doctor_whatsapp")
        collateral_id_str = request.POST.get("collateral")

        if not collateral_id_str or not collateral_id_str.isdigit():
            messages.error(request, "Please select a valid collateral.")
            return redirect(request.path)

        collateral_id = int(collateral_id_str)
        selected_collateral = next((c for c in collaterals_list if c["id"] == collateral_id), None)
        if not selected_collateral:
            messages.error(request, "Selected collateral not found.")
            return redirect(request.path)

        # Manual entry (whatsapp)
        if doctor_name and doctor_whatsapp:
            phone_e164 = _normalize_phone_e164(doctor_whatsapp)
            if not phone_e164:
                messages.error(request, "Please enter a valid WhatsApp number.")
                return redirect(request.path)

            from user_management.models import User as UMUser
            rep_user = actual_user
            if not rep_user:
                rep_user = UMUser.objects.filter(username=f"field_rep_{field_rep_id}").first()
            if not rep_user:
                rep_user = UMUser.objects.create_user(
                    username=f"field_rep_{field_rep_id}",
                    email=field_rep_email or f"field_rep_{field_rep_id}@example.com",
                    password=UMUser.objects.make_random_password(),
                    role="field_rep",
                    field_id=field_rep_field_id or "",
                )

            # store doctor
            phone_last10 = re.sub(r"\D", "", phone_e164)[-10:]
            Doctor.objects.update_or_create(rep=rep_user, phone=phone_last10, defaults={"name": doctor_name})

            collateral_obj = Collateral.objects.get(id=collateral_id, is_active=True)
            short_link = find_or_create_short_link(collateral_obj, rep_user)

            # log share best effort
            try:
                from .utils.db_operations import log_manual_doctor_share
                log_manual_doctor_share(
                    short_link_id=short_link.id,
                    field_rep_id=rep_user.id,
                    phone_e164=phone_e164,
                    collateral_id=collateral_id,
                )
            except Exception:
                try:
                    ShareLog.objects.create(
                        short_link=short_link,
                        collateral=collateral_obj,
                        field_rep=rep_user,
                        doctor_identifier=phone_e164,
                        share_channel="WhatsApp",
                        share_timestamp=timezone.now(),
                        created_at=timezone.now(),
                        updated_at=timezone.now(),
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

    return render(request, "sharing_management/fieldrep_gmail_share_collateral.html", {
        "fieldrep_id": field_rep_field_id or "Unknown",
        "fieldrep_email": field_rep_email,
        "collaterals": collaterals_list,
        "brand_campaign_id": brand_campaign_id,
        "doctors": doctors_with_status,
        "selected_collateral_id": selected_collateral_id,
    })


# ---------------------------------------------------------------------
# Doctors list (kept)
# ---------------------------------------------------------------------
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
            doctor_statuses.append({
                "doctor": doctor,
                "status": status,
                "status_class": get_doctor_status_class(status),
                "status_text": get_doctor_status_text(status),
                "last_shared": ShareLog.objects.filter(
                    doctor_identifier=doctor.phone,
                    collateral=collateral,
                ).order_by("-share_timestamp").first(),
            })

    return render(request, "sharing_management/doctor_list.html", {
        "doctors": doctor_statuses if collateral else [],
        "collateral": collateral,
        "campaign": campaign,
        "all_collaterals": Collateral.objects.filter(is_active=True).order_by("-created_at"),
    })


# ---------------------------------------------------------------------
# Video tracking (kept)
# ---------------------------------------------------------------------
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


# ---------------------------------------------------------------------
# Debug + delete collateral (kept)
# ---------------------------------------------------------------------
def debug_collaterals(request):
    collaterals = Collateral.objects.all()[:20]
    UserModel = get_user_model()
    field_reps = UserModel.objects.filter(role="field_rep")[:10]

    html = "<h2>Debug Information</h2>"
    html += "<h3>Available Collaterals:</h3><ul>"
    for col in collaterals:
        html += f"<li>ID: {col.id}, Name: {getattr(col, 'item_name', 'N/A')}, Active: {col.is_active}</li>"
    html += "</ul>"

    html += "<h3>Available Field Reps:</h3><ul>"
    for rep in field_reps:
        html += f"<li>ID: {rep.id}, Email: {rep.email}</li>"
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
