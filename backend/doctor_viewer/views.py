import json
import math
import os

from django.conf import settings
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

# PDF processing imports
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

try:
    from pdf2image import convert_from_path
except ImportError:
    convert_from_path = None

from shortlink_management.models import ShortLink
from collateral_management.models import Collateral
from collateral_management.models import CampaignCollateral as CollateralCampaignLink
from .models import DoctorEngagement
from sharing_management.models import ShareLog
from sharing_management.services.transactions import (
    mark_downloaded_pdf,
    mark_pdf_progress,
    mark_viewed,
)

# ──────────────────────────────────────────────────────────────
# Safe page count helper – works with local + remote storage
# ──────────────────────────────────────────────────────────────
def _page_count(collateral: Collateral) -> int:
    """Return page count or 0 on any failure (S3, corrupt file…)."""
    if collateral.type != "pdf":
        return 0
    try:
        if collateral.file and hasattr(collateral.file, "path") and os.path.exists(collateral.file.path):
            return len(PyPDF2.PdfReader(collateral.file.path).pages)
        resp = collateral.file.open(mode="rb")
        return len(PyPDF2.PdfReader(resp).pages)
    except Exception:
        return 0


# ──────────────────────────────────────────────────────────────
# Safe file URL helper – avoids ValueError for missing files
# ──────────────────────────────────────────────────────────────
def _safe_absolute_file_url(request, file_field):
    """
    Return an absolute URL for a Django FileField/ImageField or None.

    Django raises ValueError when accessing `.url` on an empty FileField.
    Some collateral types (e.g., video-only) legitimately have no file,
    and that should not break the verification flow.
    """
    if not file_field:
        return None
    try:
        return request.build_absolute_uri(file_field.url)
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────
# GET  /view/<code>/   → render PDF or video template
# ──────────────────────────────────────────────────────────────
def resolve_view(request, code: str):
    short_link = get_object_or_404(ShortLink, short_code=code, is_active=True)
    collateral = short_link.get_collateral()
    if not collateral or not collateral.is_active:
        return render(request, "doctor_viewer/error.html", {"msg": "Collateral unavailable"})

    engagement = DoctorEngagement.objects.create(short_link=short_link)

    # Tiny, safe hook: mark transaction viewed if share_id is present
    share_id = request.GET.get("share_id") or request.GET.get("s")
    if share_id:
        try:
            sl = ShareLog.objects.get(id=share_id)
            mark_viewed(sl, sm_engagement_id=None)
        except ShareLog.DoesNotExist:
            pass
    else:
        try:
            sl = ShareLog.objects.filter(short_link=short_link).order_by("-share_timestamp").first()
            if sl:
                mark_viewed(sl, sm_engagement_id=None)
        except Exception:
            pass

    context = {
        "collateral": collateral,
        "engagement_id": engagement.id,
        "short_code": code,
    }
    return render(request, "doctor_viewer/view.html", context)


# ──────────────────────────────────────────────────────────────
# POST /view/log/        JSON body → update DoctorEngagement
# ──────────────────────────────────────────────────────────────
@csrf_exempt
def log_engagement(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    try:
        data = json.loads(request.body.decode())
        engagement_id = int(data["engagement_id"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return HttpResponseBadRequest("Invalid JSON")

    engagement = get_object_or_404(DoctorEngagement, id=engagement_id)
    collateral = engagement.short_link.get_collateral()

    engagement.last_page_scrolled = max(engagement.last_page_scrolled, data.get("last_page", 0))
    engagement.pdf_completed = engagement.pdf_completed or data.get("pdf_completed", False)
    engagement.video_watch_percentage = max(engagement.video_watch_percentage, data.get("video_pct", 0))

    pdf_total_pages = data.get("pdf_total_pages") or _page_count(collateral)
    if pdf_total_pages:
        last_page = engagement.last_page_scrolled
        if last_page == 0:
            engagement.status = 0
        elif last_page < pdf_total_pages:
            engagement.status = 1
        else:
            engagement.status = 2

    engagement.updated_at = timezone.now()
    engagement.save(
        update_fields=[
            "last_page_scrolled",
            "pdf_completed",
            "video_watch_percentage",
            "status",
            "updated_at",
        ]
    )

    # Tiny, safe hook: reflect PDF progress into CollateralTransaction
    share_id = request.GET.get("share_id") or request.POST.get("share_id") or request.session.get("share_id")
    if share_id:
        try:
            sl = ShareLog.objects.get(id=share_id)
            mark_pdf_progress(
                sl,
                last_page=engagement.last_page_scrolled,
                completed=bool(engagement.pdf_completed),
                dv_engagement_id=engagement.id,
            )
        except ShareLog.DoesNotExist:
            pass
    else:
        try:
            sl = ShareLog.objects.filter(short_link=engagement.short_link).order_by("-share_timestamp").first()
            if sl:
                mark_pdf_progress(
                    sl,
                    last_page=engagement.last_page_scrolled,
                    completed=bool(engagement.pdf_completed),
                    dv_engagement_id=engagement.id,
                )
        except Exception:
            pass

    return JsonResponse({"status": "ok"})


# ──────────────────────────────────────────────────────────────
# GET  /view/report/<code>/     → JSON report
# ──────────────────────────────────────────────────────────────
def doctor_report(request, code: str):
    short_link = get_object_or_404(ShortLink, short_code=code, is_active=True)
    qry = (
        DoctorEngagement.objects.filter(short_link=short_link).values(
            "id",
            "view_timestamp",
            "status",
            "last_page_scrolled",
            "pdf_completed",
            "video_watch_percentage",
        )
    )
    return JsonResponse(list(qry), safe=False)


def doctor_collateral_verify(request):
    """
    Verify doctor identity (via WhatsApp number) before showing collateral.

    Key change: preserve optional `share_id` end-to-end so opens can be tracked per
    doctor-share (ShareLog/CollateralTransaction), not per shortlink.
    """
    import re
    from django.contrib import messages

    def last10(phone):
        digits = re.sub(r"\D", "", phone or "")
        return digits[-10:] if len(digits) >= 10 else digits

    share_id = (request.GET.get("share_id") or request.POST.get("share_id") or "").strip() or None

    if request.method == "GET":
        short_link_id = request.GET.get("short_link_id")
        if not short_link_id:
            messages.error(request, "Invalid access. Missing short link ID.")
            return redirect("/")

        try:
            short_link_id_int = int(short_link_id)
            short_link = ShortLink.objects.get(id=short_link_id_int)
        except (ValueError, ShortLink.DoesNotExist):
            messages.error(request, "Invalid access. Short link not found.")
            return redirect("/")

        if short_link.resource_type != "collateral":
            messages.error(request, "Invalid access. Not a collateral link.")
            return redirect("/")

        try:
            collateral = Collateral.objects.get(id=short_link.resource_id)
        except Collateral.DoesNotExist:
            messages.error(request, "Collateral not found.")
            return redirect("/")

        preview_url = None
        if collateral.pdf_file:
            preview_url = collateral.pdf_file.url
        elif collateral.thumbnail:
            preview_url = collateral.thumbnail.url

        archive_required = False
        archive_download_url = None
        archive_format = None
        if collateral.archives.exists():
            archive = collateral.archives.first()
            archive_required = True
            archive_download_url = archive.file.url
            archive_format = archive.format.lower()

        context = {
            "short_link_id": short_link_id,
            "share_id": share_id,
            "collateral": collateral,
            "preview_url": preview_url,
            "archive_required": archive_required,
            "archive_download_url": archive_download_url,
            "archive_format": archive_format,
            "error_message": None,
            "otp_required": False,
        }
        return render(request, "doctor_viewer/doctor_collateral_verify.html", context)

    # POST (WhatsApp number verification)
    whatsapp_number = request.POST.get("whatsapp_number", "").strip()
    short_link_id = request.POST.get("short_link_id")
    share_id = (request.POST.get("share_id") or share_id or "").strip() or None

    if not whatsapp_number or not short_link_id:
        messages.error(request, "Please enter a valid WhatsApp number.")
        qs = f"?short_link_id={short_link_id}" if short_link_id else ""
        if share_id:
            qs += f"&share_id={share_id}"
        return redirect(request.path + qs)

    try:
        short_link_id_int = int(short_link_id)
        short_link = ShortLink.objects.get(id=short_link_id_int)
    except (ValueError, ShortLink.DoesNotExist):
        messages.error(request, "Invalid link.")
        return redirect("/")

    input_last10 = last10(whatsapp_number)

    matched_share_log = None

    # 1) If share_id provided, validate it belongs to this short_link and matches the doctor
    if share_id:
        try:
            sl = ShareLog.objects.filter(id=int(share_id), short_link_id=short_link_id_int).first()
        except (TypeError, ValueError):
            sl = None

        if sl and last10(sl.doctor_identifier) == input_last10:
            matched_share_log = sl

    # 2) Fallback: locate a ShareLog for this short_link that matches the doctor number
    if not matched_share_log:
        logs = (
            ShareLog.objects.filter(short_link_id=short_link_id_int)
            .exclude(doctor_identifier__isnull=True)
            .exclude(doctor_identifier="")
            .order_by("-share_timestamp")
        )
        for sl in logs:
            if last10(sl.doctor_identifier) == input_last10:
                matched_share_log = sl
                break

    if not matched_share_log:
        messages.error(request, "Invalid Field ID or WhatsApp number.")
        qs = f"?short_link_id={short_link_id_int}"
        if share_id:
            qs += f"&share_id={share_id}"
        return redirect(request.path + qs)

    doctor_identifier = matched_share_log.doctor_identifier  # usually +91XXXXXXXXXX

    # Grant access (existing behavior)
    from sharing_management.utils.db_operations import grant_download_access
    if not grant_download_access(short_link_id_int, doctor_phone=doctor_identifier):
        messages.error(request, "Failed to grant download access.")
        return redirect("/")

    # Mark viewed for correct ShareLog/CollateralTransaction (best effort)
    try:
        mark_viewed(matched_share_log, sm_engagement_id=None)
    except Exception:
        pass

    try:
        collateral = Collateral.objects.get(id=short_link.resource_id)
    except Collateral.DoesNotExist:
        messages.error(request, "Collateral not found.")
        return redirect("/")

    return render(request, "doctor_viewer/doctor_collateral_view.html", {"collateral": collateral, "short_link": short_link})


def doctor_collateral_view(request):
    """
    OTP-based verification flow (existing behavior preserved).
    """
    if request.method == "POST":
        whatsapp_number = request.POST.get("whatsapp_number")
        short_link_id = request.POST.get("short_link_id")
        otp = request.POST.get("otp")

        if whatsapp_number and short_link_id and otp:
            try:
                from django.contrib import messages
                from sharing_management.utils.db_operations import grant_download_access, verify_doctor_otp

                success, row_id = verify_doctor_otp(whatsapp_number, short_link_id, otp)

                if success:
                    grant_success = grant_download_access(short_link_id)

                    # best-effort mark download in ShareLog
                    try:
                        sl = ShareLog.objects.filter(short_link_id=short_link_id).order_by("-share_timestamp").first()
                        if sl:
                            mark_downloaded_pdf(sl)
                    except Exception:
                        pass

                    if grant_success:
                        short_link = get_object_or_404(ShortLink, id=short_link_id)
                        collateral = short_link.get_collateral()

                        if collateral:
                            share_id = request.GET.get("share_id") or request.GET.get("s") or request.POST.get("share_id")
                            if share_id:
                                try:
                                    sl = ShareLog.objects.get(id=share_id)
                                    mark_viewed(sl, sm_engagement_id=None)
                                except ShareLog.DoesNotExist:
                                    pass

                            # Build Archives list
                            campaign_id = None
                            if getattr(collateral, "campaign_id", None):
                                campaign_id = collateral.campaign_id
                            else:
                                link = (
                                    CollateralCampaignLink.objects.filter(collateral=collateral)
                                    .select_related("campaign")
                                    .first()
                                )
                                if link:
                                    campaign_id = link.campaign_id

                            archives = []
                            if campaign_id:
                                older_qs = (
                                    Collateral.objects.filter(
                                        campaign_id=campaign_id,
                                        is_active=True,
                                        upload_date__lt=collateral.upload_date,
                                    )
                                    .exclude(pk=collateral.pk)
                                    .order_by("-upload_date")
                                )

                                n_prev = older_qs.count()
                                limit = 3 if n_prev >= 3 else n_prev
                                older_items = list(older_qs[:limit])

                                for c in older_items:
                                    sl = (
                                        ShortLink.objects.filter(
                                            resource_type="collateral",
                                            resource_id=c.id,
                                            is_active=True,
                                        )
                                        .order_by("-date_created")
                                        .first()
                                    )
                                    archives.append({"obj": c, "short_code": sl.short_code if sl else None})

                            absolute_pdf_url = _safe_absolute_file_url(request, collateral.file)

                            return render(
                                request,
                                "doctor_viewer/doctor_collateral_view.html",
                                {
                                    "collateral": collateral,
                                    "short_link": short_link,
                                    "verified": True,
                                    "archives": archives,
                                    "absolute_pdf_url": absolute_pdf_url,
                                },
                            )

                        messages.error(request, "Collateral not found.")
                    else:
                        messages.error(request, "Error granting access.")
                else:
                    messages.error(request, "Invalid OTP. Please try again.")

            except Exception:
                from django.contrib import messages

                messages.error(request, "Error verifying OTP. Please try again.")
        else:
            from django.contrib import messages

            messages.error(request, "Please provide all required information.")

    return render(request, "doctor_viewer/doctor_collateral_verify.html")


def tracking_dashboard(request):
    """
    Comprehensive tracking dashboard showing all doctor engagement data
    """
    engagements = DoctorEngagement.objects.select_related("short_link").order_by("-view_timestamp")

    total_engagements = engagements.count()
    pdf_engagements = engagements.filter(pdf_completed=True).count()
    video_engagements = engagements.filter(video_watch_percentage__gte=90).count()

    collateral_stats = {}
    for engagement in engagements:
        collateral = engagement.short_link.get_collateral()
        if collateral:
            collateral_name = collateral.title if hasattr(collateral, "title") else str(collateral)

            if collateral_name not in collateral_stats:
                collateral_stats[collateral_name] = {
                    "pdf_completed": 0,
                    "video_completed": 0,
                    "total_views": 0,
                    "type": collateral.type if hasattr(collateral, "type") else "unknown",
                }

            collateral_stats[collateral_name]["total_views"] += 1
            if engagement.pdf_completed:
                collateral_stats[collateral_name]["pdf_completed"] += 1
            if engagement.video_watch_percentage >= 90:
                collateral_stats[collateral_name]["video_completed"] += 1

    recent_engagements = engagements[:50]

    context = {
        "total_engagements": total_engagements,
        "pdf_engagements": pdf_engagements,
        "video_engagements": video_engagements,
        "collateral_stats": collateral_stats,
        "recent_engagements": recent_engagements,
    }

    return render(request, "doctor_viewer/tracking_dashboard.html", context)
