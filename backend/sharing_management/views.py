from __future__ import annotations

import csv
from urllib.parse import quote
import urllib.parse
import random
import string
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpResponse, HttpRequest
from django.shortcuts import render, redirect, get_object_or_404, reverse
from django.utils import timezone
from django.db import connection
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest
from django.contrib.auth import get_user_model, login
from django.contrib.auth.models import User  # Add this line

from .models import ShareLog, VideoTrackingLog, FieldRepresentative
from campaign_management.models import CampaignCollateral
from doctor_viewer.models import Doctor
from django.db.models import Max, Q, F, ExpressionWrapper, DateTimeField
from django.utils import timezone
from datetime import timedelta
from .decorators import field_rep_required
from .forms import (
    ShareForm,
    BulkManualShareForm,
    BulkPreMappedUploadForm,
    BulkManualWhatsappShareForm,
    BulkPreFilledWhatsappShareForm,
    BulkPreMappedByLoginForm,
)
from campaign_management.models import CampaignAssignment
from sharing_management.services.transactions import upsert_from_sharelog, mark_video_event
from collateral_management.models import Collateral
from collateral_management.models import CampaignCollateral as CMCampaignCollateral
from doctor_viewer.models import DoctorEngagement
from shortlink_management.models import ShortLink
from shortlink_management.utils import generate_short_code
from utils.recaptcha import recaptcha_required
from .forms import CollateralForm
from sharing_management.forms import CalendarCampaignCollateralForm
from .utils.db_operations import (
    register_field_representative, 
    validate_forgot_password, 
    get_security_question_by_email,
    authenticate_field_representative,
    authenticate_field_representative_direct,
    reset_field_representative_password,
    generate_and_store_otp,
    verify_otp
)
import random
import string
import re

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
        resource_type='collateral',
        resource_id=collateral.id,
        is_active=True
    ).first()
    if existing:
        return existing

    short_code = generate_short_code(length=8)
    return ShortLink.objects.create(
        short_code=short_code,
        resource_type='collateral',
        resource_id=collateral.id,
        created_by=user,
        date_created=timezone.now(),
        is_active=True
    )


def build_wa_link(share_log, request):
    if share_log.share_channel != "WhatsApp":
        return ""

    short_url = request.build_absolute_uri(
        f"/shortlinks/go/{share_log.short_link.short_code}/"
    )
    msg_text = (
        f"{share_log.message_text} {short_url}"
        if share_log.message_text
        else f"Hello Doctor, please check this: {short_url}"
    )
    return f"https://wa.me/{share_log.doctor_identifier}?text={quote(msg_text)}"

def get_brand_specific_message(collateral_id, collateral_name, collateral_link):
    """
    Get brand-specific message for a collateral, or fallback to default message.
    """
    from campaign_management.models import CampaignCollateral, CampaignMessage
    
    # Find the campaign for this collateral
    campaign_collateral = CampaignCollateral.objects.filter(collateral_id=collateral_id).first()
    
    if campaign_collateral and campaign_collateral.campaign:
        # Get the first active message for this campaign
        brand_message = CampaignMessage.objects.filter(
            campaign=campaign_collateral.campaign,
            is_active=True
        ).first()
        
        if brand_message:
            # Use brand-specific message
            message_text = brand_message.message_text
            # Replace placeholder with actual link
            message_text = message_text.replace('$collateralLinks', collateral_link)
            return message_text
    
    # Fallback to default message
    return f"Dear Doctor,%0A%0Aalkem testing brings you the following Practical Education topic from Indian Academy of Pediatrics%0A%0AThis IAP Education topic is {collateral_name}%0A%0APlease click on the link given below to view it:%0A{collateral_link}"


@field_rep_required
@recaptcha_required
def share_content(request):
    collateral_id = request.GET.get('collateral_id')
    initial = {}
    if collateral_id:
        initial['collateral'] = collateral_id
    brand_campaign_id = request.POST.get('brand_campaign_id') or brand_campaign_id
    if request.method == 'POST':
        form = ShareForm(request.POST)
        if form.is_valid():
            collateral = form.cleaned_data['collateral']
            doctor_contact = form.cleaned_data['doctor_contact'].strip()
            share_channel = form.cleaned_data['share_channel']
            message_text = form.cleaned_data['message_text']

            short_link = find_or_create_short_link(collateral, request.user)

            short_url = request.build_absolute_uri(
                f"/shortlinks/go/{short_link.short_code}/"
            )
            default_msg = f"Hello Doctor, please check this: {short_url}"
            full_msg = f"{message_text} {short_url}".strip() or default_msg

            try:
                if share_channel == "WhatsApp":
                    pass  # handled on frontend
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
                message_text=message_text
            )
            # Tiny, safe hook: upsert transaction row for this send
            try:
                upsert_from_sharelog(
                    share_log,
                    brand_campaign_id=str(brand_campaign_id),
                    doctor_name=None,
                    field_rep_unique_id=getattr(request.user, "employee_code", None),
                    sent_at=share_log.share_timestamp,
                )
            except Exception:
                pass

            return redirect("share_success", share_log_id=share_log.id)
    else:
        form = ShareForm(initial=initial)
        if collateral_id:
            form.fields['collateral'].widget.attrs['hidden'] = True

    return render(request, 'sharing_management/share_form.html', {'form': form})


@field_rep_required
def share_success(request, share_log_id):
    share_log = get_object_or_404(
        ShareLog, id=share_log_id, field_rep=request.user
    )
    wa_link = build_wa_link(share_log, request)
    return render(
        request,
        "sharing_management/share_success.html",
        {"share_log": share_log, "wa_link": wa_link},
    )


@field_rep_required
def list_share_logs(request):
    logs_list = ShareLog.objects.filter(field_rep=request.user).order_by('-share_timestamp')
    paginator = Paginator(logs_list, 10)
    page_number = request.GET.get("page")
    logs = paginator.get_page(page_number)

    return render(request, 'sharing_management/share_logs.html', {'logs': logs})


from django.views.decorators.cache import never_cache

@field_rep_required
@never_cache
def fieldrep_dashboard(request):
    rep = request.user
    assigned = CampaignAssignment.objects.filter(field_rep=rep).select_related('campaign')
    campaign_ids = [a.campaign_id for a in assigned]

    # Use collateral_management CampaignCollateral for mapping IDs
    share_cnts = ShareLog.objects.filter(
        field_rep=rep,
        short_link__resource_type='collateral',
        short_link__resource_id__in=CMCampaignCollateral.objects.filter(
            campaign_id__in=campaign_ids
        ).values_list('collateral_id', flat=True)
    ).values('short_link__resource_id').annotate(cnt=Count('id'))
    share_map = {r['short_link__resource_id']: r['cnt'] for r in share_cnts}

    pdf_cnts = DoctorEngagement.objects.filter(
        short_link__resource_type='collateral',
        last_page_scrolled__gt=0,
        short_link__resource_id__in=CMCampaignCollateral.objects.filter(
            campaign_id__in=campaign_ids
        ).values_list('collateral_id', flat=True)
    ).values('short_link__resource_id').annotate(cnt=Count('id'))
    pdf_map = {r['short_link__resource_id']: r['cnt'] for r in pdf_cnts}

    vid_cnts = DoctorEngagement.objects.filter(
        video_watch_percentage__gte=90,
        short_link__resource_type='collateral',
        short_link__resource_id__in=CMCampaignCollateral.objects.filter(
            campaign_id__in=campaign_ids
        ).values_list('collateral_id', flat=True)
    ).values('short_link__resource_id').annotate(cnt=Count('id'))
    vid_map = {r['short_link__resource_id']: r['cnt'] for r in vid_cnts}

    stats = []
    for a in assigned:
        campaign = a.campaign
        campaign_collaterals = CMCampaignCollateral.objects.filter(campaign=campaign)
        collateral_ids = [cc.collateral_id for cc in campaign_collaterals]

        shares = sum(share_map.get(cid, 0) for cid in collateral_ids)
        pdfs = sum(pdf_map.get(cid, 0) for cid in collateral_ids)
        videos = sum(vid_map.get(cid, 0) for cid in collateral_ids)

        stats.append({
            'campaign': campaign,
            'shares': shares,
            'pdfs': pdfs,
            'videos': videos,
        })

    # Handle campaign filtering from campaign portal
    campaign_filter = request.GET.get('campaign', '').strip()

    # Build list of collaterals via collateral_management CampaignCollateral
    if campaign_filter:
        # If a specific brand campaign ID is provided, show active collaterals for that campaign
        all_ccs = CMCampaignCollateral.objects.filter(
            campaign__brand_campaign_id=campaign_filter,
            collateral__is_active=True  # Only include active collaterals
        ).select_related('collateral', 'campaign')
    else:
        # Otherwise, default to active collaterals for campaigns assigned to this field rep
        all_ccs = CMCampaignCollateral.objects.filter(
            campaign_id__in=campaign_ids,
            collateral__is_active=True  # Only include active collaterals
        ).select_related('collateral', 'campaign')

    all_collaterals = [cc.collateral for cc in all_ccs]
    
    # Add search functionality
    search_query = request.GET.get('search', '').strip()
    if search_query:
        # Filter collaterals by brand campaign ID search
        filtered = []
        for c in all_collaterals:
            cc = CMCampaignCollateral.objects.filter(collateral=c).select_related('campaign').first()
            campaign = cc.campaign if cc else None
            brand_id = campaign.brand_campaign_id if campaign else ''
            if search_query and search_query.lower() not in brand_id.lower():
                continue
            filtered.append(c)
        all_collaterals = filtered
    
    collaterals = []
    # Map Edit Dates to collateral_management CampaignCollateral to align with edit_calendar view
    for c in all_collaterals:
        cc = CMCampaignCollateral.objects.filter(collateral=c).select_related('campaign').first()
        # Get campaign through collateral_management CampaignCollateral relationship
        campaign = cc.campaign if cc else None

        # Build best viewer URL: if both assets present, route to combined viewer
        has_pdf = bool(getattr(c, 'file', None))
        has_vid = bool(getattr(c, 'vimeo_url', ''))
        viewer_url = None
        if has_pdf and has_vid:
            try:
                from django.urls import reverse
                # Prefer shortlink if exists so tracking remains unchanged
                from shortlink_management.models import ShortLink
                sl = ShortLink.objects.filter(
                    resource_type='collateral',
                    resource_id=getattr(c, 'id', None),
                    is_active=True
                ).order_by('-date_created').first()
                if sl:
                    viewer_url = reverse('resolve_shortlink', args=[sl.short_code])
                else:
                    viewer_url = reverse('collateral_preview', args=[getattr(c, 'id', None)])
            except Exception:
                viewer_url = None

        # Construct correct PDF URL for production environment
        pdf_url = None
        if has_pdf and getattr(c, 'file', None):
            import os
            from django.urls import reverse
            filename = os.path.basename(c.file.name)
            try:
                pdf_url = request.build_absolute_uri(
                    reverse('serve_collateral_pdf', args=[filename])
                )
            except Exception as e:
                print(f"Error generating PDF URL in dashboard: {e}")
                # Fallback to manual URL construction
                pdf_url = request.build_absolute_uri(f'/collaterals/tmp/{filename}/')

        collaterals.append({
            'brand_id': campaign.brand_campaign_id if campaign else '',
            'item_name': getattr(c, 'title', ''),
            'description': getattr(c, 'description', ''),
            'url': viewer_url or (pdf_url if has_pdf else (getattr(c, 'vimeo_url', '') or '')),
            'has_both': has_pdf and has_vid,
            # Use collateral_management.Collateral id for Replace/Delete actions
            'id': getattr(c, 'id', None),
            # Use collateral_management CampaignCollateral id for Edit Dates button
            'campaign_collateral_id': cc.pk if cc else None,
        })
    
    # Get campaign_id from URL parameter or use campaign_filter
    campaign_id = request.GET.get('campaign', campaign_filter)
    
    response = render(request, 'sharing_management/fieldrep_dashboard.html', {
        'stats': stats, 
        'collaterals': collaterals,
        'search_query': search_query,
        'campaign_filter': campaign_filter,
        'brand_campaign_id': campaign_filter,  # For backward compatibility
        'campaign_id': campaign_id  # Pass campaign_id to template for field rep management
    })
    # Extra safety: ensure no caching on this page
    response['Cache-Control'] = 'no-store, no-cache, max-age=0, must-revalidate'
    response['Pragma'] = 'no-cache'
    return response


@field_rep_required
def fieldrep_campaign_detail(request, campaign_id):
    rep = request.user
    get_object_or_404(CampaignAssignment, field_rep=rep, campaign_id=campaign_id)

    ccols = CampaignCollateral.objects.filter(campaign_id=campaign_id).select_related('collateral')
    col_ids = [cc.collateral_id for cc in ccols]

    shares = ShareLog.objects.filter(
        field_rep=rep,
        short_link__resource_type='collateral',
        short_link__resource_id__in=col_ids
    ).select_related('short_link')

    doctor_map = {}
    for s in shares:
        cid = s.short_link.resource_id
        doctor_map.setdefault(cid, {})[s.doctor_identifier] = s.short_link

    engagements = DoctorEngagement.objects.filter(
        short_link__resource_id__in=col_ids,
        short_link__resource_type='collateral'
    ).select_related('short_link')

    engagement_map = {e.short_link_id: e for e in engagements}

    rows = []
    for cc in ccols:
        col = cc.collateral
        cid = col.id
        doctor_statuses = []
        for doctor, short_link in doctor_map.get(cid, {}).items():
            eng = engagement_map.get(short_link.id)
            status = 0
            detail = ''
            if col.type == 'pdf':
                if eng:
                    if eng.pdf_completed:
                        status = 2
                        detail = f"{eng.last_page_scrolled} (completed)"
                    elif eng.last_page_scrolled > 0:
                        status = 1
                        detail = f"{eng.last_page_scrolled} (partial)"
            elif col.type == 'video':
                if eng:
                    if eng.video_watch_percentage >= 90:
                        status = 2
                        detail = f"{eng.video_watch_percentage}% (completed)"
                    elif eng.video_watch_percentage > 0:
                        status = 1
                        detail = f"{eng.video_watch_percentage}% (partial)"
            doctor_statuses.append({
                'doctor': doctor,
                'status': status,
                'detail': detail,
            })
        rows.append({
            'collateral': col,
            'doctor_statuses': doctor_statuses,
        })

    return render(request, 'sharing_management/fieldrep_campaign_detail.html', {'rows': rows})


def bulk_manual_upload(request):
    if request.method == "POST":
        print(f"POST request received with files: {request.FILES}")
        
        # Simple test redirect first
        if 'test_redirect' in request.POST:
            messages.success(request, "Test redirect working!")
            return redirect("bulk_upload_success")
        
        form = BulkManualShareForm(request.POST, request.FILES)
        print(f"Form is valid: {form.is_valid()}")
        
        if form.is_valid():
            try:
                # Debug: Show CSV content
                csv_file = request.FILES['csv_file']
                csv_content = csv_file.read().decode('utf-8')
                print(f"CSV Content:\n{csv_content}")
                
                # Check what field reps actually exist
                from django.contrib.auth import get_user_model
                UserModel = get_user_model()
                existing_field_reps = UserModel.objects.filter(role="field_rep").values_list('email', flat=True)
                print(f"Existing field reps in database: {list(existing_field_reps)}")
                
                # Reset file pointer for form processing
                csv_file.seek(0)
                
                created, errors = form.save(user_request=request.user)
                print(f"Created: {created}, Errors: {errors}")
                
                if created and created > 0:
                    messages.success(request, f"Data is uploaded successfully. {created} rows imported successfully.")
                    print("Redirecting to bulk_upload_success")
                    return redirect("bulk_upload_success")
                else:
                    messages.warning(request, "No rows were created. Please check your CSV file format and data.")
                    if errors:
                        messages.info(request, f"Total errors found: {len(errors)}")
                        # Show available field reps in error message
                        if existing_field_reps:
                            messages.info(request, f"Available field rep emails: {', '.join(existing_field_reps)}")
                        else:
                            messages.error(request, "No field representatives found in database! Please create field rep users first.")
                    
                for err in errors:
                    messages.error(request, f"Error: {err}")
                    
            except Exception as e:
                print(f"Save error: {e}")
                messages.error(request, f"Upload failed: {str(e)}")
                
            return redirect("bulk_manual_upload")
        else:
            print(f"Form errors: {form.errors}")
            for field, field_errors in form.errors.items():
                for error in field_errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = BulkManualShareForm()

    return render(request, "sharing_management/bulk_manual_upload.html", {"form": form})


def bulk_upload_success(request):
    """
    Show recently uploaded data from bulk upload
    """
    from datetime import datetime, timedelta
    
    # Get recent ShareLog entries (last 1 hour) - show all recent uploads, not just current user's
    recent_time = timezone.now() - timedelta(hours=1)
    recent_uploads = ShareLog.objects.filter(
        created_at__gte=recent_time
    ).select_related('collateral', 'field_rep', 'short_link').order_by('-created_at')[:50]
    
    return render(request, "sharing_management/bulk_upload_success.html", {
        "recent_uploads": recent_uploads,
        "total_count": recent_uploads.count()
    })


def all_share_logs(request):
    """
    Show all share logs
    """
    share_logs = ShareLog.objects.all().select_related('collateral', 'field_rep', 'short_link').order_by('-created_at')[:100]
    
    return render(request, "sharing_management/all_share_logs.html", {
        "share_logs": share_logs,
        "total_count": share_logs.count()
    })


def bulk_template_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=bulk_manual_registration.csv"
    writer = csv.writer(response)
    # Header: Field Rep ID,Gmail ID
    writer.writerow(["Field Rep ID", "Gmail ID"])
    # Example row
    writer.writerow(["FR1234", "rep1@gmail.com"])
    return response


def bulk_upload_help(request):
    """
    Show available field reps and collaterals for CSV upload
    """
    from django.contrib.auth import get_user_model
    UserModel = get_user_model()
    
    # Get available field reps
    field_reps = UserModel.objects.filter(role="field_rep").values('id', 'email', 'username')
    
    # Get available collaterals
    collaterals = Collateral.objects.filter(is_active=True).values('id', 'title', 'description')
    
    return render(request, "sharing_management/bulk_upload_help.html", {
        "field_reps": field_reps,
        "collaterals": collaterals,
    })


def bulk_pre_mapped_upload(request):
    if request.method == "POST":
        form = BulkPreMappedUploadForm(request.POST, request.FILES)
        if form.is_valid():
            created, errors = form.save(admin_user=request.user)
            if created:
                messages.success(request, f"Data is uploaded successfully. {created} rows imported successfully.")
                return redirect("bulk_upload_success")
            for err in errors:
                messages.error(request, err)
            return redirect("bulk_pre_mapped_upload")
    else:
        form = BulkPreMappedUploadForm()
    return render(request, "sharing_management/bulk_premapped_upload.html", {"form": form})


def bulk_pre_mapped_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=premapped_doctors_registration.csv"
    writer = csv.writer(response)
    # Header: Doctor Name, Whatsapp Number, Field Rep ID
    writer.writerow(["Doctor Name", "Whatsapp Number", "Field Rep ID"])
    # Example row
    writer.writerow(["Dr Jane Doe", "+919999998888", "FR1234"])
    return response

# ─── Bulk manual (WhatsApp‑only) UI ──────────────────────────────────────────
def bulk_manual_upload_whatsapp(request):
    if request.method == "POST":
        form = BulkManualWhatsappShareForm(request.POST, request.FILES)
        if form.is_valid():
            created, errors = form.save(user_request=request.user)
            if created:
                messages.success(request, f"Data is uploaded successfully. {created} WhatsApp rows imported successfully.")
                return redirect("bulk_upload_success")
            for err in errors:
                messages.error(request, err)
            return redirect("bulk_manual_upload_whatsapp")
    else:
        form = BulkManualWhatsappShareForm()

    return render(
        request,
        "sharing_management/bulk_manual_upload_whatsapp.html",
        {"form": form},
    )


def bulk_whatsapp_template_csv(request):
    """
    Example CSV for WhatsApp-only bulk registration of field reps
    """
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=bulk_manual_whatsapp_registration.csv"
    writer = csv.writer(response)
    # Header: Field Rep ID, Field Rep Number
    writer.writerow(["Field Rep ID", "Field Rep Number"])
    # Example row
    writer.writerow(["FR1234", "+919876543210"])
    return response

def bulk_pre_filled_share_whatsapp(request):
    from .forms import BulkPreFilledWhatsappShareForm

    if request.method == "POST":
        form = BulkPreFilledWhatsappShareForm(request.POST, request.FILES)
        if form.is_valid():
            result = form.save(admin_user=request.user)
            if result["created"]:
                messages.success(request, f"Data is uploaded successfully. {result['created']} rows shared.")
                return redirect("bulk_upload_success")
            for err in result["errors"]:
                messages.error(request, err)
            return redirect("bulk_pre_filled_share_whatsapp")
    else:
        form = BulkPreFilledWhatsappShareForm()

    return render(request, "sharing_management/bulk_prefilled_whatsapp_upload.html", {"form": form})

def bulk_prefilled_whatsapp_template_csv(request):
    """
    Download CSV template for bulk prefilled doctors sharing by WhatsApp
    """
    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="bulk_prefilled_doctors_whatsapp.csv"'

    writer = csv.writer(response)
    # Header: Doctor Name, Whatsapp Number, Field Rep ID
    writer.writerow(["Doctor Name", "Whatsapp Number", "Field Rep ID"])
    # Example rows
    writer.writerow(['Dr. John Doe', '+919876543210', 'FR1234'])
    writer.writerow(['Dr. Jane Smith', '+919876543211', 'FR5678'])

    return response

def edit_collateral_dates(request, pk):
    collateral = get_object_or_404(Collateral, pk=pk)
    if request.method == 'POST':
        form = CollateralForm(request.POST, request.FILES, instance=collateral)
        if form.is_valid():
            form.save()
            return redirect('collateral_list')  # Adjust this to your correct redirect
    else:
        form = CollateralForm(instance=collateral)
    
    return render(request, 'collaterals/edit_collateral_dates.html', {'form': form, 'collateral': collateral})

def edit_campaign_calendar(request):
    from django.http import JsonResponse
    # Use bridging model aligned with collateral_management.Collateral
    from collateral_management.models import CampaignCollateral as CMCampaignCollateral
    # Ensure collateral_object is defined across all branches
    collateral_object = None
    
    # Optional filter by Brand Campaign ID
    brand_filter = request.GET.get('brand') or request.GET.get('campaign')
    if brand_filter:
        campaign_collaterals = CMCampaignCollateral.objects.select_related('campaign', 'collateral')\
            .filter(campaign__brand_campaign_id=brand_filter)
    else:
        campaign_collaterals = CMCampaignCollateral.objects.select_related('campaign', 'collateral').all()
    
    # Check if we're editing an existing record
    edit_id = request.GET.get('id')
    print(f"Edit ID from URL: {edit_id}")
    if edit_id:
        try:
            existing_record = CMCampaignCollateral.objects.get(id=edit_id)
            # Set collateral_object for template usage when editing existing record
            collateral_object = existing_record.collateral
            if request.method == 'POST':
                print(f"POST data: {request.POST}")
                form = CalendarCampaignCollateralForm(request.POST, instance=existing_record)
                print(f"Form is valid: {form.is_valid()}")
                if form.is_valid():
                    print(f"Form cleaned_data: {form.cleaned_data}")
                    saved_instance = form.save()
                    print(f"Saved instance: {saved_instance}")
                    print(f"Start date: {saved_instance.start_date}, End date: {saved_instance.end_date}")
                    # If AJAX, return JSON instead of redirect
                    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'id': saved_instance.id,
                            'brand_campaign_id': saved_instance.campaign.brand_campaign_id,
                            'collateral_id': saved_instance.collateral_id,
                            'collateral_name': str(saved_instance.collateral),
                            'start_date': saved_instance.start_date.strftime('%Y-%m-%d') if saved_instance.start_date else '',
                            'end_date': saved_instance.end_date.strftime('%Y-%m-%d') if saved_instance.end_date else ''
                        })
                    messages.success(request, 'Calendar dates updated successfully.')
                    return redirect(f'/share/edit-calendar/?id={edit_id}')
                else:
                    print(f"Form errors: {form.errors}")
                    # Add form errors to messages for debugging
                    for field, errors in form.errors.items():
                        for error in errors:
                            messages.error(request, f'{field}: {error}')
                    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'errors': form.errors}, status=400)
            else:
                form = CalendarCampaignCollateralForm(instance=existing_record)
        except CMCampaignCollateral.DoesNotExist:
            messages.error(request, 'Record not found.')
            return redirect('edit_campaign_calendar')
    else:
        # No ID provided - handle form submission to update existing records
        if request.method == 'POST':
            collateral_id = request.POST.get('collateral')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            brand_campaign_id = request.POST.get('campaign', '').strip()
            
            print(f"POST data - Collateral ID: {collateral_id}, Start: {start_date}, End: {end_date}")
            
            if collateral_id:
                # Find existing CampaignCollateral record with this collateral
                existing_qs = CMCampaignCollateral.objects.filter(collateral_id=collateral_id)
                # Prefer record within the selected brand campaign if provided
                if brand_campaign_id:
                    existing_qs = existing_qs.filter(campaign__brand_campaign_id=brand_campaign_id)
                existing_record = existing_qs.first()
                
                if existing_record:
                    # Update existing record
                    form = CalendarCampaignCollateralForm(request.POST, instance=existing_record)
                    if form.is_valid():
                        print(f"Updating existing record: {existing_record}")
                        saved_instance = form.save()
                        # If AJAX, return JSON success
                        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                            return JsonResponse({
                                'success': True,
                                'id': saved_instance.id,
                                'brand_campaign_id': saved_instance.campaign.brand_campaign_id,
                                'collateral_id': saved_instance.collateral_id,
                                'collateral_name': str(saved_instance.collateral),
                                'start_date': saved_instance.start_date.strftime('%Y-%m-%d') if saved_instance.start_date else '',
                                'end_date': saved_instance.end_date.strftime('%Y-%m-%d') if saved_instance.end_date else ''
                            })
                        messages.success(request, 'Calendar dates updated successfully!')
                        return redirect('edit_campaign_calendar')
                    else:
                        print(f"Form errors: {form.errors}")
                        for field, errors in form.errors.items():
                            for error in errors:
                                messages.error(request, f'{field}: {error}')
                        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                            return JsonResponse({'success': False, 'errors': form.errors}, status=400)
                else:
                    # Create new record - but we need to find the campaign from the brand_campaign_id
                    if brand_campaign_id:
                        from campaign_management.models import Campaign
                        try:
                            campaign = Campaign.objects.get(brand_campaign_id=brand_campaign_id)
                            form = CalendarCampaignCollateralForm(request.POST)
                            if form.is_valid():
                                instance = form.save(commit=False)
                                instance.campaign = campaign
                                instance.save()
                                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                                    return JsonResponse({
                                        'success': True,
                                        'id': instance.id,
                                        'brand_campaign_id': instance.campaign.brand_campaign_id,
                                        'collateral_id': instance.collateral_id,
                                        'collateral_name': str(instance.collateral),
                                        'start_date': instance.start_date.strftime('%Y-%m-%d') if instance.start_date else '',
                                        'end_date': instance.end_date.strftime('%Y-%m-%d') if instance.end_date else ''
                                    })
                                messages.success(request, 'New campaign collateral created successfully!')
                                return redirect('edit_campaign_calendar')
                            else:
                                print(f"Form errors: {form.errors}")
                                for field, errors in form.errors.items():
                                    for error in errors:
                                        messages.error(request, f'{field}: {error}')
                                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                                    return JsonResponse({'success': False, 'errors': form.errors}, status=400)
                        except Campaign.DoesNotExist:
                            messages.error(request, f'Campaign with Brand Campaign ID "{brand_campaign_id}" not found.')
                            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                                return JsonResponse({'success': False, 'error': 'Campaign not found.'}, status=404)
                    else:
                        messages.error(request, 'Brand Campaign ID is required to create a new campaign collateral.')
                        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                            return JsonResponse({'success': False, 'error': 'Brand Campaign ID is required.'}, status=400)
            else:
                messages.error(request, 'Please select a collateral.')
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Please select a collateral.'}, status=400)
        
        # Show form with optional initial values from query params
        initial = {}
        # Allow prefill via dashboard link fallback
        prefill_collateral_id = request.GET.get('collateral_id')
        prefill_brand = request.GET.get('brand') or request.GET.get('campaign')
        collateral_object = None
        if prefill_brand:
            initial['campaign'] = prefill_brand
        if prefill_collateral_id:
            try:
                collateral_object = Collateral.objects.get(id=prefill_collateral_id)
                initial['collateral'] = prefill_collateral_id
            except Collateral.DoesNotExist:
                pass
            # If there is an existing record, prefill dates too
            try:
                # Prefer record within the selected brand campaign if provided
                record_qs = CMCampaignCollateral.objects.filter(collateral_id=prefill_collateral_id)
                if prefill_brand:
                    record_qs = record_qs.filter(campaign__brand_campaign_id=prefill_brand)
                existing_record = record_qs.first()
                if existing_record:
                    if existing_record.start_date:
                        initial['start_date'] = existing_record.start_date.date()
                    if existing_record.end_date:
                        initial['end_date'] = existing_record.end_date.date()
            except Exception:
                pass
        
        # Initialize form with brand_campaign_id to filter collaterals
        form_kwargs = {'initial': initial}
        if prefill_brand:
            form_kwargs['brand_campaign_id'] = prefill_brand
        elif collateral_object and collateral_object.campaign_collaterals.exists():
            form_kwargs['brand_campaign_id'] = collateral_object.campaign_collaterals.first().campaign.brand_campaign_id
            
        form = CalendarCampaignCollateralForm(**form_kwargs)
    
    return render(request, 'sharing_management/edit_calendar.html', {
        'form': form,
        'campaign_collaterals': campaign_collaterals,
        'collateral': collateral_object,  # Pass collateral to template
        'title': 'Edit Calendar',
        'editing': bool(edit_id)
    })

def fieldrep_email_registration(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        # Redirect to password creation page with email as GET param
        return redirect(f'/share/fieldrep-create-password/?email={email}')
    return render(request, 'sharing_management/fieldrep_email_registration.html')

def fieldrep_create_password(request):
    email = request.GET.get('email') or request.POST.get('email')
    
    # Fetch security questions from database using Django ORM
    try:
        from .models import SecurityQuestion
        security_questions = SecurityQuestion.objects.all().values_list('id', 'question_txt')
    except Exception as e:
        print(f"Error fetching security questions: {e}")
        security_questions = []
    
    if request.method == 'POST':
        field_id = request.POST.get('field_id')
        whatsapp_number = request.POST.get('whatsapp_number', '').strip()
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        security_question_id = request.POST.get('security_question')
        security_answer = request.POST.get('security_answer')
        
        # Validate WhatsApp number if provided
        if whatsapp_number and not whatsapp_number.isdigit() or len(whatsapp_number) < 10 or len(whatsapp_number) > 15:
            return render(request, 'sharing_management/fieldrep_create_password.html', {
                'email': email,
                'security_questions': security_questions,
                'error': 'Please enter a valid WhatsApp number (10-15 digits).'
            })
        
        # Add password validation logic here if needed
        if password == confirm_password:
            # Use the new registration function with the specified placeholder style
            success = register_field_representative(
                field_id=field_id,
                email=email,
                whatsapp_number=whatsapp_number,
                password=password,
                security_question_id=security_question_id,
                security_answer=security_answer
            )
            
            if success:
                messages.success(request, 'Registration successful! Please login.')
                return redirect('fieldrep_login')
            else:
                return render(request, 'sharing_management/fieldrep_create_password.html', {
                    'email': email,
                    'security_questions': security_questions,
                    'error': 'Registration failed. Please try again.'
                })
        else:
            return render(request, 'sharing_management/fieldrep_create_password.html', {
                'email': email,
                'security_questions': security_questions,
                'error': 'Passwords do not match.'
            })
    
    return render(request, 'sharing_management/fieldrep_create_password.html', {
        'email': email,
        'security_questions': security_questions
    })

def fieldrep_login(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        # Authenticate using database
        user_id, field_id, user_email = authenticate_field_representative(email, password)
        
        if user_id:
            # Clear any existing Google authentication session
            # Remove Google auth related session keys
            google_session_keys = [
                '_auth_user_id', '_auth_user_backend', '_auth_user_hash',
                'user_id', 'username', 'email', 'first_name', 'last_name'
            ]
            
            for key in google_session_keys:
                if key in request.session:
                    del request.session[key]
            
            # Store field rep user info in session
            request.session['field_rep_id'] = user_id
            request.session['field_rep_email'] = user_email
            request.session['field_rep_field_id'] = field_id
            
            messages.success(request, f'Welcome back, {field_id}!')
            
            # Check if user is prefilled or manual based on field_id
            if field_id and field_id.startswith('PREFILLED_'):
                # Prefilled user - redirect to prefilled share collateral
                return redirect('prefilled_fieldrep_share_collateral')
            else:
                # Manual user - redirect to regular share collateral
                return redirect('fieldrep_share_collateral')
        else:
            return render(request, 'sharing_management/fieldrep_login.html', {
                'error': 'Invalid email or password. Please try again.'
            })
    
    return render(request, 'sharing_management/fieldrep_login.html')

def fieldrep_forgot_password(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        security_answer = request.POST.get('security_answer')
        security_question_id = request.POST.get('security_question_id')
        
        # Step 1: If no answer, show security question
        if not security_answer:
            # Get security question from database using email
            question_id, question_text = get_security_question_by_email(email)
            if question_id and question_text:
                return render(request, 'sharing_management/fieldrep_forgot_password.html', {
                    'email': email,
                    'security_question': question_text,
                    'security_question_id': question_id
                })
            else:
                return render(request, 'sharing_management/fieldrep_forgot_password.html', {
                    'error': 'Email not found or no security question set.'
                })
        else:
            # Use the new validation function with the specified placeholder style
            is_valid = validate_forgot_password(email, security_question_id, security_answer)
            if is_valid:
                return redirect(f'/share/fieldrep-reset-password/?email={email}')
            else:
                return render(request, 'sharing_management/fieldrep_forgot_password.html', {
                    'email': email,
                    'security_question': request.POST.get('security_question'),
                    'security_question_id': security_question_id,
                    'error': 'Invalid security answer. Please try again.'
                })
    return render(request, 'sharing_management/fieldrep_forgot_password.html')

def fieldrep_reset_password(request):
    email = request.GET.get('email') or request.POST.get('email')
    if request.method == 'POST':
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        
        if password == confirm_password:
            # Reset password in database
            success = reset_field_representative_password(email, password)
            if success:
                messages.success(request, 'Password reset successfully! Please login with your new password.')
                return redirect('fieldrep_login')
            else:
                return render(request, 'sharing_management/fieldrep_reset_password.html', {
                    'email': email,
                    'error': 'Failed to reset password. Please try again.'
                })
        else:
            return render(request, 'sharing_management/fieldrep_reset_password.html', {
                'email': email,
                'error': 'Passwords do not match.'
            })
    
    return render(request, 'sharing_management/fieldrep_reset_password.html', {'email': email})



def fieldrep_share_collateral(request, brand_campaign_id=None):
    # Get user info from session
    field_rep_id = request.session.get('field_rep_id')
    field_rep_email = request.session.get('field_rep_email')
    field_rep_field_id = request.session.get('field_rep_field_id')
    
    # If brand_campaign_id not provided in URL, try to get it from GET parameters
    if brand_campaign_id is None:
        brand_campaign_id = request.GET.get('brand_campaign_id')
    
    if not field_rep_id:
        messages.error(request, 'Please login first.')
        return redirect('fieldrep_login')
    
    # Get real collaterals from database
    try:
        from collateral_management.models import Collateral, CampaignCollateral as CMCampaignCollateral

        if brand_campaign_id:
            # Limit to collaterals linked to the given brand campaign
            cc_links = CMCampaignCollateral.objects.filter(campaign__brand_campaign_id=brand_campaign_id).select_related('collateral')
            collaterals = [link.collateral for link in cc_links if link.collateral]
        else:
            collaterals = Collateral.objects.filter(is_active=True)
        
        # Convert to list format for template
        collaterals_list = []
        for collateral in collaterals:
            # Create short link for each collateral
            short_link = find_or_create_short_link(collateral, request.user)
            collaterals_list.append({
                'id': collateral.id,
                'name': collateral.title,
                'description': collateral.description,
                'link': request.build_absolute_uri(f"/shortlinks/go/{short_link.short_code}/")
            })
    except Exception as e:
        print(f"Error fetching collaterals: {e}")
        collaterals_list = []
        messages.error(request, 'Error loading collaterals. Please try again.')
    
    if request.method == 'POST':
        doctor_name = request.POST.get('doctor_name')
        doctor_whatsapp = request.POST.get('doctor_whatsapp')
        collateral_id = int(request.POST.get('collateral'))

        # Find the selected collateral
        selected_collateral = next((c for c in collaterals_list if c['id'] == collateral_id), None)
        
        if selected_collateral and doctor_whatsapp:
            # Log the share in database
            try:
                from .utils.db_operations import log_manual_doctor_share
                # Get the short link for this collateral
                collateral_obj = Collateral.objects.get(id=collateral_id)
                short_link = find_or_create_short_link(collateral_obj, request.user)
                
                # Log the share
                log_manual_doctor_share(
                    short_link_id=short_link.id,
                    field_rep_id=field_rep_id,
                    phone_e164=doctor_whatsapp,
                    collateral_id=collateral_id
                )
                
                # Get brand-specific message
                message = get_brand_specific_message(collateral_id, selected_collateral['name'], selected_collateral['link'])
                wa_url = f"https://wa.me/91{doctor_whatsapp}?text={urllib.parse.quote(message)}"
                
                messages.success(request, f'Collateral shared successfully with {doctor_name}!')
                return redirect(wa_url)
                
            except Exception as e:
                print(f"Error logging share: {e}")
                messages.error(request, 'Error sharing collateral. Please try again.')
                return redirect('fieldrep_share_collateral')
        else:
            messages.error(request, 'Please provide all required information.')
            return redirect('fieldrep_share_collateral')
    
    return render(request, 'sharing_management/fieldrep_share_collateral.html', {
        'fieldrep_id': field_rep_field_id or 'Unknown',
        'fieldrep_email': field_rep_email,
        'collaterals': collaterals_list,
        'brand_campaign_id': brand_campaign_id,
    })

def prefilled_fieldrep_registration(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        # Redirect to password creation page with email as GET param
        return redirect(f'/share/prefilled-fieldrep-create-password/?email={email}')
    return render(request, 'sharing_management/prefilled_fieldrep_registration.html')

def prefilled_fieldrep_create_password(request):
    email = request.GET.get('email') or request.POST.get('email')
    # Generate a random password (10 chars, letters+digits)
    def generate_password(length=10):
        chars = string.ascii_letters + string.digits
        return ''.join(random.choices(chars, k=length))

    if request.method == 'POST':
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        # Accept system or custom password
        if not confirm_password or password == confirm_password:
            # Register user logic here
            try:
                from .utils.db_operations import register_field_representative
                
                # Check if user already exists
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT id FROM sharing_management_fieldrepresentative 
                        WHERE email = %s
                        LIMIT 1
                    """, [email])
                    existing_user = cursor.fetchone()
                
                if existing_user:
                    messages.success(request, 'User already exists! Please login with your credentials.')
                    return redirect('fieldrep_login')
                
                # Generate a unique field ID for prefilled user
                import time
                timestamp = int(time.time())
                field_id = f"PREFILLED_{email.split('@')[0].upper()}_{timestamp}"
                
                # Register the user
                success = register_field_representative(
                    field_id=field_id,
                    email=email,
                    password=password,
                    whatsapp_number=None,  # Will be set later
                    security_question_id=1,  # Default question
                    security_answer="prefilled_user"  # Default answer
                )
                
                if success:
                    
                    return redirect('fieldrep_login')
                else:
                    return render(request, 'sharing_management/prefilled_fieldrep_create_password.html', {
                        'email': email,
                        'password': password,
                        'error': 'Registration failed. Please try again.'
                    })
            except Exception as e:
                print(f"Error registering prefilled user: {e}")
                return render(request, 'sharing_management/prefilled_fieldrep_create_password.html', {
                    'email': email,
                    'password': password,
                    'error': 'Registration failed. Please try again.'
                })
        else:
            return render(request, 'sharing_management/prefilled_fieldrep_create_password.html', {
                'email': email,
                'password': password,
                'error': 'Passwords do not match.'
            })
    else:
        password = generate_password()
    return render(request, 'sharing_management/prefilled_fieldrep_create_password.html', {
        'email': email,
        'password': password
    })

def prefilled_fieldrep_share_collateral(request, brand_campaign_id=None):
    import urllib.parse
    
    # Get user info from session
    field_rep_id = request.session.get('field_rep_id')
    field_rep_email = request.session.get('field_rep_email')
    field_rep_field_id = request.session.get('field_rep_field_id')
    
    # Store brand_campaign_id in session if provided
    if brand_campaign_id:
        request.session['brand_campaign_id'] = brand_campaign_id
    else:
        # Try to get from session if not in URL
        brand_campaign_id = request.session.get('brand_campaign_id')
    
    if not field_rep_id:
        messages.error(request, 'Please login first.')
        return redirect('fieldrep_login')
    
    # Get doctors assigned to THIS field rep (from admin dashboard)
    try:
        from doctor_viewer.models import Doctor
        from user_management.models import User
        
        # Get the field rep user object by field_id (since field_rep_id is from FieldRepresentative table)
        field_rep_user = None
        if field_rep_field_id:
            try:
                field_rep_user = User.objects.get(field_id=field_rep_field_id, role='field_rep')
            except User.DoesNotExist:
                # Try to find by email/gmail as fallback
                if field_rep_email:
                    try:
                        field_rep_user = User.objects.filter(email=field_rep_email, role='field_rep').first()
                    except:
                        pass
        
        doctors_list = []
        if field_rep_user:
            # Fetch doctors assigned via admin dashboard (doctor_viewer_doctor table)
            assigned_doctors = Doctor.objects.filter(rep=field_rep_user)
            doctors_list = [
                {
                    'id': doc.id,
                    'name': doc.name,
                    'phone': doc.phone or '',
                    'email': '',  # Doctor model doesn't have email field
                    'specialty': '',
                    'city': '',
                }
                for doc in assigned_doctors
            ]
        
        # Also try to get prefilled doctors as fallback
        if not doctors_list:
            try:
                rep_pk, rep_field_id, rep_smg_id = _get_current_rep_ids(request)
                doctors_data = _fetch_assigned_prefilled_doctors(rep_pk, rep_field_id, rep_smg_id)
                doctors_list = [
                    {
                        'id': d[0],
                        'name': d[1],
                        'phone': d[2],
                        'email': d[3],
                        'specialty': d[4],
                        'city': d[5],
                    }
                    for d in doctors_data
                ]
            except Exception as e:
                pass
        
        if not doctors_list:
            messages.info(request, "No doctors are assigned to your account.")
    except Exception as e:
        doctors_list = []
        
    
    # Get real collaterals from database
    try:
        from collateral_management.models import Collateral
        from user_management.models import User
        
        collaterals = Collateral.objects.filter(is_active=True)
        
        # Get or create a user for this field rep (for short link creation)
        try:
            actual_user = User.objects.get(field_id=field_rep_field_id, role='field_rep')
        except User.DoesNotExist:
            # Try to get or create user by email
            if field_rep_email:
                actual_user, created = User.objects.get_or_create(
                    username=f"field_rep_{field_rep_id}",
                    defaults={
                        'email': field_rep_email,
                        'first_name': f"Field Rep {field_rep_field_id or field_rep_id}",
                        'role': 'field_rep'
                    }
                )
            else:
                actual_user = request.user if request.user.is_authenticated else None
        
        # Convert to list format for template
        collaterals_list = []
        for collateral in collaterals:
            try:
                # Create short link for each collateral
                short_link = find_or_create_short_link(collateral, actual_user)
                collaterals_list.append({
                    'id': collateral.id,
                    'name': collateral.title,
                    'description': collateral.description,
                    'link': request.build_absolute_uri(f"/shortlinks/go/{short_link.short_code}/")
                })
            except Exception as e:
                # Skip this collateral if there's an error
                continue
    except Exception as e:
        collaterals_list = []
        messages.error(request, 'Error loading collaterals. Please try again.')
    
    if request.method == 'POST':
        try:
            doctor_id_str = request.POST.get('doctor_id', '').strip()
            collateral_id_str = request.POST.get('collateral', '').strip()
            
            if not doctor_id_str or not collateral_id_str:
                messages.error(request, 'Please select both doctor and collateral.')
                return redirect('prefilled_fieldrep_share_collateral')
            
            doctor_id = int(doctor_id_str)
            collateral_id = int(collateral_id_str)
            
            # Find the selected doctor and collateral
            selected_doctor = next((d for d in doctors_list if d['id'] == doctor_id), None)
            selected_collateral = next((c for c in collaterals_list if c['id'] == collateral_id), None)
            
            if not selected_doctor:
                messages.error(request, f'Doctor with ID {doctor_id} not found. Please select a valid doctor.')
                return redirect('prefilled_fieldrep_share_collateral')
            
            if not selected_collateral:
                messages.error(request, f'Collateral with ID {collateral_id} not found. Please select a valid collateral.')
                return redirect('prefilled_fieldrep_share_collateral')
            
            # Now we know both exist, proceed with sharing
            try:
                from .utils.db_operations import share_prefilled_doctor
                from collateral_management.models import Collateral
                from user_management.models import User
                
                # Get or create a user for this field rep (for short link creation)
                try:
                    actual_user = User.objects.get(field_id=field_rep_field_id, role='field_rep')
                except User.DoesNotExist:
                    # Try to get or create user by email
                    if field_rep_email:
                        actual_user, created = User.objects.get_or_create(
                            username=f"field_rep_{field_rep_id}",
                            defaults={
                                'email': field_rep_email,
                                'first_name': f"Field Rep {field_rep_field_id or field_rep_id}",
                                'role': 'field_rep'
                            }
                        )
                    else:
                        actual_user = request.user if request.user.is_authenticated else None
                
                if not actual_user:
                    messages.error(request, 'Unable to create user for short link. Please try again.')
                    return redirect('prefilled_fieldrep_share_collateral')
                
                # Get the short link for this collateral
                collateral_obj = Collateral.objects.get(id=collateral_id)
                short_link = find_or_create_short_link(collateral_obj, actual_user)
                
                # Share the prefilled doctor (use actual_user.id instead of field_rep_id)
                success = share_prefilled_doctor(
                    rep_id=actual_user.id,  # Use User ID, not FieldRepresentative ID
                    prefilled_doctor_id=doctor_id,
                    short_link_id=short_link.id,
                    collateral_id=collateral_id
                )
                
                if success:
                    # Get brand-specific message
                    message = get_brand_specific_message(collateral_id, selected_collateral['name'], selected_collateral['link'])
                    # Clean phone number for WhatsApp URL (remove +91, +, spaces, etc.)
                    clean_phone = selected_doctor['phone'].replace('+91', '').replace('+', '').replace(' ', '').replace('-', '')
                    wa_url = f"https://wa.me/91{clean_phone}?text={urllib.parse.quote(message)}"
                    
                    messages.success(request, f'Collateral shared successfully with {selected_doctor["name"]}!')
                    return redirect(wa_url)
                else:
                    messages.error(request, 'Error sharing collateral. Please try again.')
                    return redirect('prefilled_fieldrep_share_collateral')
                    
            except Exception as e:
                messages.error(request, 'Error sharing collateral. Please try again.')
                return redirect('prefilled_fieldrep_share_collateral')
                
        except ValueError:
            messages.error(request, 'Invalid doctor or collateral ID. Please select valid options.')
            return redirect('prefilled_fieldrep_share_collateral')
        except Exception as e:
            messages.error(request, 'An error occurred. Please try again.')
            return redirect('prefilled_fieldrep_share_collateral')
    
    # Get assigned doctors for this field rep
    try:
        doctors_list = []
        # Your existing code to fetch doctors
        # ...
        
        if not doctors_list:
            messages.info(request, "No doctors are assigned to your account.")
    except Exception as e:
        doctors_list = []
        
    
    # Get real collaterals from database
    collaterals_list = []
    try:
        from collateral_management.models import Collateral
        from user_management.models import User
        
        collaterals = Collateral.objects.filter(is_active=True)
        
        # Get or create a user for this field rep (for short link creation)
        try:
            actual_user = User.objects.get(field_id=field_rep_field_id, role='field_rep')
        except User.DoesNotExist:
            # Try to get or create user by email
            if field_rep_email:
                actual_user, created = User.objects.get_or_create(
                    username=f"field_rep_{field_rep_id}",
                    defaults={
                        'email': field_rep_email,
                        'first_name': f"Field Rep {field_rep_field_id or field_rep_id}",
                        'role': 'field_rep'
                    }
                )
            else:
                actual_user = request.user if request.user.is_authenticated else None
        
        # Convert to list format for template
        for collateral in collaterals:
            try:
                # Create short link for each collateral
                short_link = find_or_create_short_link(collateral, actual_user)
                collaterals_list.append({
                    'id': collateral.id,
                    'name': collateral.title,
                    'description': collateral.description,
                    'link': request.build_absolute_uri(f"/shortlinks/go/{short_link.short_code}/")
                })
            except Exception as e:
                # Skip this collateral if there's an error
                continue
    except Exception as e:
        collaterals_list = []
        messages.error(request, 'Error loading collaterals. Please try again.')
    
    if request.method == 'POST':
        try:
            doctor_id_str = request.POST.get('doctor_id', '').strip()
            collateral_id_str = request.POST.get('collateral', '').strip()
            
            if not doctor_id_str or not collateral_id_str:
                messages.error(request, 'Please select both doctor and collateral.')
                return redirect('prefilled_fieldrep_share_collateral')
        
            doctor_id = int(doctor_id_str)
            collateral_id = int(collateral_id_str)
            
            # Find the selected doctor and collateral
            selected_doctor = next((d for d in doctors_list if d['id'] == doctor_id), None)
            selected_collateral = next((c for c in collaterals_list if c['id'] == collateral_id), None)
            
            if not selected_doctor:
                messages.error(request, f'Doctor with ID {doctor_id} not found. Please select a valid doctor.')
                return redirect('prefilled_fieldrep_share_collateral')
            
            if not selected_collateral:
                messages.error(request, f'Collateral with ID {collateral_id} not found. Please select a valid collateral.')
                return redirect('prefilled_fieldrep_share_collateral')
            
            # Now we know both exist, proceed with sharing
            try:
                from .utils.db_operations import share_prefilled_doctor
                from collateral_management.models import Collateral
                from user_management.models import User
                
                # Get or create a user for this field rep (for short link creation)
                try:
                    actual_user = User.objects.get(field_id=field_rep_field_id, role='field_rep')
                except User.DoesNotExist:
                    # Try to get or create user by email
                    if field_rep_email:
                        actual_user, created = User.objects.get_or_create(
                            username=f"field_rep_{field_rep_id}",
                            defaults={
                                'email': field_rep_email,
                                'first_name': f"Field Rep {field_rep_field_id or field_rep_id}",
                                'role': 'field_rep'
                            }
                        )
                    else:
                        actual_user = request.user if request.user.is_authenticated else None
                
                if not actual_user:
                    messages.error(request, 'Unable to create user for short link. Please try again.')
                    return redirect('prefilled_fieldrep_share_collateral')
            
                # Get the short link for this collateral
                collateral_obj = Collateral.objects.get(id=collateral_id)
                short_link = find_or_create_short_link(collateral_obj, actual_user)
                
                # Share the prefilled doctor (use actual_user.id instead of field_rep_id)
                success = share_prefilled_doctor(
                    rep_id=actual_user.id,  # Use User ID, not FieldRepresentative ID
                    prefilled_doctor_id=doctor_id,
                    short_link_id=short_link.id,
                    collateral_id=collateral_id
                )
                
                if success:
                    # Get brand-specific message
                    message = get_brand_specific_message(collateral_id, selected_collateral['name'], selected_collateral['link'])
                    # Clean phone number for WhatsApp URL (remove +91, +, spaces, etc.)
                    clean_phone = selected_doctor['phone'].replace('+91', '').replace('+', '').replace(' ', '').replace('-', '')
                    wa_url = f"https://wa.me/91{clean_phone}?text={urllib.parse.quote(message)}"
                    
                    messages.success(request, f'Collateral shared successfully with {selected_doctor["name"]}!')
                    return redirect(wa_url)
                else:
                    messages.error(request, 'Error sharing collateral. Please try again.')
                    return redirect('prefilled_fieldrep_share_collateral')
                        
            except Exception as e:
                messages.error(request, 'Error sharing collateral. Please try again.')
        except ValueError:
            messages.error(request, 'Invalid doctor or collateral ID. Please select valid options.')
            return redirect('prefilled_fieldrep_share_collateral')
        except Exception as e:
            messages.error(request, 'An error occurred. Please try again.')
            return redirect('prefilled_fieldrep_share_collateral')
    
    # This is the response for GET requests or if no POST data was submitted
    return render(request, 'sharing_management/prefilled_fieldrep_share_collateral.html', {
        'fieldrep_id': field_rep_field_id or 'Unknown',
        'fieldrep_email': field_rep_email,
        'doctors': doctors_list,
        'collaterals': collaterals_list
    })

def fieldrep_gmail_login(request):
    # Get brand_campaign_id from GET parameters if it exists (support both 'brand_campaign_id' and 'campaign' parameters)
    brand_campaign_id = request.GET.get('brand_campaign_id') or request.GET.get('campaign')
    
    if request.method == 'POST':
        field_id = request.POST.get('field_id')
        gmail_id = request.POST.get('gmail_id')
        action = request.POST.get('action')  # Get which button was clicked
        
        # Get brand_campaign_id from POST if it exists (in case it was submitted via form)
        brand_campaign_id = request.POST.get('brand_campaign_id', brand_campaign_id)
        
        # Build redirect URL with brand_campaign_id if it exists
        redirect_params = f'?brand_campaign_id={brand_campaign_id}' if brand_campaign_id else ''
        
        # Check if Register button was clicked
        if 'register' in request.POST:
            # Redirect to registration flow with email and brand_campaign_id
            if gmail_id:
                register_url = f'/share/fieldrep-create-password/?email={gmail_id}'
                if brand_campaign_id:
                    register_url += f'&brand_campaign_id={brand_campaign_id}'
                return redirect(register_url)
            else:
                messages.error(request, 'Please provide Gmail ID to register.')
                return render(request, 'sharing_management/fieldrep_gmail_login.html', {'brand_campaign_id': brand_campaign_id})
        
        # Handle Login
        if field_id and gmail_id:
            # Look up user by field_id and email (gmail_id)
            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, field_id, email, is_active
                        FROM sharing_management_fieldrepresentative
                        WHERE field_id = %s AND email = %s AND is_active = 1
                        LIMIT 1
                    """, [field_id, gmail_id])
                    
                    result = cursor.fetchone()
                    if result:
                        user_id, field_id, email, is_active = result
                        
                        # Clear any existing Google authentication session
                        google_session_keys = [
                            '_auth_user_id', '_auth_user_backend', '_auth_user_hash',
                            'user_id', 'username', 'email', 'first_name', 'last_name'
                        ]
                        
                        for key in google_session_keys:
                            if key in request.session:
                                del request.session[key]
                        
                        # Store field rep user info in session
                        request.session['field_rep_id'] = user_id
                        request.session['field_rep_email'] = email
                        request.session['field_rep_field_id'] = field_id
                        
                        messages.success(request, f'Welcome back, {field_id}!')
                        
                        # Check if user is prefilled or manual based on field_id
                        if field_id and field_id.startswith('PREFILLED_'):
                            # Prefilled user - redirect to prefilled share collateral with brand_campaign_id
                            if brand_campaign_id:
                                return redirect(f'/share/prefilled-fieldrep-share-collateral/?brand_campaign_id={brand_campaign_id}')
                            return redirect('prefilled_fieldrep_share_collateral')
                        else:
                            # Manual user - redirect to gmail share collateral with brand_campaign_id
                            if brand_campaign_id:
                                return redirect(f'/share/fieldrep-gmail-share-collateral/?brand_campaign_id={brand_campaign_id}')
                            return redirect('fieldrep_gmail_share_collateral')
                    else:
                        messages.error(request, 'Invalid Field ID or Gmail ID. Please check and try again.')
            except Exception as e:
                print(f"Error in Gmail login: {e}")
                messages.error(request, 'Login failed. Please try again.')
        else:
            messages.error(request, 'Please provide both Field ID and Gmail ID.')
    
    return render(request, 'sharing_management/fieldrep_gmail_login.html')

def fieldrep_gmail_share_collateral(request, brand_campaign_id=None):
    import urllib.parse

    # Get user info from session
    field_rep_id = request.session.get('field_rep_id')
    field_rep_email = request.session.get('field_rep_email')
    field_rep_field_id = request.session.get('field_rep_field_id')
    
    # If brand_campaign_id not provided in URL, try to get it from GET parameters
    if brand_campaign_id is None:
        brand_campaign_id = request.GET.get('brand_campaign_id')
    
    if not field_rep_id:
        messages.error(request, 'Please login first.')
        return redirect('fieldrep_login')
    
    # Get real collaterals from database
    try:
        from collateral_management.models import Collateral, CampaignCollateral as CMCampaignCollateral
        from campaign_management.models import CampaignCollateral as CMCampaignCollateral2

        # Initialize empty list for collaterals
        collaterals = []
        
        if brand_campaign_id and brand_campaign_id != 'all':
            print(f"[DEBUG] Filtering collaterals for brand_campaign_id: {brand_campaign_id}")
            
            # First from campaign_management.CampaignCollateral
            cc_links = CMCampaignCollateral2.objects.filter(
                campaign__brand_campaign_id=brand_campaign_id
            ).select_related('collateral', 'campaign')
            campaign_collaterals = [link.collateral for link in cc_links if link.collateral and getattr(link.collateral, 'is_active', True)]
            
            # Then from collateral_management.CampaignCollateral
            collateral_links = CMCampaignCollateral.objects.filter(
                campaign__brand_campaign_id=brand_campaign_id
            ).select_related('collateral', 'campaign')
            collateral_collaterals = [link.collateral for link in collateral_links if link.collateral and getattr(link.collateral, 'is_active', True)]
            
            # Combine and deduplicate collaterals
            collaterals = list({c.id: c for c in campaign_collaterals + collateral_collaterals if hasattr(c, 'id')}.values())
            
            if not collaterals:
                messages.info(request, f"No collaterals found for campaign {brand_campaign_id}")
        else:
            # Show all active collaterals if no brand campaign ID provided
            collaterals = Collateral.objects.filter(is_active=True).order_by('-created_at')
            messages.info(request, "Showing all available collaterals as no specific campaign is selected.")
        
        # Convert to list format for template
        collaterals_list = []
        
        # Get or create a user for this field rep
        from user_management.models import User
        try:
            user = User.objects.get(username=f"field_rep_{field_rep_id}")
        except User.DoesNotExist:
            user = User.objects.create_user(
                username=f"field_rep_{field_rep_id}",
                email=field_rep_email or f"field_rep_{field_rep_id}@example.com",
                first_name=f"Field Rep {field_rep_id}",
                password=User.objects.make_random_password()
            )
        
        for collateral in collaterals:
            try:
                short_link = find_or_create_short_link(collateral, user)
                collaterals_list.append({
                    'id': collateral.id,
                    'name': getattr(collateral, 'title', getattr(collateral, 'name', 'Untitled')),
                    'description': getattr(collateral, 'description', ''),
                    'link': request.build_absolute_uri(f"/shortlinks/go/{short_link.short_code}/")
                })
            except Exception as e:
                print(f"Error creating short link for collateral {getattr(collateral, 'id', 'unknown')}: {e}")
                continue
    except Exception as e:
        print(f"Error fetching collaterals: {e}")
        collaterals_list = []
        messages.error(request, 'Error loading collaterals. Please try again.')
    
    if request.method == 'POST':
        doctor_id = request.POST.get('doctor_id')
        doctor_name = request.POST.get('doctor_name')
        doctor_whatsapp = request.POST.get('doctor_whatsapp')

        # Get and validate collateral_id
        collateral_id_str = request.POST.get('collateral')
        if not collateral_id_str or not collateral_id_str.isdigit():
            messages.error(request, 'Please select a valid collateral.')
            # Preserve campaign and selection on redirect
            redirect_url = request.path
            params = []
            if brand_campaign_id:
                params.append(f"brand_campaign_id={brand_campaign_id}")
            if collateral_id_str:
                params.append(f"collateral={collateral_id_str}")
            if params:
                redirect_url = f"{redirect_url}?{'&'.join(params)}"
            return redirect(redirect_url)

        collateral_id = int(collateral_id_str)

        # Find the selected collateral
        selected_collateral = next((c for c in collaterals_list if c['id'] == collateral_id), None)
        if not selected_collateral:
            messages.error(request, 'Selected collateral not found.')
            redirect_url = request.path
            params = []
            if brand_campaign_id:
                params.append(f"brand_campaign_id={brand_campaign_id}")
            params.append(f"collateral={collateral_id}")
            if params:
                redirect_url = f"{redirect_url}?{'&'.join(params)}"
            return redirect(redirect_url)

        # Branch A: assigned doctor from list
        if doctor_id:
            try:
                from doctor_viewer.models import Doctor
                from collateral_management.models import Collateral
                from .utils.db_operations import log_manual_doctor_share
                from user_management.models import User

                # Handle both numeric and field_rep_* formatted IDs
                if isinstance(doctor_id, str) and doctor_id.startswith('field_rep_'):
                    try:
                        # Extract the numeric part after 'field_rep_'
                        rep_id = int(doctor_id.split('_')[-1])
                        # Find the doctor associated with this field rep
                        doc = Doctor.objects.filter(rep_id=rep_id).first()
                    except (ValueError, IndexError):
                        messages.error(request, 'Invalid doctor ID format')
                        return redirect(request.path)
                else:
                    # Handle numeric ID case
                    try:
                        doc_pk = int(doctor_id)
                        doc = Doctor.objects.filter(pk=doc_pk).first()
                    except (ValueError, TypeError):
                        messages.error(request, 'Invalid doctor ID')
                        return redirect(request.path)
                
                if not doc:
                    messages.error(request, 'Doctor not found')
                    return redirect(request.path)
                
                field_rep_user = None
                # Safely resolve by numeric id only if applicable
                if isinstance(field_rep_id, int):
                    field_rep_user = User.objects.filter(id=field_rep_id).first()
                elif isinstance(field_rep_id, str) and field_rep_id.isdigit():
                    field_rep_user = User.objects.filter(id=int(field_rep_id)).first()
                # Fallback to username pattern
                if not field_rep_user:
                    field_rep_user = User.objects.filter(username=f"field_rep_{field_rep_id}").first()
                if not field_rep_user:
                    field_rep_user = User.objects.create_user(
                        username=f"field_rep_{field_rep_id}",
                        email=field_rep_email or f"field_rep_{field_rep_id}@example.com",
                        first_name=f"Field Rep {field_rep_id}",
                        password=User.objects.make_random_password()
                    )

                collateral_obj = Collateral.objects.get(id=collateral_id)
                short_link = find_or_create_short_link(collateral_obj, field_rep_user)

                success = log_manual_doctor_share(
                    short_link_id=short_link.id,
                    field_rep_id=field_rep_id,
                    phone_e164=doc.phone or '',
                    collateral_id=collateral_id
                )

                if success:
                    message = get_brand_specific_message(collateral_id, selected_collateral['name'], selected_collateral['link'])
                    clean_phone = (doc.phone or '').replace('+91', '').replace('+', '').replace(' ', '').replace('-', '')
                    wa_url = f"https://wa.me/91{clean_phone}?text={urllib.parse.quote(message)}"
                    messages.success(request, f"Message prepared for {doc.name}. Redirecting to WhatsApp…")
                    return redirect(wa_url)
                else:
                    messages.error(request, 'Error sharing collateral. Please try again.')
                    redirect_url = request.path
                    params = []
                    if brand_campaign_id:
                        params.append(f"brand_campaign_id={brand_campaign_id}")
                    params.append(f"collateral={collateral_id}")
                    if params:
                        redirect_url = f"{redirect_url}?{'&'.join(params)}"
                    return redirect(redirect_url)
            except Exception as e:
                print(f"Error sharing to assigned doctor: {e}")
                import traceback; traceback.print_exc()
                messages.error(request, 'An error occurred while preparing WhatsApp message.')
                redirect_url = request.path
                params = []
                if brand_campaign_id:
                    params.append(f"brand_campaign_id={brand_campaign_id}")
                params.append(f"collateral={collateral_id}")
                if params:
                    redirect_url = f"{redirect_url}?{'&'.join(params)}"
                return redirect(redirect_url)

        # Branch B: manual entry from form
        if selected_collateral and doctor_name and doctor_whatsapp:
            try:
                from .utils.db_operations import log_manual_doctor_share
                from collateral_management.models import Collateral
                from doctor_viewer.models import Doctor
                from user_management.models import User

                # Resolve actual field rep user robustly
                field_rep_user = User.objects.filter(id=field_rep_id).first()
                if not field_rep_user:
                    field_rep_user = User.objects.filter(username=f"field_rep_{field_rep_id}").first()
                if not field_rep_user:
                    field_rep_user = User.objects.create_user(
                        username=f"field_rep_{field_rep_id}",
                        email=field_rep_email or f"field_rep_{field_rep_id}@example.com",
                        first_name=f"Field Rep {field_rep_id}",
                        password=User.objects.make_random_password()
                    )
                collateral_obj = Collateral.objects.get(id=collateral_id)
                short_link = find_or_create_short_link(collateral_obj, field_rep_user)

                # Create/update doctor record linked to the field rep
                Doctor.objects.update_or_create(
                    phone=doctor_whatsapp,
                    defaults={
                        'name': doctor_name,
                        'rep': field_rep_user
                    }
                )

                success = log_manual_doctor_share(
                    short_link_id=short_link.id,
                    field_rep_id=field_rep_id,
                    phone_e164=doctor_whatsapp,
                    collateral_id=collateral_id
                )

                if success:
                    # Instead of redirecting away, keep user on the same page and show doctor in the list
                    messages.success(request, f"Doctor '{doctor_name}' added and collateral prepared.")
                    redirect_url = request.path
                    params = []
                    if brand_campaign_id:
                        params.append(f"brand_campaign_id={brand_campaign_id}")
                    params.append(f"collateral={collateral_id}")
                    if params:
                        redirect_url = f"{redirect_url}?{'&'.join(params)}"
                    return redirect(redirect_url)
                else:
                    messages.error(request, 'Error sharing collateral. Please try again.')
                    redirect_url = request.path
                    params = []
                    if brand_campaign_id:
                        params.append(f"brand_campaign_id={brand_campaign_id}")
                    params.append(f"collateral={collateral_id}")
                    if params:
                        redirect_url = f"{redirect_url}?{'&'.join(params)}"
                    return redirect(redirect_url)
            except Exception as e:
                print(f"Error sharing manual doctor: {e}")
                messages.error(request, 'Error sharing collateral. Please try again.')
                redirect_url = request.path
                params = []
                if brand_campaign_id:
                    params.append(f"brand_campaign_id={brand_campaign_id}")
                params.append(f"collateral={collateral_id}")
                if params:
                    redirect_url = f"{redirect_url}?{'&'.join(params)}"
                return redirect(redirect_url)
        else:
            messages.error(request, 'Please fill all required fields.')
            redirect_url = request.path
            params = []
            if brand_campaign_id:
                params.append(f"brand_campaign_id={brand_campaign_id}")
            if collateral_id_str:
                params.append(f"collateral={collateral_id_str}")
            if params:
                redirect_url = f"{redirect_url}?{'&'.join(params)}"
            return redirect(redirect_url)
    
    # Get assigned doctors for this field rep
    from doctor_viewer.models import Doctor
    from sharing_management.models import ShareLog
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Q

    from user_management.models import User as UMUser
    actual_user = None
    if field_rep_field_id:
        actual_user = UMUser.objects.filter(field_id=field_rep_field_id, role='field_rep').first()
    if not actual_user and field_rep_email:
        actual_user = UMUser.objects.filter(email=field_rep_email, role='field_rep').first()
    if not actual_user:
        try:
            if isinstance(field_rep_id, int):
                actual_user = UMUser.objects.filter(id=field_rep_id).first()
            elif isinstance(field_rep_id, str):
                if field_rep_id.isdigit():
                    actual_user = UMUser.objects.filter(id=int(field_rep_id)).first()
                elif field_rep_id.startswith('field_rep_'):
                    rep_num = field_rep_id.split('_')[-1]
                    if rep_num.isdigit():
                        actual_user = UMUser.objects.filter(id=int(rep_num)).first() or UMUser.objects.filter(username=field_rep_id).first()
                    else:
                        actual_user = UMUser.objects.filter(username=field_rep_id).first()
                else:
                    actual_user = UMUser.objects.filter(username=f"field_rep_{field_rep_id}").first()
        except Exception:
            actual_user = UMUser.objects.filter(username=f"field_rep_{field_rep_id}").first()

    if actual_user:
        assigned_doctors = Doctor.objects.filter(rep=actual_user)
    else:
        q = Q()
        if field_rep_field_id:
            q |= Q(rep__field_id=field_rep_field_id)
        if field_rep_email:
            q |= Q(rep__email=field_rep_email)
        if isinstance(field_rep_id, int):
            q |= Q(rep_id=field_rep_id)
        elif isinstance(field_rep_id, str):
            if field_rep_id.isdigit():
                q |= Q(rep_id=int(field_rep_id))
            elif field_rep_id.startswith('field_rep_'):
                q |= Q(rep__username=field_rep_id)
            else:
                q |= Q(rep__username=f"field_rep_{field_rep_id}")
        assigned_doctors = Doctor.objects.filter(q)
    
    # Get the selected collateral ID from URL parameters
    selected_collateral_id = request.GET.get('collateral')
    
    # Prepare doctors with status
    doctors_with_status = []
    for doctor in assigned_doctors:
        status = 'not_sent'
        
        if selected_collateral_id:
            # Check if this collateral was shared with this doctor
            # Match ShareLog records using actual user id or fallback username
            phone_val = doctor.phone or ''
            phone_clean = phone_val.replace('+', '').replace(' ', '').replace('-', '')
            possible_ids = [phone_val]
            if phone_clean and len(phone_clean) == 10:
                possible_ids.append(f"+91{phone_clean}")
                possible_ids.append(f"91{phone_clean}")
            elif phone_clean.startswith('91'):
                possible_ids.append(f"+{phone_clean}")

            share_log_q = Q(doctor_identifier__in=possible_ids) & Q(collateral_id=selected_collateral_id)
            rep_filters = Q()
            rep_ids = []
            if actual_user and getattr(actual_user, 'id', None):
                rep_ids.append(actual_user.id)
            if isinstance(field_rep_id, int):
                rep_ids.append(field_rep_id)
            elif isinstance(field_rep_id, str) and field_rep_id.isdigit():
                rep_ids.append(int(field_rep_id))
            if rep_ids:
                rep_filters |= Q(field_rep_id__in=rep_ids)
            usernames = []
            if isinstance(field_rep_id, str) and field_rep_id.startswith('field_rep_'):
                usernames.append(field_rep_id)
            usernames.append(f"field_rep_{field_rep_id}")
            rep_filters |= Q(field_rep__username__in=usernames)
            share_log_q &= rep_filters

            share_log = ShareLog.objects.filter(share_log_q).order_by('-share_timestamp').first()
            
            if share_log:
                status = 'sent'
                from doctor_viewer.models import DoctorEngagement
                opened = DoctorEngagement.objects.filter(short_link_id=share_log.short_link_id).exists()
                if opened:
                    status = 'opened'
                else:
                    six_days_ago = timezone.now() - timedelta(days=6)
                    if share_log.share_timestamp < six_days_ago:
                        status = 'reminder'
        
        doctors_with_status.append({
            'id': doctor.id,
            'name': doctor.name,
            'phone': doctor.phone,
            'status': status
        })
    
    return render(request, 'sharing_management/fieldrep_gmail_share_collateral.html', {
        'fieldrep_id': field_rep_field_id or 'Unknown',
        'fieldrep_email': field_rep_email,
        'collaterals': collaterals_list,
        'brand_campaign_id': brand_campaign_id,
        'doctors': doctors_with_status,
        'selected_collateral_id': selected_collateral_id
    })

def prefilled_fieldrep_gmail_login(request):
    # Clear any existing session data first
    session_keys = ['field_rep_id', 'field_rep_email', 'field_rep_field_id', 
                   'fieldrep_id', 'fieldrep_field_id', 'is_prefilled_fieldrep']
    for key in session_keys:
        if key in request.session:
            del request.session[key]
    
    campaign_id = request.GET.get('campaign')
    
    # Only process if this is a POST request with valid credentials
    if request.method == 'POST':
        field_rep_id = request.POST.get('field_id')
        gmail = request.POST.get('gmail_id')
        
        if field_rep_id and gmail and campaign_id:
            try:
                from django.db import IntegrityError
                from sharing_management.models import FieldRepresentative
                from django.shortcuts import redirect
                
                # Try to get or create the field representative
                try:
                    # First, try to get an existing rep by field_id
                    rep, created = FieldRepresentative.objects.get_or_create(
                        field_id=field_rep_id,
                        defaults={
                            'gmail': gmail,
                            'email': gmail,
                            'auth_method': 'gmail',
                            'is_active': True
                        }
                    )
                    
                    # If the rep already existed, update the gmail/email if they're different
                    if not created:
                        if rep.gmail != gmail or rep.email != gmail:
                            rep.gmail = gmail
                            rep.email = gmail
                            rep.save(update_fields=['gmail', 'email'])
                    
                    print(f"[DEBUG] Logging in field rep: {field_rep_id}")
                    
                except IntegrityError as ie:
                    # If we get an integrity error, it might be a race condition
                    # Try to get the existing record
                    rep = FieldRepresentative.objects.get(field_id=field_rep_id)
                    
                    # Update the gmail/email if they're different
                    if rep.gmail != gmail or rep.email != gmail:
                        rep.gmail = gmail
                        rep.email = gmail
                        rep.save(update_fields=['gmail', 'email'])
                
                # Log the user in
                request.session['field_rep_id'] = rep.id
                request.session['field_rep_email'] = rep.email
                request.session['field_rep_field_id'] = rep.field_id
                
                # Redirect to share page
                redirect_url = '/share/prefilled-fieldrep-gmail-share-collateral/'
                if campaign_id:
                    redirect_url += f'?campaign={campaign_id}'
                return redirect(redirect_url)
                
            except Exception as e:
                print(f"[ERROR] Error in login/registration: {str(e)}")
                import traceback
                traceback.print_exc()
                from django.contrib import messages
                messages.error(request, 'Error during login. Please try again.')
    
    # If we get here, show the login page
    context = {'campaign': campaign_id}
    print(f"[DEBUG] Rendering login page with context: {context}")
    return render(request, 'sharing_management/prefilled_fieldrep_gmail_login_new.html', context)

def prefilled_fieldrep_gmail_share_collateral_updated(request):
    try:
        import urllib.parse
        from django.utils import timezone
        from collateral_management.models import Collateral, CampaignCollateral
        from django.db.models import OuterRef, Exists, Q, F, Max, BooleanField
        from django.db.models.functions import Coalesce
        from django.db.models.expressions import ExpressionWrapper, Value
        from datetime import timedelta
        from django.contrib import messages
        from django.shortcuts import redirect, render
        from django.http import JsonResponse
        from django.conf import settings
        from doctor_viewer.models import Doctor, DoctorEngagement
        from user_management.models import User
        from sharing_management.models import ShareLog, VideoTrackingLog
        from campaign_management.models import Campaign
        
        # Get user info from session
        field_rep_id = request.session.get('field_rep_id')
        field_rep_email = request.session.get('field_rep_email')
        field_rep_field_id = request.session.get('field_rep_field_id')
        brand_campaign_id = request.GET.get('campaign') or request.session.get('brand_campaign_id')
        
        # Get the field rep user object
        field_rep_user = None
        if field_rep_field_id:
            try:
                field_rep_user = User.objects.get(field_id=field_rep_field_id, role='field_rep')
                print(f"[DEBUG] Found field rep user: {field_rep_user}")
            except User.DoesNotExist:
                if field_rep_email:
                    field_rep_user = User.objects.filter(email=field_rep_email, role='field_rep').first()
        
        if not field_rep_user and field_rep_id:
            try:
                field_rep_user = User.objects.get(id=field_rep_id, role='field_rep')
            except User.DoesNotExist:
                pass
        
        # Store brand_campaign_id in session if provided in URL
        if 'campaign' in request.GET:
            request.session['brand_campaign_id'] = brand_campaign_id
            
        # Get the campaign object if brand_campaign_id is provided
        campaign = None
        if brand_campaign_id:
            try:
                campaign = Campaign.objects.filter(brand_campaign_id=brand_campaign_id).first()
                print(f"[DEBUG] Found campaign: {campaign}")
                if not campaign:
                    print(f"[WARNING] No campaign found with brand_campaign_id: {brand_campaign_id}")
            except Exception as e:
                print(f"[ERROR] Error getting campaign: {e}")
        else:
            print("[DEBUG] No brand_campaign_id provided in request")
        
        if not field_rep_id:
            messages.error(request, 'Please login first.')
            return redirect('fieldrep_login')
            
        # Initialize variables
        doctors_list = []
        collaterals = []
        selected_collateral_id = None
        
        # Get doctors assigned to this field rep
        try:
            if field_rep_user:
                # Get collaterals for the campaign
                campaign_collaterals = []
                if campaign:
                    campaign_collaterals = list(CampaignCollateral.objects.filter(
                        campaign=campaign
                    ).values_list('collateral_id', flat=True))
                
                # Get doctors assigned to this field rep using the reverse relation
                doctors_qs = field_rep_user.doctors.all()
                
                # If no doctors found, try alternative lookup by field_rep_id
                if not doctors_qs.exists() and field_rep_field_id:
                    try:
                        # Try to find by field_id (exact match)
                        field_rep = User.objects.filter(field_id=field_rep_field_id).first()
                        if field_rep:
                            doctors_qs = field_rep.doctors.all()
                    except Exception as e:
                        print(f"[WARNING] Error filtering by field_rep_id: {e}")
                
                # If still no doctors, try to find any doctor with a matching phone number
                if not doctors_qs.exists() and field_rep_user.phone_number:
                    try:
                        # Try to find by rep's phone number (last 4 digits)
                        if field_rep_user.phone_number and len(field_rep_user.phone_number) >= 4:
                            last_four = field_rep_user.phone_number[-4:]
                            doctors_qs = Doctor.objects.filter(phone__endswith=last_four)
                    except Exception as e:
                        print(f"[WARNING] Error finding doctors by phone: {e}")
                
                # If we still don't have doctors, create a dummy list with basic info
                if not doctors_qs.exists():
                    print("[WARNING] No doctors found for field rep:", field_rep_user)
                    # Create a dummy doctor for testing
                    doctors_list = [{
                        'id': 0,
                        'name': 'Test Doctor',
                        'phone': '9876543210',
                        'status': 'not_shared',
                        'last_shared': None
                    }]
                else:
                    # Convert to list with status information
                    doctors_list = []
                    for doc in doctors_qs:
                        doctors_list.append({
                            'id': doc.id,
                            'name': doc.name or 'Unnamed Doctor',
                            'phone': doc.phone or '',
                            'status': 'not_shared',  # Default status
                            'last_shared': None
                        })
                
                # Get the selected collateral ID
                selected_collateral_id = request.GET.get('collateral')
                
                # If no collateral selected, get the most recent one
                if not selected_collateral_id:
                    if campaign_collaterals:
                        latest_collateral = Collateral.objects.filter(
                            id__in=campaign_collaterals,
                            is_active=True
                        ).order_by('-created_at').first()
                    else:
                        latest_collateral = Collateral.objects.filter(
                            is_active=True
                        ).order_by('-created_at').first()
                    
                    if latest_collateral:
                        selected_collateral_id = latest_collateral.id
                
                if selected_collateral_id:
                    doctors_list = []
                    for doc in doctors_qs:
                        status = 'not_sent'
                        last_shared = None
                        phone_val = doc.phone or ''
                        phone_clean = str(phone_val).replace('+', '').replace(' ', '').replace('-', '')
                        ids = [phone_val]
                        if len(phone_clean) == 10:
                            ids.append(f"+91{phone_clean}")
                            ids.append(f"91{phone_clean}")
                        elif phone_clean.startswith('91'):
                            ids.append(f"+{phone_clean}")

                        q = Q(doctor_identifier__in=ids) & Q(collateral_id=selected_collateral_id)
                        share_log = ShareLog.objects.filter(q).order_by('-share_timestamp').first()
                        if share_log:
                            last_shared = share_log.share_timestamp
                            status = 'sent'
                            if DoctorEngagement.objects.filter(short_link_id=share_log.short_link_id).exists():
                                status = 'opened'
                            else:
                                if share_log.share_timestamp <= timezone.now() - timedelta(days=6):
                                    status = 'reminder'

                        doctors_list.append({
                            'id': doc.id,
                            'name': doc.name or 'Unnamed Doctor',
                            'phone': doc.phone or '',
                            'status': status,
                            'last_shared': last_shared
                        })
                else:
                    doctors_list = [{
                        'id': doc.id,
                        'name': doc.name or 'Unnamed Doctor',
                        'phone': doc.phone or '',
                        'status': 'not_sent',
                        'last_shared': None
                    } for doc in doctors_qs]
        
        except Exception as e:
            print(f"[ERROR] Error fetching doctors: {e}")
            
        
        # Get collaterals for the dropdown
        collaterals = []
        try:
            from collateral_management.models import CampaignCollateral
            
            if campaign:
                print(f"[DEBUG] Fetching collaterals for campaign: {campaign.id} - {campaign.name}")
                try:
                    # Get active campaign collaterals with related collateral data
                    campaign_collaterals = CampaignCollateral.objects.filter(
                        campaign=campaign,
                        collateral__is_active=True
                    ).select_related('collateral').order_by('-collateral__created_at')
                    
                    print(f"[DEBUG] Found {campaign_collaterals.count()} campaign collaterals")
                    
                    if campaign_collaterals.exists():
                        collaterals = [{
                            'id': cc.collateral.id,
                            'name': cc.collateral.title or f'Collateral {cc.collateral.id}'
                        } for cc in campaign_collaterals]
                        print(f"[DEBUG] Found {len(collaterals)} active collaterals for campaign")
                    else:
                        print("[WARNING] No active collaterals found for campaign")
                        all_collaterals = Collateral.objects.filter(is_active=True).order_by('-created_at')
                        collaterals = [{
                            'id': c.id,
                            'name': c.title or f'Collateral {c.id}'
                        } for c in all_collaterals]
                        print(f"[DEBUG] Falling back to {len(collaterals)} active collaterals")
                        
                except Exception as e:
                    print(f"[ERROR] Error fetching campaign collaterals: {e}")
                    import traceback
                    traceback.print_exc()
                    all_collaterals = Collateral.objects.filter(is_active=True).order_by('-created_at')
                    collaterals = [{
                        'id': c.id,
                        'name': c.title or f'Collateral {c.id}'
                    } for c in all_collaterals]
                    print(f"[DEBUG] Error occurred, falling back to {len(collaterals)} active collaterals")
            else:
                print("[DEBUG] No campaign specified, fetching all active collaterals")
                all_collaterals = Collateral.objects.filter(is_active=True).order_by('-created_at')
                collaterals = [{
                    'id': c.id,
                    'name': c.title or f'Collateral {c.id}'
                } for c in all_collaterals]
                print(f"[DEBUG] Found {len(collaterals)} active collaterals")
                
            print(f"[DEBUG] Returning {len(collaterals)} collaterals")
                
        except Exception as e:
            import traceback
            error_msg = f"[ERROR] Error fetching collaterals: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            messages.error(request, 'Error loading collaterals. Please try again.')
            # Fallback to empty queryset
            collaterals = Collateral.objects.none()
        
        # Handle AJAX form submission for sharing
        if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            try:
                from sharing_management.models import ShareLog
                from django.urls import reverse
                
                doctor_id = request.POST.get('doctor_id')
                collateral_id = request.POST.get('collateral')
                
                if not doctor_id or not collateral_id:
                    return JsonResponse({
                        'success': False,
                        'message': 'Please select both doctor and collateral.'
                    }, status=400)
                
                try:
                    # Get doctor and collateral objects
                    try:
                        from user_management.models import User
                        
                        # Handle field_rep_* format by finding the actual user first
                        if isinstance(doctor_id, str) and doctor_id.startswith('field_rep_'):
                            # Extract the numeric part after 'field_rep_'
                            try:
                                rep_id = int(doctor_id.split('_')[-1])
                                # Find the doctor associated with this field rep
                                doctor = Doctor.objects.filter(rep_id=rep_id).first()
                                if not doctor:
                                    messages.error(request, 'Doctor not found for this field rep')
                                    return redirect(request.path)
                            except (ValueError, IndexError):
                                messages.error(request, 'Invalid doctor ID format')
                                return redirect(request.path)
                        else:
                            # Handle numeric ID case
                            if isinstance(doctor_id, str) and doctor_id.isdigit():
                                doctor_id = int(doctor_id)
                            doctor = Doctor.objects.filter(id=doctor_id).first()
                            if not doctor:
                                messages.error(request, 'Doctor not found')
                                return redirect(request.path)
                        
                        collateral = Collateral.objects.get(id=collateral_id)
                    except (ValueError, TypeError) as e:
                        messages.error(request, f'Error processing request: {str(e)}')
                        return redirect(request.path)
                    
                    # Create a short link for the collateral
                    from shortlink_management.models import ShortLink
                    from django.utils.crypto import get_random_string

                    short_code = get_random_string(length=6)
                    short_link = ShortLink.objects.create(
                        short_code=short_code,
                        resource_type='collateral',
                        resource_id=collateral.id,
                        created_by=field_rep_user,
                        is_active=True
                    )

                    # Create share log with the short link
                    share_log = ShareLog.objects.create(
                        short_link=short_link,
                        collateral=collateral,
                        field_rep=field_rep_user,
                        doctor_identifier=doctor.phone or doctor.email or f"Doctor {doctor.id}",
                        share_channel='WhatsApp',
                        message_text=f"Shared collateral: {collateral.title}"
                    )
                    # Tiny, safe hook: upsert transaction row for this send
                    try:
                        upsert_from_sharelog(
                            share_log,
                            brand_campaign_id=str(brand_campaign_id),
                            doctor_name=getattr(doctor, 'name', None),
                            field_rep_unique_id=getattr(field_rep_user, "employee_code", None),
                            sent_at=share_log.share_timestamp,
                        )
                    except Exception:
                        pass

                    # --- Generate WhatsApp share URL ---
                    from urllib.parse import quote

                    # Use configured SITE_URL or fallback
                    base_url = getattr(settings, 'SITE_URL', 'http://example.com')
                    short_url = request.build_absolute_uri(f"/shortlinks/go/{share_log.short_link.short_code}/")

                    # WhatsApp message text
                    message = (
                        f"{share_log.message_text} {short_url}"
                        if share_log.message_text
                        else f"Hello Doctor, please check this: {short_url}"
                    )

                    # Properly URL encode message
                    encoded_message = quote(message, safe='')

                    # Ensure phone is digits only (no +, spaces, etc.)
                    phone = str(doctor.phone).replace('+', '').replace(' ', '')

                    # Final WhatsApp link
                    whatsapp_url = f"https://wa.me/{phone}?text={encoded_message}"

                    return JsonResponse({
                        'success': True,
                        'message': 'Collateral shared successfully!',
                        'wa_url': whatsapp_url,
                        'doctor_id': doctor_id
                    })

                except (Doctor.DoesNotExist, Collateral.DoesNotExist):
                    return JsonResponse({
                        'success': False,
                        'message': 'Invalid doctor or collateral selected.'
                    }, status=400)

            except Exception as e:
                import traceback
                print(f"[ERROR] Error processing AJAX form: {e}")
                traceback.print_exc()
                return JsonResponse({
                    'success': False,
                    'message': 'An error occurred while processing your request.'
                }, status=500)
        
        # Handle non-AJAX form submission (fallback)
        elif request.method == 'POST':
            try:
                doctor_id = request.POST.get('doctor_id')
                collateral_id = request.POST.get('collateral')
                
                if not doctor_id or not collateral_id:
                    messages.error(request, 'Please select both doctor and collateral.')
                else:
                    # Handle the sharing logic for non-AJAX
                    try:
                        from user_management.models import User
                        
                        # Handle field_rep_* format by finding the actual user first
                        if isinstance(doctor_id, str) and doctor_id.startswith('field_rep_'):
                            # Extract the numeric part after 'field_rep_'
                            try:
                                rep_id = int(doctor_id.split('_')[-1])
                                # Find the doctor associated with this field rep
                                doctor = Doctor.objects.filter(rep_id=rep_id).first()
                                if not doctor:
                                    messages.error(request, 'Doctor not found for this field rep')
                                    return redirect(request.path)
                            except (ValueError, IndexError):
                                messages.error(request, 'Invalid doctor ID format')
                                return redirect(request.path)
                        else:
                            # Handle numeric ID case
                            if isinstance(doctor_id, str) and doctor_id.isdigit():
                                doctor_id = int(doctor_id)
                            doctor = Doctor.objects.filter(id=doctor_id).first()
                            if not doctor:
                                messages.error(request, 'Doctor not found')
                                return redirect(request.path)
                        
                        collateral = Collateral.objects.get(id=collateral_id)
                    except (ValueError, TypeError) as e:
                        messages.error(request, f'Error processing request: {str(e)}')
                        return redirect(request.path)
                        
                        # Create short link and share log (similar to AJAX version)
                        from shortlink_management.models import ShortLink
                        from django.utils.crypto import get_random_string
                        from urllib.parse import quote

                        short_code = get_random_string(length=6)
                        short_link = ShortLink.objects.create(
                            short_code=short_code,
                            resource_type='collateral',
                            resource_id=collateral.id,
                            created_by=field_rep_user,
                            is_active=True
                        )

                        share_log = ShareLog.objects.create(
                            short_link=short_link,
                            collateral=collateral,
                            field_rep=field_rep_user,
                            doctor_identifier=doctor.phone or doctor.email or f"Doctor {doctor.id}",
                            share_channel='WhatsApp',
                            message_text=f"Shared collateral: {collateral.title}"
                        )
                        # Tiny, safe hook: upsert transaction row for this send
                        try:
                            upsert_from_sharelog(
                                share_log,
                                brand_campaign_id=str(brand_campaign_id),
                                doctor_name=getattr(doctor, 'name', None),
                                field_rep_unique_id=getattr(field_rep_user, "employee_code", None),
                                sent_at=share_log.share_timestamp,
                            )
                        except Exception:
                            pass

                        messages.success(request, 'Collateral shared successfully!')
                        
                    except (Doctor.DoesNotExist, Collateral.DoesNotExist):
                        messages.error(request, 'Invalid doctor or collateral selected.')
                    
                return redirect(request.path + f'?campaign={brand_campaign_id}' + 
                              (f'&collateral={collateral_id}' if collateral_id else ''))
                    
            except Exception as e:
                print(f"[ERROR] Error processing non-AJAX form: {e}")
                messages.error(request, 'Error processing your request. Please try again.')
        
        # Prepare context for the template
        context = {
            'fieldrep_id': field_rep_field_id or 'N/A',
            'fieldrep_email': field_rep_email or 'N/A',
            'doctors': doctors_list,
            'collaterals': collaterals,
            'selected_collateral_id': int(selected_collateral_id) if selected_collateral_id else None,
            'brand_campaign_id': brand_campaign_id,
            'campaign': brand_campaign_id  # Add campaign to context for template
        }
        
        # Use the new template
        return render(request, 'sharing_management/prefilled_fieldrep_gmail_share_collateral_updated.html', context)
        
    except Exception as e:
        import traceback
        print(f"[ERROR] Error in prefilled_fieldrep_gmail_share_collateral_updated: {e}")
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'message': 'An error occurred while processing your request.'
        }, status=500)
def fieldrep_whatsapp_login(request):
    if request.method == 'POST':
        field_id = request.POST.get('field_id')
        raw = request.POST.get('whatsapp_number', '')
        import re
        digits = re.sub(r'\D', '', raw)
        if len(digits) == 10:
            whatsapp_number = f'+91{digits}'
        elif digits.startswith('91') and len(digits) == 12:
            whatsapp_number = f'+{digits}'
        elif digits.startswith('0') and len(digits) == 11:
            whatsapp_number = f'+91{digits[1:]}'
        else:
            whatsapp_number = f'+{digits}'
        
        if field_id and whatsapp_number:
            # Get client IP and user agent for audit logging
            ip_address = request.META.get('REMOTE_ADDR')
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            # Try authentication first
            success, user_id, user_data = authenticate_field_representative_direct(field_id, whatsapp_number, ip_address, user_agent)
            
            # If authentication fails, try to register new user automatically
            if not success:
                print(f"Authentication failed, attempting automatic registration for {field_id}")
                
                # Create user directly in User model for immediate login
                try:
                    from user_management.models import User
                    from django.contrib.auth.hashers import make_password
                    
                    # Check if user already exists in User model
                    existing_user = User.objects.filter(field_id=field_id).first()
                    if not existing_user:
                        # Create new user directly
                        new_user = User.objects.create(
                            username=f"fieldrep_{field_id}",
                            email=f"{field_id.lower()}@example.com",
                            field_id=field_id,
                            phone_number=whatsapp_number,
                            role='field_rep',
                            active=True,
                            password=make_password("defaultpass123")
                        )
                        print(f"DEBUG: Created new user with ID: {new_user.id}")
                        
                        # Set session data directly for immediate login
                        success = True
                        user_id = new_user.id
                        user_data = {
                            'field_id': field_id,
                            'email': new_user.email,
                            'phone_number': whatsapp_number
                        }
                        messages.success(request, f'Welcome! New account created for {field_id}')
                    else:
                        print(f"DEBUG: User already exists, using existing user")
                        success = True
                        user_id = existing_user.id
                        user_data = {
                            'field_id': field_id,
                            'email': existing_user.email,
                            'phone_number': whatsapp_number
                        }
                        messages.success(request, f'Welcome back, {field_id}!')
                        
                except Exception as e:
                    print(f"DEBUG: Error creating user: {e}")
                    messages.error(request, 'Could not create account. Please try again.')
                    return redirect('fieldrep_whatsapp_login')
            
            if success:
                # Clear any existing Google authentication session
                google_session_keys = [
                    '_auth_user_id', '_auth_user_backend', '_auth_user_hash',
                    'user_id', 'username', 'email', 'first_name', 'last_name'
                ]
                
                for key in google_session_keys:
                    if key in request.session:
                        del request.session[key]
                
                # Store field rep user info in session
                request.session['field_rep_id'] = user_id
                request.session['field_rep_email'] = user_data['email']
                request.session['field_rep_field_id'] = user_data['field_id']
                
                print(f"DEBUG: Session data stored - ID: {user_id}, Email: {user_data['email']}, Field ID: {user_data['field_id']}")
                
                messages.success(request, f'Welcome back, {user_data["field_id"]}!')
                
                # Check if user is prefilled or manual based on field_id
                if user_data['field_id'] and user_data['field_id'].startswith('PREFILLED_'):
                    # Prefilled user - redirect to prefilled share collateral
                    print(f"DEBUG: Redirecting to prefilled share collateral")
                    return redirect('prefilled_fieldrep_share_collateral')
                else:
                    # Manual user - redirect to whatsapp share collateral
                    print(f"DEBUG: Redirecting to manual whatsapp share collateral")
                    return redirect('fieldrep_whatsapp_share_collateral')
            else:
                messages.error(request, 'Invalid Field ID or WhatsApp number. Please check and try again.')
        else:
            messages.error(request, 'Please provide both Field ID and WhatsApp number.')
    
    return render(request, 'sharing_management/fieldrep_whatsapp_login.html')

def fieldrep_whatsapp_share_collateral_updated(request, brand_campaign_id=None):
    import urllib.parse
    
    # Get user info from session
    field_rep_id = request.session.get('field_rep_id')
    field_rep_email = request.session.get('field_rep_email')
    field_rep_field_id = request.session.get('field_rep_field_id')
    selected_collateral_id = None  # Initialize with default value
    
    # Get brand_campaign_id from URL or GET parameters (support both 'brand_campaign_id' and 'campaign' parameters)
    brand_campaign_id = (
        request.resolver_match.kwargs.get('brand_campaign_id') or 
        request.GET.get('brand_campaign_id') or 
        request.GET.get('campaign')
    )
    
    # Store brand_campaign_id in session if provided in URL
    if 'campaign' in request.GET:
        request.session['brand_campaign_id'] = brand_campaign_id
    
    print(f"DEBUG: Share collateral view - Session data: ID={field_rep_id}, Email={field_rep_email}, Field_ID={field_rep_field_id}, Campaign={brand_campaign_id}")
    
    if not field_rep_id:
        print(f"DEBUG: No field_rep_id in session, redirecting to login")
        messages.error(request, 'Please login first.')
        return redirect('fieldrep_whatsapp_login')
    
    # Get real collaterals from database
    try:
        from collateral_management.models import Collateral, CampaignCollateral
        from user_management.models import User
        from campaign_management.models import CampaignCollateral as CMCampaignCollateral
        
        # Initialize empty list for collaterals
        collaterals = []
        
        if brand_campaign_id and brand_campaign_id != 'all':
            print(f"[DEBUG] Filtering collaterals for brand_campaign_id: {brand_campaign_id}")
            
            # First from campaign_management.CampaignCollateral
            cc_links = CMCampaignCollateral.objects.filter(
                campaign__brand_campaign_id=brand_campaign_id
            ).select_related('collateral', 'campaign')
            print(f"[DEBUG] Found {len(cc_links)} campaign collaterals from campaign_management")
            
            campaign_collaterals = [link.collateral for link in cc_links if link.collateral and getattr(link.collateral, 'is_active', True)]
            print(f"[DEBUG] After filtering, {len(campaign_collaterals)} active campaign collaterals")
            
            # Then from collateral_management.CampaignCollateral
            collateral_links = CampaignCollateral.objects.filter(
                campaign__brand_campaign_id=brand_campaign_id
            ).select_related('collateral', 'campaign')
            print(f"[DEBUG] Found {len(collateral_links)} collaterals from collateral_management")
            
            collateral_collaterals = [link.collateral for link in collateral_links if link.collateral and getattr(link.collateral, 'is_active', True)]
            print(f"[DEBUG] After filtering, {len(collateral_collaterals)} active collaterals from collateral_management")
            
            # Combine and deduplicate collaterals
            all_collaterals = campaign_collaterals + collateral_collaterals
            print(f"[DEBUG] Total collaterals before deduplication: {len(all_collaterals)}")
            
            collaterals = list({c.id: c for c in all_collaterals if hasattr(c, 'id')}.values())
            print(f"[DEBUG] Total unique collaterals after deduplication: {len(collaterals)}")
            
            if not collaterals:
                messages.info(request, f"No collaterals found for campaign {brand_campaign_id}")
            else:
                # Initialize selected collateral from GET or default to first one
                selected_collateral_id = request.GET.get('collateral')
                if not selected_collateral_id and collaterals:
                    selected_collateral_id = collaterals[0].id
                if selected_collateral_id:
                    try:
                        selected_collateral_id = int(selected_collateral_id)
                    except (ValueError, TypeError):
                        selected_collateral_id = collaterals[0].id if collaterals else None
        else:
            # Show all active collaterals if no brand campaign ID provided
            collaterals = Collateral.objects.filter(is_active=True).order_by('-created_at')
            messages.info(request, "Showing all available collaterals as no specific campaign is selected.")
            
            # Initialize selected collateral from GET or default to latest
            selected_collateral_id = request.GET.get('collateral')
            if not selected_collateral_id and collaterals.exists():
                selected_collateral_id = collaterals.first().id
            if selected_collateral_id:
                try:
                    selected_collateral_id = int(selected_collateral_id)
                except (ValueError, TypeError):
                    selected_collateral_id = None
        
        # Get the actual user object for short link creation
        try:
            actual_user = User.objects.get(id=field_rep_id)
        except User.DoesNotExist:
            actual_user = request.user  # fallback
        
        # Convert to list format for template
        collaterals_list = []
        for collateral in collaterals:
            try:
                # Create short link for each collateral
                short_link = find_or_create_short_link(collateral, actual_user)
                collaterals_list.append({
                    'id': collateral.id,
                    'name': getattr(collateral, 'title', getattr(collateral, 'item_name', 'Untitled')),
                    'description': getattr(collateral, 'description', ''),
                    'link': request.build_absolute_uri(f"/shortlinks/go/{short_link.short_code}/")
                })
            except Exception as e:
                print(f"Error creating short link for collateral {getattr(collateral, 'id', 'unknown')}: {e}")
                continue
                
    except Exception as e:
        print(f"Error fetching collaterals: {e}")
        collaterals_list = []
        messages.error(request, 'Error loading collaterals. Please try again.')
    
    # Do not override selected collateral here; keep original flow

    if request.method == 'POST':
        print(f"POST request received: {request.POST}")
        action = request.POST.get('action')
        doctor_id = request.POST.get('doctor_id')
        doctor_name = request.POST.get('doctor_name')
        doctor_whatsapp = request.POST.get('doctor_whatsapp')
        collateral_id = request.POST.get('collateral')

        # Branch 0: Add Doctor (persist only, no share)
        if action == 'add_doctor':
            try:
                from user_management.models import User
                from doctor_viewer.models import Doctor

                # Get the field rep user
                try:
                    field_rep_user = User.objects.get(id=field_rep_id)
                except User.DoesNotExist:
                    messages.error(request, 'Field representative not found.')
                    return redirect('fieldrep_whatsapp_share_collateral')

                # Validate inputs
                if not doctor_name or not doctor_whatsapp:
                    messages.error(request, 'Please provide both doctor name and WhatsApp number.')
                    return redirect('fieldrep_whatsapp_share_collateral')

                clean_phone = ''.join(c for c in doctor_whatsapp if c.isdigit())
                if len(clean_phone) != 10:
                    messages.error(request, 'Please enter a valid 10-digit phone number.')
                    return redirect('fieldrep_whatsapp_share_collateral')

                formatted_phone = f"+91{clean_phone}"

                # Create or update the doctor record and assign to this rep
                doctor, created = Doctor.objects.update_or_create(
                    rep=field_rep_user,
                    phone=formatted_phone,
                    defaults={
                        'name': doctor_name.strip(),
                        'source': 'manual'
                    }
                )

                if created:
                    messages.success(request, f'Doctor {doctor_name} added and assigned successfully.')
                else:
                    messages.success(request, f'Doctor {doctor_name} updated and assigned successfully.')

                return redirect('fieldrep_whatsapp_share_collateral')
            except Exception as e:
                print(f"Error adding doctor: {e}")
                import traceback; traceback.print_exc()
                messages.error(request, 'An error occurred while adding the doctor.')
                return redirect('fieldrep_whatsapp_share_collateral')

        print(f"Form data - Doctor: {doctor_name}, WhatsApp: {doctor_whatsapp}, Collateral: {collateral_id}")

        if not collateral_id:
            messages.error(request, 'Please select a collateral.')
            return redirect('fieldrep_whatsapp_share_collateral')
            
        try:
            collateral_id = int(collateral_id)
        except (ValueError, TypeError):
            messages.error(request, 'Invalid collateral selected.')
            return redirect('fieldrep_whatsapp_share_collateral')

        # Find the selected collateral
        selected_collateral = next((c for c in collaterals_list if c['id'] == collateral_id), None)
        print(f"Selected collateral: {selected_collateral}")
        
        # Branch A: assigned doctor via doctor_id (button in list)
        if doctor_id:
            try:
                from doctor_viewer.models import Doctor
                from collateral_management.models import Collateral
                from .utils.db_operations import log_manual_doctor_share

                # Handle both numeric and field_rep_* formatted IDs
                if isinstance(doctor_id, str) and doctor_id.startswith('field_rep_'):
                    try:
                        # Extract the numeric part after 'field_rep_'
                        rep_id = int(doctor_id.split('_')[-1])
                        # Find the doctor associated with this field rep
                        doc = Doctor.objects.filter(rep_id=rep_id).first()
                    except (ValueError, IndexError):
                        messages.error(request, 'Invalid doctor ID format')
                        return redirect(request.path)
                else:
                    # Handle numeric ID case
                    try:
                        doc_pk = int(doctor_id)
                        doc = Doctor.objects.filter(pk=doc_pk).first()
                    except (ValueError, TypeError):
                        messages.error(request, 'Invalid doctor ID')
                        return redirect(request.path)
                
                if not doc:
                    messages.error(request, 'Doctor not found')
                    return redirect(request.path)

                # Build short link for selected collateral
                collateral_obj = Collateral.objects.get(id=collateral_id)
                short_link = find_or_create_short_link(collateral_obj, actual_user)

                # Log share with doctor's phone
                success = log_manual_doctor_share(
                    short_link_id=short_link.id,
                    field_rep_id=field_rep_id,
                    phone_e164=doc.phone or '',
                    collateral_id=collateral_id
                )

                if success:
                    message = get_brand_specific_message(collateral_id, selected_collateral['name'], selected_collateral['link'])
                    clean_phone = (doc.phone or '').replace('+91', '').replace('+', '').replace(' ', '').replace('-', '')
                    wa_url = f"https://wa.me/91{clean_phone}?text={urllib.parse.quote(message)}"
                    messages.success(request, f"Message prepared for {doc.name}. Redirecting to WhatsApp…")
                    return redirect(wa_url)
                else:
                    messages.error(request, 'Error sharing collateral. Please try again.')
                    return redirect('fieldrep_whatsapp_share_collateral')
            except Exception as e:
                print(f"Error sharing to assigned doctor: {e}")
                import traceback; traceback.print_exc()
                messages.error(request, 'An error occurred while preparing WhatsApp message.')
                return redirect('fieldrep_whatsapp_share_collateral')

        # Branch B: manual doctor entered in the form
        if selected_collateral and doctor_name and doctor_whatsapp:
            try:
                from .utils.db_operations import log_manual_doctor_share
                from collateral_management.models import Collateral
                from doctor_viewer.models import Doctor
                from user_management.models import User
                
                # Get the field rep user
                try:
                    field_rep_user = User.objects.get(id=field_rep_id)
                except User.DoesNotExist:
                    messages.error(request, 'Field representative not found.')
                    return redirect('fieldrep_whatsapp_share_collateral')
                
                # Clean and validate phone number
                clean_phone = ''.join(c for c in doctor_whatsapp if c.isdigit())
                if len(clean_phone) != 10:
                    messages.error(request, 'Please enter a valid 10-digit phone number.')
                    return redirect('fieldrep_whatsapp_share_collateral')
                
                # Format phone number for storage
                formatted_phone = f"+91{clean_phone}"
                
                # Create or update the doctor record
                doctor, created = Doctor.objects.update_or_create(
                    rep=field_rep_user,
                    phone=formatted_phone,
                    defaults={
                        'name': doctor_name.strip(),
                        'source': 'manual'
                    }
                )
                
                # Get the collateral object
                try:
                    collateral_obj = Collateral.objects.get(id=collateral_id, is_active=True)
                except Collateral.DoesNotExist:
                    messages.error(request, 'Selected collateral not found or inactive.')
                    return redirect('fieldrep_whatsapp_share_collateral')
                
                # Create or get short link
                short_link = find_or_create_short_link(collateral_obj, actual_user)
                
                # Log the doctor share
                success = log_manual_doctor_share(
                    short_link_id=short_link.id,
                    field_rep_id=field_rep_id,
                    phone_e164=formatted_phone,
                    collateral_id=collateral_id
                )
                
                if success:
                    # Get brand-specific message
                    message = get_brand_specific_message(
                        collateral_id, 
                        selected_collateral['name'], 
                        selected_collateral.get('link', '')
                    )
                    
                    # Clean phone number for WhatsApp URL
                    whatsapp_phone = clean_phone  # Already cleaned to 10 digits
                    wa_url = f"https://wa.me/91{whatsapp_phone}?text={urllib.parse.quote(message)}"
                    
                    # Add success message and redirect to WhatsApp
                    messages.success(request, f'Collateral shared successfully with {doctor_name}!')
                    return redirect(wa_url)
                else:
                    messages.error(request, 'Failed to log share. Please try again.')
                    return redirect('fieldrep_whatsapp_share_collateral')
                    
            except Exception as e:
                print(f"Error in doctor share process: {str(e)}")
                import traceback
                traceback.print_exc()
                messages.error(request, 'An error occurred while processing your request. Please try again.')
                return redirect('fieldrep_whatsapp_share_collateral')
        else:
            messages.error(request, 'Please fill in all required fields.')
            return redirect('fieldrep_whatsapp_share_collateral')
    
    # Debug information
    print(f"[DEBUG] Rendering template with {len(collaterals_list)} collaterals")
    
    # Get the actual user object to get the name
    from user_management.models import User
    from doctor_viewer.models import Doctor
    from sharing_management.models import ShareLog
    from django.db.models import Max, Q
    from datetime import datetime, timedelta
    
    try:
        user = User.objects.get(id=field_rep_id)
        field_rep_name = user.get_full_name() or user.username or field_rep_field_id or "Field Representative"
        
        # Get doctors assigned to this field rep
        doctors = Doctor.objects.filter(rep=user)
        print(f"[DEBUG] Found {doctors.count()} doctors assigned to field rep {field_rep_id}")
        
        # Get share logs for these doctors
        doctors_list = []
        if doctors.exists():
            # Get the latest share log for each doctor
            doctor_phones = doctors.values_list('phone', flat=True)
            latest_logs = (
                ShareLog.objects
                .filter(doctor_identifier__in=doctor_phones)
                .filter(
                    Q(field_rep_id=getattr(actual_user, 'id', None)) |
                    Q(field_rep__username=f"field_rep_{field_rep_id}")
                )
            ).values('doctor_identifier').annotate(
                latest_share=Max('share_timestamp'),
                latest_view=Max('created_at')
            )
            
            # Create a dictionary of doctor_identifier -> latest share info
            share_info = {log['doctor_identifier']: log for log in latest_logs}
            
            # Determine status for each doctor
            now = datetime.now()
            for doctor in doctors:
                status = 'not_shared'  # default status
                
                # Use phone number as the identifier for share logs
                if doctor.phone in share_info:
                    log = share_info[doctor.phone]
                    if log['latest_view']:
                        status = 'viewed'
                    elif log['latest_share']:
                        days_since_share = (now - log['latest_share'].replace(tzinfo=None)).days
                        if days_since_share > 3:  # More than 3 days since last share
                            status = 'needs_reminder'
                        else:
                            status = 'shared'
                
                doctors_list.append({
                    'id': doctor.id,
                    'name': doctor.name,
                    'phone': doctor.phone,
                    'email': getattr(doctor, 'email', ''),  # Safely get email attribute
                    'specialty': getattr(doctor, 'specialty', ''),
                    'city': getattr(doctor, 'city', ''),
                    'status': status
                })
            
            print(f"[DEBUG] Processed {len(doctors_list)} doctors with their status")
        
    except User.DoesNotExist:
        field_rep_name = field_rep_field_id or "Field Representative"
        doctors_list = []
    except Exception as e:
        print(f"[ERROR] Error processing doctors: {e}")
        import traceback
        traceback.print_exc()
        doctors_list = []
    
    # Compute per-doctor status for the selected collateral to drive button colors
    try:
        from sharing_management.models import ShareLog
        from doctor_viewer.models import DoctorEngagement
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        for d in doctors_list:
            phone = (d.get('phone') or '').strip()
            status = 'not_shared'
            if selected_collateral_id and phone:
                # Normalize phone to digits for matching regardless of +country code
                digits = ''.join(ch for ch in phone if ch.isdigit())
                last10 = digits[-10:] if len(digits) >= 10 else digits
                sl = (
                    ShareLog.objects
                    .filter(collateral_id=selected_collateral_id)
                    .filter(
                        Q(field_rep_id=getattr(actual_user, 'id', None)) |
                        Q(field_rep__username=f"field_rep_{field_rep_id}")
                    )
                    .filter(
                        Q(doctor_identifier=phone) |
                        Q(doctor_identifier__endswith=digits) |
                        Q(doctor_identifier__endswith=last10) |
                        Q(doctor_identifier__endswith=('91' + last10))
                    )
                    .order_by('-share_timestamp')
                    .first()
                )

                if sl:
                    engaged = DoctorEngagement.objects.filter(short_link_id=sl.short_link_id).exists()
                    if engaged:
                        status = 'viewed'
                    else:
                        six_days_ago = now - timedelta(days=6)
                        status = 'needs_reminder' if sl.share_timestamp <= six_days_ago else 'shared'
            d['status'] = status
    except Exception as e:
        print(f"[WARN] Failed computing doctor statuses: {e}")
        for d in doctors_list:
            d['status'] = d.get('status') or 'not_shared'

    return render(request, 'sharing_management/fieldrep_whatsapp_share_collateral.html', {
        'collaterals': collaterals_list,
        'doctors': doctors_list,
        'brand_campaign_id': brand_campaign_id,
        'fieldrep_id': field_rep_field_id or field_rep_id or "",
        'field_rep_name': field_rep_name,
        'field_rep_email': field_rep_email or "",
        'selected_collateral_id': selected_collateral_id,
    })
def prefilled_fieldrep_whatsapp_login(request, brand_campaign_id=None):
    # If user is already authenticated, redirect to share collateral page
    if request.user.is_authenticated and hasattr(request.user, 'fieldrep'):
        if brand_campaign_id:
            return redirect('prefilled_fieldrep_whatsapp_share_collateral_by_campaign', 
                          brand_campaign_id=brand_campaign_id)
        return redirect('prefilled_fieldrep_whatsapp_share_collateral')

    if request.method == 'POST':
        field_id = (request.POST.get('field_id') or '').strip()
        raw_phone = request.POST.get('whatsapp_number') or ''
        
        # Store brand_campaign_id in session if provided in URL
        if brand_campaign_id:
            request.session['brand_campaign_id'] = brand_campaign_id

        # --- Normalize phone to E.164 (+91XXXXXXXXXX) ---
        digits = re.sub(r'\D', '', raw_phone)
        if len(digits) == 10:
            phone_e164 = f'+91{digits}'
        elif digits.startswith('91') and len(digits) == 12:
            phone_e164 = f'+{digits}'
        elif digits.startswith('0') and len(digits) == 11:
            phone_e164 = f'+91{digits[1:]}'
        else:
            phone_e164 = f'+{digits}' if digits else ''

        if not field_id or not phone_e164:
            messages.error(request, 'Please provide both Field ID and WhatsApp number.')
            return render(request, 'sharing_management/prefilled_fieldrep_whatsapp_login.html')

        # --- Try direct auth against existing field rep ---
        ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        success, user_id, user_data = authenticate_field_representative_direct(
            field_id, phone_e164, ip_address, user_agent
        )

        if not success:
            messages.error(request, 'Invalid Field ID or WhatsApp number.')
            return render(request, 'sharing_management/prefilled_fieldrep_whatsapp_login.html')

        # --- Log user into Django (covers @login_required targets) ---
        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            messages.error(request, 'Your account was found but is inactive or missing.')
            return render(request, 'sharing_management/prefilled_fieldrep_whatsapp_login.html')

        # If you use a custom backend, pass its dotted path here; otherwise default ModelBackend
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')

        # --- Set EVERY session flag the share view might expect ---
        fr_field_id = user_data.get('field_id') or getattr(user, 'field_id', '') or field_id
        request.session['fieldrep_id'] = user.id
        request.session['field_rep_id'] = user.id
        request.session['fieldrep_field_id'] = fr_field_id
        request.session['field_rep_field_id'] = fr_field_id
        request.session['is_prefilled_fieldrep'] = True
        
        # Store brand_campaign_id in session if available in the URL
        if brand_campaign_id:
            request.session['brand_campaign_id'] = brand_campaign_id

        messages.success(request, f'Welcome back, {fr_field_id}!')
        
        # Redirect to the share collateral page with brand_campaign_id if available
        if brand_campaign_id or 'brand_campaign_id' in request.session:
            campaign_id = brand_campaign_id or request.session.get('brand_campaign_id')
            return redirect('prefilled_fieldrep_whatsapp_share_collateral_by_campaign', 
                          brand_campaign_id=campaign_id)
        return redirect('prefilled_fieldrep_whatsapp_share_collateral')

    # GET: render login form
    return render(request, 'sharing_management/prefilled_fieldrep_whatsapp_login.html')
def _current_fieldrep_user_id(request):
    return (
        request.session.get('field_rep_id')
        or request.session.get('fieldrep_id')
        or (request.user.is_authenticated and request.user.id)
        or None
    )
def _get_current_rep_ids(request):
    """
    Returns:
      rep_pk       -> user_management_user.id (int) if available
      rep_field_id -> business Field ID string (e.g., 'FR123')
      rep_smg_id   -> sharing_management_fieldrepresentative.id (int) if present
    """
    from django.db import connection

    rep_pk = (
        request.session.get('field_rep_id')
        or request.session.get('fieldrep_id')
        or (request.user.is_authenticated and request.user.id)
        or None
    )
    rep_field_id = (
        request.session.get('field_rep_field_id')
        or request.session.get('fieldrep_field_id')
        or getattr(request.user, 'field_id', None)
    )

    rep_smg_id = None
    if rep_field_id:
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id
                    FROM sharing_management_fieldrepresentative
                    WHERE UPPER(field_id) = UPPER(%s)
                    LIMIT 1
                """, [rep_field_id])
                row = cursor.fetchone()
                if row:
                    rep_smg_id = row[0]
        except Exception as e:
            # Table may not exist in some deployments; okay to ignore.
            print(f"[info] SMG rep lookup by field_id failed: {e}")

    return rep_pk, rep_field_id, rep_smg_id


def _detect_assignment_table():
    """
    Find a mapping table that links 'prefilled_doctor' to a field‑rep id.
    Returns (table_name, doctor_col, rep_col) or None if not found.
    """
    from django.db import connection
    doctor_candidates = ('prefilled_doctor_id', 'doctor_id', 'doctor_fk')
    rep_candidates    = ('fieldrep_id', 'field_rep_id', 'rep_id',
                         'representative_id', 'field_representative_id')

    try:
        with connection.cursor() as cursor:
            # Step 1: find tables that have a doctor column
            cursor.execute("""
                SELECT DISTINCT table_name
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND column_name IN %s
            """, [doctor_candidates])
            doctor_tables = [r[0] for r in cursor.fetchall()]

            # Step 2: for each such table, check if it also has a rep column
            for tbl in doctor_tables:
                cursor.execute("""
                    SELECT LOWER(column_name)
                    FROM information_schema.columns
                    WHERE table_schema = DATABASE()
                      AND table_name = %s
                """, [tbl])
                cols = {r[0] for r in cursor.fetchall()}
                doc_col = next((c for c in doctor_candidates if c in cols), None)
                rep_col = next((c for c in rep_candidates if c in cols), None)
                if doc_col and rep_col:
                    return (tbl, doc_col, rep_col)
    except Exception as e:
        print(f"[info] assignment table detection failed: {e}")

    return None


def _fetch_assigned_prefilled_doctors(rep_pk, rep_field_id, rep_smg_id):
    """
    Return rows = [(id, full_name, phone, email, specialty, city), ...]
    Order of attempts:
      1) Use detected mapping table with (doctor_col, rep_col).
         Prefer rep_smg_id if the rep_col looks numeric; else rep_field_id.
      2) Filter directly on prefilled_doctor using common rep columns (int)
      3) Filter directly on prefilled_doctor using common field_id columns (str)
    """
    from django.db import connection

    # 1) Mapping table join (auto‑detected)
    detected = _detect_assignment_table()
    if detected:
        tbl, doctor_col, rep_col = detected
        try:
            with connection.cursor() as cursor:
                # Heuristic: if we have a numeric SMG rep id, try it first
                bind_val = rep_smg_id if rep_smg_id is not None else rep_pk
                # If we still don't have a numeric id, try field‑id string
                if bind_val is None and rep_field_id:
                    bind_val = rep_field_id

                cursor.execute(f"""
                    SELECT d.id, d.full_name, d.phone, d.email, d.specialty, d.city
                    FROM prefilled_doctor AS d
                    INNER JOIN {tbl} AS m ON m.{doctor_col} = d.id
                    WHERE m.{rep_col} = %s
                    ORDER BY d.full_name
                """, [bind_val])
                rows = cursor.fetchall()
                if rows:
                    print(f"[info] Using mapping table {tbl} via {rep_col} with value {bind_val}")
                    return rows
        except Exception as e:
            print(f"[info] mapping‑table join failed ({tbl}): {e}")

    # 2) Direct numeric rep id columns on prefilled_doctor
    for col in ("rep_id", "field_rep_id", "assigned_rep_id"):
        if rep_smg_id is None and rep_pk is None:
            break
        try:
            val = rep_smg_id if rep_smg_id is not None else rep_pk
            with connection.cursor() as cursor:
                cursor.execute(f"""
                    SELECT id, full_name, phone, email, specialty, city
                    FROM prefilled_doctor
                    WHERE {col} = %s
                    ORDER BY full_name
                """, [val])
                rows = cursor.fetchall()
                if rows:
                    print(f"[info] Using prefilled_doctor.{col} = {val}")
                    return rows
        except Exception:
            pass

    # 3) Direct string field‑id columns on prefilled_doctor
    for col in ("assigned_field_id", "field_id", "owner_field_id"):
        if not rep_field_id:
            break
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"""
                    SELECT id, full_name, phone, email, specialty, city
                    FROM prefilled_doctor
                    WHERE {col} = %s
                    ORDER BY full_name
                """, [rep_field_id])
                rows = cursor.fetchall()
                if rows:
                    print(f"[info] Using prefilled_doctor.{col} = {rep_field_id}")
                    return rows
        except Exception:
            pass

    # No matches
    return []
def prefilled_fieldrep_whatsapp_share_collateral(request, brand_campaign_id=None):
    import urllib.parse
    from django.utils import timezone
    
    # Debug: Print incoming brand_campaign_id
    print(f"[DEBUG] Incoming brand_campaign_id: {brand_campaign_id}")
    print(f"[DEBUG] POST data: {request.POST}")
    
    brand_campaign_id = request.POST.get('brand_campaign_id') or brand_campaign_id
    print(f"[DEBUG] Final brand_campaign_id: {brand_campaign_id}")
    
    # Get user info from session
    field_rep_id = request.session.get('field_rep_id')
    field_rep_email = request.session.get('field_rep_email')
    field_rep_field_id = request.session.get('field_rep_field_id')
    uid = _current_fieldrep_user_id(request)
    if not field_rep_id:
        messages.error(request, 'Please login first.')
        return redirect('fieldrep_login')
    
    # Get doctors assigned to THIS field rep (from admin dashboard)
    try:
        from doctor_viewer.models import Doctor
        from user_management.models import User
        
        # Get the field rep user object by field_id (since field_rep_id is from FieldRepresentative table)
        field_rep_user = None
        if field_rep_field_id:
            try:
                field_rep_user = User.objects.get(field_id=field_rep_field_id, role='field_rep')
            except User.DoesNotExist:
                if field_rep_email:
                    try:
                        field_rep_user = User.objects.filter(email=field_rep_email, role='field_rep').first()
                    except:
                        pass
        
        doctors_list = []
        if field_rep_user:
            assigned_doctors = Doctor.objects.filter(rep=field_rep_user)
            doctors_list = [
                {
                    'id': doc.id,
                    'name': doc.name,
                    'phone': doc.phone or '',
                    'email': '',
                    'specialty': '',
                    'city': '',
                }
                for doc in assigned_doctors
            ]
        
        if not doctors_list:
            try:
                rep_pk, rep_field_id, rep_smg_id = _get_current_rep_ids(request)
                doctors_data = _fetch_assigned_prefilled_doctors(rep_pk, rep_field_id, rep_smg_id)
                doctors_list = [
                    {
                        'id': d[0],
                        'name': d[1],
                        'phone': d[2],
                        'email': d[3],
                        'specialty': d[4],
                        'city': d[5],
                    }
                    for d in doctors_data
                ]
            except Exception:
                pass
        
        if not doctors_list:
            messages.info(request, "No doctors are assigned to your account.")
    except Exception:
        doctors_list = []
        
    
    # Get real collaterals from database
    try:
        from collateral_management.models import Collateral, CampaignCollateral
        from user_management.models import User
        from campaign_management.models import CampaignCollateral as CMCampaignCollateral, CampaignAssignment
        
        # Initialize empty list for collaterals
        collaterals = []
        
        # Get the field rep's assigned campaigns if no specific brand_campaign_id is provided
        if not brand_campaign_id or brand_campaign_id == 'all':
            # Try to get from session first
            brand_campaign_id = request.session.get('brand_campaign_id')
            
            # If still no campaign ID, get the first assigned campaign for this field rep
            if not brand_campaign_id and field_rep_field_id:
                try:
                    assignment = CampaignAssignment.objects.filter(
                        field_rep__field_id=field_rep_field_id
                    ).select_related('campaign').first()
                    
                    if assignment and assignment.campaign:
                        brand_campaign_id = assignment.campaign.brand_campaign_id
                        request.session['brand_campaign_id'] = brand_campaign_id
                except Exception as e:
                    print(f"Error getting assigned campaign: {e}")
        
        if brand_campaign_id and brand_campaign_id != 'all':
            print(f"[DEBUG] Filtering collaterals for brand_campaign_id: {brand_campaign_id}")
            
            # First from campaign_management.CampaignCollateral
            cc_links = CMCampaignCollateral.objects.filter(
                campaign__brand_campaign_id=brand_campaign_id
            ).select_related('collateral', 'campaign')
            print(f"[DEBUG] Found {len(cc_links)} campaign collaterals from campaign_management")
            
            campaign_collaterals = [link.collateral for link in cc_links if link.collateral and link.collateral.is_active]
            print(f"[DEBUG] After filtering, {len(campaign_collaterals)} active campaign collaterals")
            
            # Then from collateral_management.CampaignCollateral
            collateral_links = CampaignCollateral.objects.filter(
                campaign__brand_campaign_id=brand_campaign_id
            ).select_related('collateral', 'campaign')
            print(f"[DEBUG] Found {len(collateral_links)} collaterals from collateral_management")
            
            collateral_collaterals = [link.collateral for link in collateral_links if link.collateral and link.collateral.is_active]
            print(f"[DEBUG] After filtering, {len(collateral_collaterals)} active collaterals from collateral_management")
            
            # Combine and deduplicate collaterals
            all_collaterals = campaign_collaterals + collateral_collaterals
            print(f"[DEBUG] Total collaterals before deduplication: {len(all_collaterals)}")
            
            collaterals = list({c.id: c for c in all_collaterals}.values())
            print(f"[DEBUG] Total unique collaterals after deduplication: {len(collaterals)}")
            
            # If no collaterals found, show a message
            if not collaterals:
                messages.info(request, f"No collaterals found for campaign {brand_campaign_id}")
        else:
            # Show all active collaterals if no brand campaign ID provided and no assigned campaign found
            collaterals = Collateral.objects.filter(is_active=True).order_by('-created_at')
            collaterals_list = [{'id': c.id, 'name': c.name} for c in collaterals]
            
            # Debug output
            print(f"[DEBUG] Found {len(doctors_list)} doctors and {len(collaterals_list)} collaterals")
            
            # Ensure we have a list, even if empty
            collaterals = list(collaterals) if collaterals else []
            
            # Pick latest by default
            latest_collateral_id = collaterals[0].id if collaterals else None
            selected_collateral_id = int(request.POST.get('collateral')) if request.method == 'POST' and request.POST.get('collateral') else latest_collateral_id
            
            # Resolve a user for short link creation
            try:
                actual_user = User.objects.get(field_id=field_rep_field_id, role='field_rep')
            except User.DoesNotExist:
                actual_user = request.user if request.user.is_authenticated else None
            
            collaterals_list = []
            for collateral in collaterals:
                short_link = find_or_create_short_link(collateral, actual_user)
                # Handle both collateral models - campaign_management and collateral_management
                collateral_name = getattr(collateral, 'title', getattr(collateral, 'item_name', 'Unknown'))
                collateral_description = getattr(collateral, 'description', '')
                collaterals_list.append({
                    'id': collateral.id,
                    'name': collateral_name,
                    'description': collateral_description,
                    'link': request.build_absolute_uri(f"/shortlinks/go/{short_link.short_code}/")
                })
            
            # Sort collaterals by creation date (newest first)
            collaterals_list.sort(key=lambda x: next((c.created_at for c in collaterals if c.id == x['id']), timezone.now()), reverse=True)
        latest_collateral_id = collaterals[0].id if collaterals else None
        selected_collateral_id = int(request.POST.get('collateral')) if request.method == 'POST' and request.POST.get('collateral') else latest_collateral_id
        
        # Resolve a user for short link creation
        try:
            actual_user = User.objects.get(field_id=field_rep_field_id, role='field_rep')
        except User.DoesNotExist:
            actual_user = request.user if request.user.is_authenticated else None
        
        collaterals_list = []
        for collateral in collaterals:
            short_link = find_or_create_short_link(collateral, actual_user)
            # Handle both collateral models - campaign_management and collateral_management
            collateral_name = getattr(collateral, 'title', getattr(collateral, 'item_name', 'Unknown'))
            collateral_description = getattr(collateral, 'description', '')
            collaterals_list.append({
                'id': collateral.id,
                'name': collateral_name,
                'description': collateral_description,
                'link': request.build_absolute_uri(f"/shortlinks/go/{short_link.short_code}/")
            })
        
        # Sort collaterals by creation date (newest first)
        collaterals_list.sort(key=lambda x: next((c.created_at for c in collaterals if c.id == x['id']), timezone.now()), reverse=True)
    except Exception:
        collaterals_list = []
        selected_collateral_id = None
        messages.error(request, 'Error loading collaterals. Please try again.')
    
    # Build per-doctor status for selected collateral
    status_by_doctor = {}
    try:
        from django.db.models import Max
        from .models import ShareLog
        from doctor_viewer.models import DoctorEngagement
        from shortlink_management.models import ShortLink
        
        if selected_collateral_id:
            # For each doctor, determine status
            now = timezone.now()
            for d in doctors_list:
                phone = d['phone']
                sl = ShareLog.objects.filter(
                    field_rep_id=field_rep_id,
                    collateral_id=selected_collateral_id,
                    doctor_identifier=phone
                ).order_by('-created_at').first()
                if not sl:
                    status = 'not_sent'
                else:
                    days = (now - sl.created_at).days
                    engaged = DoctorEngagement.objects.filter(short_link_id=sl.short_link_id).exists()
                    if engaged:
                        status = 'opened'
                    elif days >= 6:
                        status = 'reminder'
                    else:
                        status = 'sent'
                status_by_doctor[d['id']] = status
        # attach status onto each doctor dict for easy template access
        for d in doctors_list:
            d['status'] = status_by_doctor.get(d['id'], 'unknown')
    except Exception:
        for d in doctors_list:
            d['status'] = 'unknown'

    if request.method == 'POST':
        try:
            doctor_id_str = request.POST.get('doctor_id', '').strip()
            collateral_id_str = request.POST.get('collateral', '').strip()
            
            if not doctor_id_str or not collateral_id_str:
                messages.error(request, 'Please select both doctor and collateral.')
                return redirect('prefilled_fieldrep_whatsapp_share_collateral')
            
            doctor_id = int(doctor_id_str)
            collateral_id = int(collateral_id_str)
            
            selected_doctor = next((d for d in doctors_list if d['id'] == doctor_id), None)
            selected_collateral = next((c for c in collaterals_list if c['id'] == collateral_id), None)
            
            if not selected_doctor or not selected_collateral:
                messages.error(request, 'Invalid selection.')
                return redirect('prefilled_fieldrep_whatsapp_share_collateral')
            
            from .utils.db_operations import share_prefilled_doctor
            from collateral_management.models import Collateral
            from user_management.models import User
            
            try:
                actual_user = User.objects.get(field_id=field_rep_field_id, role='field_rep')
            except User.DoesNotExist:
                actual_user = request.user if request.user.is_authenticated else None
            if not actual_user:
                messages.error(request, 'Unable to create user for short link. Please try again.')
                return redirect('prefilled_fieldrep_whatsapp_share_collateral')
            
            collateral_obj = Collateral.objects.get(id=collateral_id)
            short_link = find_or_create_short_link(collateral_obj, actual_user)
            
            success = share_prefilled_doctor(
                rep_id=actual_user.id,
                prefilled_doctor_id=doctor_id,
                short_link_id=short_link.id,
                collateral_id=collateral_id
            )
            
            if success:
                message = get_brand_specific_message(collateral_id, selected_collateral['name'], selected_collateral['link'])
                clean_phone = selected_doctor['phone'].replace('+91', '').replace('+', '').replace(' ', '').replace('-', '')
                wa_url = f"https://wa.me/91{clean_phone}?text={urllib.parse.quote(message)}"
                messages.success(request, f"Message sent to {selected_doctor['name']}")
                return redirect(wa_url)
            messages.error(request, 'Error sharing collateral. Please try again.')
            return redirect('prefilled_fieldrep_whatsapp_share_collateral')
        except Exception:
            messages.error(request, 'Error sharing collateral. Please try again.')
            return redirect('prefilled_fieldrep_whatsapp_share_collateral')
    
    return render(request, 'sharing_management/prefilled_fieldrep_whatsapp_share_collateral.html', {
        'fieldrep_id': field_rep_field_id or 'Unknown',
        'fieldrep_email': field_rep_email,
        'doctors': doctors_list,
        'collaterals': collaterals_list,
        'selected_collateral_id': selected_collateral_id,
        'status_by_doctor': status_by_doctor,
        'brand_campaign_id': brand_campaign_id,
    })

@csrf_exempt
def get_doctor_status(doctor, collateral):
    """Determine the status of a doctor for a given collateral"""
    # Check if collateral was shared
    share_log = ShareLog.objects.filter(
        doctor_identifier=doctor.phone,
        collateral=collateral
    ).order_by('-share_timestamp').first()
    
    if not share_log:
        return 'not_shared'
    
    # Check if doctor has engaged with the content
    engagement = DoctorEngagement.objects.filter(
        short_link__resource_id=collateral.id,
        short_link__resource_type='collateral',
        doctor=doctor
    ).first()
    
    if engagement:
        return 'viewed'
    
    # Check if it's time for a reminder (6+ days since sharing)
    six_days_ago = timezone.now() - timedelta(days=6)
    if share_log.share_timestamp <= six_days_ago:
        return 'needs_reminder'
    
    return 'shared'

def get_doctor_status_class(status):
    """Return the appropriate CSS class for each status"""
    return {
        'not_shared': 'btn-danger',
        'shared': 'btn-warning',
        'needs_reminder': 'btn-purple',
        'viewed': 'btn-success'
    }.get(status, 'btn-secondary')

def get_doctor_status_text(status):
    """Return the appropriate button text for each status"""
    return {
        'not_shared': 'Send Message',
        'shared': 'Sent',
        'needs_reminder': 'Send Reminder',
        'viewed': 'Viewed'
    }.get(status, 'Unknown')

def doctor_list(request, campaign_id=None):
    """View to display doctors with their sharing status for a campaign"""
    # Get the current user (field rep)
    user = request.user
    
    # Get the campaign if provided
    campaign = None
    if campaign_id:
        campaign = get_object_or_404(CampaignAssignment, id=campaign_id)
    
    # Get the selected collateral (from GET or POST)
    collateral_id = request.GET.get('collateral') or request.POST.get('collateral')
    if not collateral_id and request.method == 'GET':
        # Get the most recent collateral if none selected
        latest_collateral = Collateral.objects.filter(
            is_active=True
        ).order_by('-created_at').first()
        if latest_collateral:
            collateral_id = latest_collateral.id
    
    collateral = None
    if collateral_id:
        collateral = get_object_or_404(Collateral, id=collateral_id)
    
    # Get assigned doctors for the campaign or all doctors for the rep
    if campaign:
        doctors = Doctor.objects.filter(
            Q(rep=user) | 
            Q(campaignassignment=campaign)
        ).distinct()
    else:
        doctors = Doctor.objects.filter(rep=user)
    
    # Annotate with sharing status if collateral is selected
    doctor_statuses = []
    if collateral:
        for doctor in doctors:
            status = get_doctor_status(doctor, collateral)
            doctor_statuses.append({
                'doctor': doctor,
                'status': status,
                'status_class': get_doctor_status_class(status),
                'status_text': get_doctor_status_text(status),
                'last_shared': ShareLog.objects.filter(
                    doctor_identifier=doctor.phone,
                    collateral=collateral
                ).order_by('-share_timestamp').first()
            })
    
    context = {
        'doctors': doctor_statuses if collateral else [],
        'collateral': collateral,
        'campaign': campaign,
        'all_collaterals': Collateral.objects.filter(is_active=True).order_by('-created_at'),
    }
    
    return render(request, 'sharing_management/doctor_list.html', context)


def video_tracking(request):
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    transaction_id = request.POST.get('collateral_sharing')
    user_id = request.POST.get('userId')
    video_status = request.POST.get('status')
    comment = "Video Viewed"

    if not (transaction_id and user_id and video_status):
        return HttpResponseBadRequest("Missing required parameters.")

    # Determine video progress percentage
    if video_status == '1':
        video_percentage = '1'  # 0-50%
    elif video_status == '2':
        video_percentage = '2'  # 50%-99%
    elif video_status == '3':
        video_percentage = '3'  # 100%
    else:
        return HttpResponseBadRequest("Invalid video status.")

    try:
        share_log = ShareLog.objects.get(id=transaction_id)
    except ShareLog.DoesNotExist:
        return HttpResponseBadRequest("Transaction not found in ShareLog table.")

    exists = VideoTrackingLog.objects.filter(
        share_log=share_log,
        user_id=user_id,
        video_percentage=video_percentage
    ).exists()

    if not exists:
        video_log = VideoTrackingLog.objects.create(
            share_log=share_log,
            user_id=user_id,
            video_status=video_status,
            video_percentage=video_percentage,
            comment=comment
        )
        # Tiny, safe hook: record transaction-level video event
        try:
            sl = ShareLog.objects.get(id=video_log.share_log_id)
            pct = int(float(video_log.video_percentage)) if video_log.video_percentage else 0
            mark_video_event(
                sl,
                status=int(video_log.video_status),
                percentage=pct,
                event_id=video_log.id,
                when=getattr(video_log, 'created_at', timezone.now()),
            )
        except ShareLog.DoesNotExist:
            pass
        return JsonResponse({"status": "success", "msg": "New video tracking log inserted successfully."})
    else:
        return JsonResponse({"status": "exists", "msg": "This video progress state has already been recorded."})

def bulk_pre_mapped_by_login(request):
    if request.method == "POST":
        form = BulkPreMappedByLoginForm(request.POST, request.FILES)
        if form.is_valid():
            result = form.save(admin_user=request.user)
            if result["created"] or result.get("updated"):
                messages.success(
                    request,
                    f"Data is uploaded successfully. Doctors created: {result['created']}. Mappings created/updated: {result.get('updated', 0)}."
                )
            for err in result["errors"]:
                messages.error(request, err)
            return render(
                request,
                "sharing_management/bulk_premapped_login_success.html",
                result
            )
    else:
        form = BulkPreMappedByLoginForm()
    return render(
        request,
        "sharing_management/bulk_premapped_login_upload.html",
        {"form": form}
    )

def bulk_pre_mapped_by_login_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=premapped_by_login_registration.csv"
    w = csv.writer(response)
    # Header: Doctor Name, Gmail ID, Field Rep ID
    w.writerow(["Doctor Name", "Gmail ID", "Field Rep ID"])
    # Example row
    w.writerow(["Dr John Doe", "rep1@gmail.com", "FR1234"])
    return response

def debug_collaterals(request):
    """Debug view to show available collaterals"""
    from collateral_management.models import Collateral
    from django.contrib.auth import get_user_model
    
    UserModel = get_user_model()
    
    collaterals = Collateral.objects.all()[:20]  # Limit to first 20
    field_reps = UserModel.objects.filter(role="field_rep")[:10]  # Limit to first 10
    
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
    """
    View to handle collateral deletion from the field rep dashboard.
    Soft deletes the collateral by setting is_active to False.
    """
    print(f"DEBUG: Delete request received for collateral ID: {pk}")
    print(f"DEBUG: Request method: {request.method}")
    print(f"DEBUG: Request POST data: {request.POST}")
    print(f"DEBUG: Request GET data: {request.GET}")
    
    if request.method == 'POST':
        try:
            # Get the collateral
            from collateral_management.models import Collateral
            from django.core.exceptions import ObjectDoesNotExist
            
            print(f"DEBUG: Attempting to get collateral with ID: {pk}")
            try:
                collateral = Collateral.objects.get(pk=pk, is_active=True)
                print(f"DEBUG: Found collateral: {collateral}")
                
                # Soft delete by setting is_active to False
                print("DEBUG: Soft deleting collateral...")
                collateral.is_active = False
                collateral.save()
                print("DEBUG: Collateral soft deleted successfully")
                
                messages.success(request, 'Collateral has been deleted successfully.')
            except ObjectDoesNotExist:
                print(f"DEBUG: Collateral with ID {pk} not found or already deleted")
                messages.warning(request, 'This collateral has already been deleted or does not exist.')
            
            # Get campaign filter from either POST or GET parameters
            campaign_filter = request.POST.get('campaign') or request.GET.get('campaign', '')
            print(f"DEBUG: Campaign filter: {campaign_filter}")
            
            if campaign_filter:
                redirect_url = f"{reverse('fieldrep_dashboard')}?campaign={campaign_filter}"
                print(f"DEBUG: Redirecting to: {redirect_url}")
                return redirect(redirect_url)
            return redirect('fieldrep_dashboard')
            
        except Exception as e:
            error_msg = f'Error deleting collateral: {str(e)}'
            print(f"ERROR: {error_msg}")
            messages.error(request, error_msg)
            campaign_filter = request.POST.get('campaign') or request.GET.get('campaign', '')
            if campaign_filter:
                return redirect(f"{reverse('fieldrep_dashboard')}?campaign={campaign_filter}")
            return redirect('fieldrep_dashboard')
    
    # If not a POST request, redirect to dashboard with campaign filter if it exists
    print("DEBUG: Not a POST request, redirecting to dashboard")
    campaign_filter = request.GET.get('campaign', '')
    if campaign_filter:
        return redirect(f"{reverse('fieldrep_dashboard')}?campaign={campaign_filter}")
    return redirect('fieldrep_dashboard')
