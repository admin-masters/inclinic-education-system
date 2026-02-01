# doctor_viewer/views.py
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
from sharing_management.services.transactions import mark_video_event

# ──────────────────────────────────────────────────────────────
# Safe page count helper – works with local + remote storage
# ──────────────────────────────────────────────────────────────
def _page_count(collateral: Collateral) -> int:
    if not collateral:
        return 0

    if getattr(collateral, "type", None) not in ["pdf", "pdf_video"]:
        return 0

    if PyPDF2 is None:
        return 0

    try:
        if collateral.file and hasattr(collateral.file, "path") and os.path.exists(collateral.file.path):
            return len(PyPDF2.PdfReader(collateral.file.path).pages)

        if collateral.file:
            resp = collateral.file.open(mode="rb")
            return len(PyPDF2.PdfReader(resp).pages)

        return 0
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

    existing_engagement_id = request.session.get("dv_engagement_id")
    engagement = DoctorEngagement.objects.filter(id=existing_engagement_id).first() if existing_engagement_id else None

    if not engagement:
        engagement = DoctorEngagement.objects.create(short_link=short_link)
        request.session["dv_engagement_id"] = engagement.id

    # ---------------------------------------------------------
    # IMPORTANT: ShareLog model has ghost fields not in DB.
    # So DO NOT use ShareLog.objects.get()/filter().first() here.
    # ---------------------------------------------------------
    share_id = request.GET.get("share_id") or request.GET.get("s")

    sl = None
    try:
        if share_id:
            try:
                share_id_int = int(share_id)
            except Exception:
                share_id_int = None

            if share_id_int:
                rows = list(
                    ShareLog.objects.raw(
                        """
                        SELECT id, short_link_id, doctor_identifier, share_channel,
                               share_timestamp, collateral_id, field_rep_id, message_text
                        FROM sharing_management_sharelog
                        WHERE id = %s
                        LIMIT 1
                        """,
                        [share_id_int],
                    )
                )
                sl = rows[0] if rows else None

        if sl is None:
            rows = list(
                ShareLog.objects.raw(
                    """
                    SELECT id, short_link_id, doctor_identifier, share_channel,
                           share_timestamp, collateral_id, field_rep_id, message_text
                    FROM sharing_management_sharelog
                    WHERE short_link_id = %s
                    ORDER BY share_timestamp DESC, id DESC
                    LIMIT 1
                    """,
                    [short_link.id],
                )
            )
            sl = rows[0] if rows else None

        if sl:
            # Prevent Django from trying to lazy-load ghost DB columns later
            try:
                sl.__dict__["field_rep_email"] = ""
            except Exception:
                pass
            try:
                sl.__dict__["brand_campaign_id"] = ""
            except Exception:
                pass

            try:
                mark_viewed(sl, sm_engagement_id=None)
            except Exception as e:
                print("[VIEW DEBUG] mark_viewed failed:", e)

            request.session["share_id"] = sl.id

    except Exception as e:
        print("[VIEW DEBUG] ShareLog raw lookup failed:", e)

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

    old_last_page = int(engagement.last_page_scrolled or 0)
    old_pdf_completed = bool(engagement.pdf_completed)
    old_video_pct = int(engagement.video_watch_percentage or 0)
    old_status = int(engagement.status or 0)

    now = timezone.now()

    pdf_total_pages = 0
    try:
        pdf_total_pages = int(data.get("pdf_total_pages") or 0)
    except Exception:
        pdf_total_pages = 0

    if event == "pdf_download":
        engagement.pdf_completed = True

    elif event == "page_scroll":
        try:
            page_number = int(data.get("page_number") or 1)
        except Exception:
            page_number = 1
        if page_number < 1:
            page_number = 1

        engagement.last_page_scrolled = max(int(engagement.last_page_scrolled or 0), page_number)

        # Update status if total pages provided
        if pdf_total_pages > 0:
            half = (pdf_total_pages + 1) // 2
            last_page = int(engagement.last_page_scrolled or 0)

            if last_page <= 1:
                engagement.status = 0
            elif last_page >= pdf_total_pages:
                engagement.status = 2
            elif last_page >= half:
                engagement.status = 1
            else:
                engagement.status = 0

    elif event == "video_progress":
        try:
            pct = int(value)
        except Exception:
            pct = 0
        pct = max(0, min(100, pct))

        # bucket into 0/50/100
        if pct >= 100:
            pct = 100
        elif pct >= 50:
            pct = 50
        else:
            pct = 0

        engagement.video_watch_percentage = max(int(engagement.video_watch_percentage or 0), pct)

    engagement.updated_at = now
    engagement.save(update_fields=["last_page_scrolled", "pdf_completed", "video_watch_percentage", "status", "updated_at"])

    new_last_page = int(engagement.last_page_scrolled or 0)
    new_pdf_completed = bool(engagement.pdf_completed)
    new_video_pct = int(engagement.video_watch_percentage or 0)
    new_status = int(engagement.status or 0)

    if new_last_page != old_last_page:
        print(f"[TRACKING DEBUG] PDF last_page_scrolled changed: {old_last_page} -> {new_last_page} "
              f"(engagement_id={engagement.id}, share_id={share_id}, event={event})")

    if new_status != old_status:
        print(f"[TRACKING DEBUG] PDF status changed: {old_status} -> {new_status} "
              f"(engagement_id={engagement.id}, share_id={share_id})")

    if new_pdf_completed != old_pdf_completed:
        print(f"[TRACKING DEBUG] PDF downloaded changed: {old_pdf_completed} -> {new_pdf_completed} "
              f"(engagement_id={engagement.id}, share_id={share_id})")

    if new_video_pct != old_video_pct:
        print(f"[TRACKING DEBUG] Video % changed: {old_video_pct}% -> {new_video_pct}% "
              f"(engagement_id={engagement.id}, share_id={share_id})")

    # ---------------------------------------------------------
    # FIX: Load ShareLog WITHOUT selecting ghost DB columns.
    # ---------------------------------------------------------
    if share_id:
        try:
            try:
                share_id_int = int(share_id)
            except Exception:
                share_id_int = None

            if not share_id_int:
                print(f"[TRACKING DEBUG] share_id not int: {share_id}")
                return JsonResponse({"ok": True, "event": event})

            rows = list(
                ShareLog.objects.raw(
                    """
                    SELECT id, short_link_id, doctor_identifier, share_channel,
                           share_timestamp, collateral_id, field_rep_id, message_text
                    FROM sharing_management_sharelog
                    WHERE id = %s
                    LIMIT 1
                    """,
                    [share_id_int],
                )
            )
            sl = rows[0] if rows else None

            if not sl:
                print(f"[TRACKING DEBUG] ShareLog not found for share_id={share_id_int}")
                return JsonResponse({"ok": True, "event": event})

            # Prevent lazy-loading ghost fields
            try:
                sl.__dict__["field_rep_email"] = ""
            except Exception:
                pass

            # If your services try to read brand_campaign_id, set it here best-effort
            brand_campaign_id_val = ""
            try:
                if getattr(sl, "collateral_id", None):
                    link = (
                        CollateralCampaignLink.objects
                        .select_related("campaign")
                        .filter(collateral_id=sl.collateral_id)
                        .order_by("-id")
                        .first()
                    )
                    if link and getattr(link, "campaign", None):
                        brand_campaign_id_val = getattr(link.campaign, "brand_campaign_id", "") or ""
            except Exception as e:
                print("[TRACKING DEBUG] brand_campaign_id best-effort lookup failed:", e)

            try:
                sl.__dict__["brand_campaign_id"] = brand_campaign_id_val
            except Exception:
                pass

            # Now update dashboard/transactions
            try:
                mark_viewed(sl, sm_engagement_id=None)
            except Exception as e:
                print("[TRACKING DEBUG] mark_viewed failed:", e)

            try:
                mark_pdf_progress(
                    sl,
                    last_page=int(engagement.last_page_scrolled or 0),
                    completed=bool(engagement.pdf_completed),
                    dv_engagement_id=engagement.id,
                    total_pages=pdf_total_pages,
                )
                print("[TRACKING DEBUG] ✅ mark_pdf_progress called for share_id =", sl.id)
            except Exception as e:
                print("[TRACKING DEBUG] mark_pdf_progress failed:", e)

            if engagement.pdf_completed:
                try:
                    mark_downloaded_pdf(sl)
                    print("[TRACKING DEBUG] ✅ mark_downloaded_pdf called for share_id =", sl.id)
                except Exception as e:
                    print("[TRACKING DEBUG] mark_downloaded_pdf failed:", e)

            if event == "video_progress":
                try:
                    mark_video_event(
                        sl,
                        status=int(engagement.video_watch_percentage or 0),
                        percentage=int(engagement.video_watch_percentage or 0),
                        event_id=0,
                        when=timezone.now(),
                    )
                    print("[TRACKING DEBUG] ✅ mark_video_event called for share_id =", sl.id)
                except Exception as e:
                    print("[TRACKING DEBUG] mark_video_event failed:", e)

        except Exception as e:
            print("[TRACKING DEBUG] ERROR updating ShareLog/CollateralTransaction:", e)

    return JsonResponse({"ok": True, "event": event})



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
    from django.contrib import messages
    import re

    def last10(phone):
        digits = re.sub(r"\D", "", phone or "")
        return digits[-10:] if len(digits) >= 10 else digits

    # ─────────────────────────────────────────
    # GET: Render verification page with preview
    # ─────────────────────────────────────────
    if request.method == "GET":
        short_link_id = request.GET.get("short_link_id")
        try:
            short_link_id = int(short_link_id)
            short_link = get_object_or_404(ShortLink, id=short_link_id, is_active=True)
            collateral = short_link.get_collateral()

            if not collateral or not collateral.is_active:
                messages.error(request, "Collateral unavailable.")
                return render(request, "doctor_viewer/doctor_collateral_verify.html")

            # (keep your existing preview logic unchanged)
            pdf_preview_url = None
            pdf_preview_image = None

            if collateral.file:
                media_path = collateral.file.name
                file_path = os.path.join(settings.MEDIA_ROOT, media_path)
                pdf_preview_url = request.build_absolute_uri(f"{settings.MEDIA_URL}{media_path}")

                if os.path.exists(file_path):
                    img_data = None
                    if collateral.type == "pdf" and fitz:
                        try:
                            doc = fitz.open(file_path)
                            page = doc[0]
                            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                            img_data = pix.tobytes("png")
                            doc.close()
                        except Exception:
                            img_data = None

                    if img_data:
                        preview_dir = os.path.join(settings.MEDIA_ROOT, "previews")
                        os.makedirs(preview_dir, exist_ok=True)
                        preview_filename = f"preview_{collateral.id}.png"
                        preview_path = os.path.join(preview_dir, preview_filename)
                        with open(preview_path, "wb") as f:
                            f.write(img_data)
                        pdf_preview_image = f"{settings.MEDIA_URL}previews/{preview_filename}"

            video_preview_image = None
            if collateral.type in ["video", "pdf_video"] and collateral.vimeo_url:
                try:
                    import requests
                    vimeo_id = str(collateral.vimeo_url).strip()
                    if "vimeo.com" in vimeo_id:
                        if "/video/" in vimeo_id:
                            vimeo_id = vimeo_id.split("/video/")[-1].split("?")[0]
                        else:
                            vimeo_id = vimeo_id.strip("/").split("/")[-1]
                    vimeo_id = "".join(filter(str.isdigit, vimeo_id))
                    if vimeo_id:
                        thumbnail_url = f"https://vumbnail.com/{vimeo_id}.jpg"
                        response = requests.get(thumbnail_url, timeout=10)
                        if response.status_code == 200:
                            preview_dir = os.path.join(settings.MEDIA_ROOT, "previews")
                            os.makedirs(preview_dir, exist_ok=True)
                            video_preview_filename = f"video_preview_{collateral.id}.jpg"
                            video_preview_path = os.path.join(preview_dir, video_preview_filename)
                            with open(video_preview_path, "wb") as f:
                                f.write(response.content)
                            video_preview_image = f"{settings.MEDIA_URL}previews/{video_preview_filename}"
                except Exception as e:
                    print("[VERIFYDBG] video thumbnail error:", e)

            return render(request, "doctor_viewer/doctor_collateral_verify.html", {
                "short_link_id": short_link_id,
                "collateral": collateral,
                "pdf_preview_url": pdf_preview_url,
                "pdf_preview_image": pdf_preview_image,
                "video_preview_image": video_preview_image,
            })

        except Exception as e:
            print("[VERIFYDBG] GET verify error:", e)
            messages.error(request, "Invalid or expired access link.")
            return render(request, "doctor_viewer/doctor_collateral_verify.html")

    # ─────────────────────────────────────────
    # POST: Verify WhatsApp number
    # ─────────────────────────────────────────
    if request.method == "POST":
        whatsapp_number = (request.POST.get("whatsapp_number") or "").strip()
        short_link_id = request.POST.get("short_link_id")

        print("[VERIFYDBG] POST verify received")
        print(f"[VERIFYDBG] raw whatsapp_number='{whatsapp_number}' short_link_id='{short_link_id}'")

        try:
            short_link_id = int(short_link_id)
        except (TypeError, ValueError):
            messages.error(request, "Invalid access link.")
            return render(request, "doctor_viewer/doctor_collateral_verify.html")

        if not whatsapp_number:
            messages.error(request, "Please provide WhatsApp number.")
            return render(request, "doctor_viewer/doctor_collateral_verify.html")

        input_last10 = last10(whatsapp_number)
        print("[VERIFYDBG] input_last10 =", input_last10)

        matched = False
        matched_sharelog_id = None

        try:
            logs = list(
                ShareLog.objects.filter(short_link_id=short_link_id)
                .exclude(doctor_identifier__isnull=True)
                .exclude(doctor_identifier__exact="")
                .values("id", "doctor_identifier")
            )
            print(f"[VERIFYDBG] ShareLog rows for short_link_id={short_link_id}: count={len(logs)}")

            # Print up to 10 rows as last10 only (safe + useful)
            for row in logs[:10]:
                stored = row.get("doctor_identifier") or ""
                print(f"[VERIFYDBG] row id={row.get('id')} stored_last10={last10(stored)} stored_raw='{stored}'")

            for row in logs:
                stored = row.get("doctor_identifier") or ""
                if last10(stored) == input_last10:
                    matched = True
                    matched_sharelog_id = row["id"]
                    break

        except Exception as e:
            print("[VERIFYDBG] ERROR reading ShareLog:", e)

        print("[VERIFYDBG] verification matched =", matched, " matched_sharelog_id =", matched_sharelog_id)

        if not matched:
            messages.error(
                request,
                "WhatsApp number not found in our records. "
                "Please use the same number used to share this content."
            )
            return redirect(request.path + f"?short_link_id={short_link_id}")

        # Grant access
        from sharing_management.utils.db_operations import grant_download_access

        if not grant_download_access(short_link_id):
            messages.error(request, "Error granting access.")
            return redirect(request.path + f"?short_link_id={short_link_id}")

        short_link = get_object_or_404(ShortLink, id=short_link_id)
        collateral = short_link.get_collateral()

        request.session["share_id"] = matched_sharelog_id

        # (keep the rest of your existing “archives + engagement” logic unchanged)
        campaign_id = getattr(collateral, "campaign_id", None)
        if not campaign_id:
            link = (
                CollateralCampaignLink.objects
                .filter(collateral=collateral)
                .select_related("campaign")
                .first()
            )
            if link:
                campaign_id = link.campaign_id

        archives = []
        if campaign_id:
            older = (
                Collateral.objects.filter(
                    campaign_id=campaign_id,
                    is_active=True,
                    upload_date__lt=collateral.upload_date,
                )
                .exclude(pk=collateral.pk)
                .order_by("-upload_date")[:3]
            )

            for c in older:
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

        session_key = f"dv_engagement_id_{short_link_id}"
        existing_engagement_id = request.session.get(session_key)

        engagement = None
        if existing_engagement_id:
            engagement = DoctorEngagement.objects.filter(id=existing_engagement_id, short_link=short_link).first()

        if not engagement:
            engagement = DoctorEngagement.objects.create(short_link=short_link)
            request.session[session_key] = engagement.id

        print("[VERIFYDBG] ✅ access granted; engagement_id =", engagement.id)

        return render(request, "doctor_viewer/doctor_collateral_view.html", {
            "collateral": collateral,
            "short_link": short_link,
            "verified": True,
            "archives": archives,
            "absolute_pdf_url": absolute_pdf_url,
            "share_id": matched_sharelog_id,
            "engagement_id": engagement.id,
        })

def doctor_collateral_view(request):
    """
    OTP-based verification flow (existing behavior preserved).
    """
    from django.contrib import messages
    import re

    if request.method == "POST":
        whatsapp_number = request.POST.get("whatsapp_number")
        short_link_id = request.POST.get("short_link_id")
        otp = request.POST.get("otp")

        if whatsapp_number and short_link_id and otp:
            try:
                from sharing_management.utils.db_operations import grant_download_access, verify_doctor_otp

                success, row_id = verify_doctor_otp(whatsapp_number, short_link_id, otp)

                if not success:
                    messages.error(request, "Invalid OTP. Please try again.")
                    return render(request, "doctor_viewer/doctor_collateral_verify.html")

                grant_success = grant_download_access(short_link_id)
                if not grant_success:
                    messages.error(request, "Error granting access.")
                    return render(request, "doctor_viewer/doctor_collateral_verify.html")

                short_link = get_object_or_404(ShortLink, id=short_link_id)
                collateral = short_link.get_collateral()
                if not collateral:
                    messages.error(request, "Collateral not found.")
                    return render(request, "doctor_viewer/doctor_collateral_verify.html")

                # best-effort mark download in ShareLog (RAW, avoid ghost fields)
                try:
                    rows = list(
                        ShareLog.objects.raw(
                            """
                            SELECT id, short_link_id, doctor_identifier, share_channel,
                                   share_timestamp, collateral_id, field_rep_id, message_text
                            FROM sharing_management_sharelog
                            WHERE short_link_id = %s
                            ORDER BY share_timestamp DESC, id DESC
                            LIMIT 1
                            """,
                            [int(short_link_id)],
                        )
                    )
                    sl = rows[0] if rows else None
                    if sl:
                        try:
                            sl.__dict__["field_rep_email"] = ""
                        except Exception:
                            pass
                        try:
                            sl.__dict__["brand_campaign_id"] = ""
                        except Exception:
                            pass
                        mark_downloaded_pdf(sl)
                except Exception as e:
                    print("[OTP VIEW DEBUG] mark_downloaded_pdf failed:", e)

                # Archives (keep existing logic)
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
                        .order_by("-upload_date")[:3]
                    )
                    for c in older_qs:
                        sl2 = (
                            ShortLink.objects.filter(
                                resource_type="collateral",
                                resource_id=c.id,
                                is_active=True,
                            )
                            .order_by("-date_created")
                            .first()
                        )
                        archives.append({"obj": c, "short_code": sl2.short_code if sl2 else None})

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
                        "share_id": request.session.get("share_id"),
                    },
                )

            except Exception as e:
                print("[OTP VIEW DEBUG] ERROR:", e)
                messages.error(request, "Error verifying OTP. Please try again.")
        else:
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
