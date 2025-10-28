from __future__ import annotations

import csv
from urllib.parse import quote
import urllib.parse

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpResponse, HttpRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db import connection
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest
from .models import ShareLog, VideoTrackingLog

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
from collateral_management.models import Collateral
from campaign_management.models import CampaignCollateral
from doctor_viewer.models import DoctorEngagement
from shortlink_management.models import ShortLink
from shortlink_management.utils import generate_short_code
from utils.recaptcha import recaptcha_required
from .forms import CollateralForm
from campaign_management.forms import CampaignCollateralForm
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


@field_rep_required
def fieldrep_dashboard(request):
    rep = request.user
    assigned = CampaignAssignment.objects.filter(field_rep=rep).select_related('campaign')
    campaign_ids = [a.campaign_id for a in assigned]

    share_cnts = ShareLog.objects.filter(
        field_rep=rep,
        short_link__resource_type='collateral',
        short_link__resource_id__in=CampaignCollateral.objects.filter(
            campaign_id__in=campaign_ids
        ).values_list('collateral_id', flat=True)
    ).values('short_link__resource_id').annotate(cnt=Count('id'))
    share_map = {r['short_link__resource_id']: r['cnt'] for r in share_cnts}

    pdf_cnts = DoctorEngagement.objects.filter(
        short_link__resource_type='collateral',
        last_page_scrolled__gt=0,
        short_link__resource_id__in=CampaignCollateral.objects.filter(
            campaign_id__in=campaign_ids
        ).values_list('collateral_id', flat=True)
    ).values('short_link__resource_id').annotate(cnt=Count('id'))
    pdf_map = {r['short_link__resource_id']: r['cnt'] for r in pdf_cnts}

    vid_cnts = DoctorEngagement.objects.filter(
        video_watch_percentage__gte=90,
        short_link__resource_type='collateral',
        short_link__resource_id__in=CampaignCollateral.objects.filter(
            campaign_id__in=campaign_ids
        ).values_list('collateral_id', flat=True)
    ).values('short_link__resource_id').annotate(cnt=Count('id'))
    vid_map = {r['short_link__resource_id']: r['cnt'] for r in vid_cnts}

    stats = []
    for a in assigned:
        campaign = a.campaign
        campaign_collaterals = CampaignCollateral.objects.filter(campaign=campaign)
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

    # Use campaign_management Collateral here to match the FK on CampaignCollateral
    from campaign_management.models import Collateral as CampaignMgmtCollateral
    all_collaterals = CampaignMgmtCollateral.objects.all()
    
    # Add search functionality
    search_query = request.GET.get('search', '').strip()
    if search_query:
        # Filter collaterals by brand campaign ID
        filtered_collaterals = []
        for c in all_collaterals:
            cc = CampaignCollateral.objects.filter(collateral=c).first()
            campaign = cc.campaign if cc else None
            brand_id = campaign.brand_campaign_id if campaign else ''
            
            if search_query.lower() in brand_id.lower():
                filtered_collaterals.append(c)
        all_collaterals = filtered_collaterals
    
    # Read submissions.csv to get the correct IDs
    import pandas as pd
    import os
    csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'submissions.csv')
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        # If file not found, create an empty DataFrame to avoid errors
        df = pd.DataFrame(columns=['id', 'ItemName', 'Brand_Campaign_ID'])
        print(f"Warning: submissions.csv not found at {csv_path}")
    except Exception as e:
        # For any other error, create an empty DataFrame
        df = pd.DataFrame(columns=['id', 'ItemName', 'Brand_Campaign_ID'])
        print(f"Error reading submissions.csv: {e}")
    
    collaterals = []
    for c in all_collaterals:
        cc = CampaignCollateral.objects.filter(collateral=c).first()
        # Get campaign through CampaignCollateral relationship
        campaign = cc.campaign if cc else None
        
        # Find the corresponding CSV ID based on item name and brand campaign ID
        csv_id = None
        if campaign:
            matching_rows = df[(df['ItemName'] == c.item_name) & (df['Brand_Campaign_ID'] == campaign.brand_campaign_id)]
            if not matching_rows.empty:
                csv_id = matching_rows.iloc[0]['id']
        
        collaterals.append({
            'brand_id': campaign.brand_campaign_id if campaign else '',
            'item_name': c.item_name,  # Use item_name field from campaign_management model
            'description': c.description,
            'url': c.file.url if c.file else (c.vimeo_url or ''),
            'id': csv_id if csv_id else c.id,  # Use CSV ID if found, otherwise fallback to campaign management ID
            'campaign_collateral_id': cc.pk if cc else None,
        })
    
    return render(request, 'sharing_management/fieldrep_dashboard.html', {
        'stats': stats, 
        'collaterals': collaterals,
        'search_query': search_query
    })


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
                    messages.success(request, f"{created} rows imported successfully.")
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
    response["Content-Disposition"] = "attachment; filename=bulk_manual_template.csv"
    writer = csv.writer(response)
    
    # Write header row
    writer.writerow([
        "field_rep_email",
        "doctor_name", 
        "doctor_contact",
        "collateral_id",
        "share_channel",
        "message_text",
    ])
    
    # Get actual field rep users from database
    from django.contrib.auth import get_user_model
    UserModel = get_user_model()
    
    try:
        # Try to get a real field rep user
        field_rep = UserModel.objects.filter(role="field_rep").first()
        rep_email = field_rep.email if field_rep else "bhartidhote8@gmail.com"
    except:
        rep_email = "bhartidhote8@gmail.com"
    
    # Get actual collateral ID
    try:
        from collateral_management.models import Collateral
        collateral = Collateral.objects.filter(is_active=True).first()
        col_id = str(collateral.id) if collateral else "1"
        print(f"DEBUG: Using collateral ID {col_id} for template")
        if not collateral:
            # If no active collaterals, try any collateral
            collateral = Collateral.objects.first()
            col_id = str(collateral.id) if collateral else "1"
            print(f"DEBUG: No active collaterals, using any collateral ID {col_id}")
    except Exception as e:
        print(f"DEBUG: Error getting collateral: {e}")
        col_id = "1"
    
    writer.writerow([
        rep_email,
        "Dr John Doe", 
        "+919812345678",
        col_id,
        "WhatsApp",
        "Hi Doctor, please see this.",
    ])
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
                messages.success(request, f"{created} rows imported successfully.")
                return redirect("bulk_upload_success")
            for err in errors:
                messages.error(request, err)
            return redirect("bulk_pre_mapped_upload")
    else:
        form = BulkPreMappedUploadForm()
    return render(request, "sharing_management/bulk_premapped_upload.html", {"form": form})


def bulk_pre_mapped_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=premapped_template.csv"
    writer = csv.writer(response)
    writer.writerow(["doctor_name", "whatsapp_number", "fieldrep_id", "collateral_id"])
    writer.writerow(["Dr Jane Doe", "+919999998888", "42", "99"])
    return response

# ─── Bulk manual (WhatsApp‑only) UI ──────────────────────────────────────────
def bulk_manual_upload_whatsapp(request):
    if request.method == "POST":
        form = BulkManualWhatsappShareForm(request.POST, request.FILES)
        if form.is_valid():
            created, errors = form.save(user_request=request.user)
            if created:
                messages.success(request, f"{created} WhatsApp rows imported successfully.")
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
    Example CSV for WhatsApp‑only bulk upload.
    """
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=bulk_manual_whatsapp_template.csv"
    writer = csv.writer(response)
    
    # Write header row
    writer.writerow([
        "field_rep_email",
        "doctor_name",
        "whatsapp_number",
        "collateral_id",
        "message_text",
    ])
    
    writer.writerow([
        "rep@example.com",
        "Dr Jane Doe",
        "+919876543210",
        "42",                  # collateral_id
        "Hi Doctor, please see this.",
    ])
    return response
def bulk_pre_filled_share_whatsapp(request):
    from .forms import BulkPreFilledWhatsappShareForm

    if request.method == "POST":
        form = BulkPreFilledWhatsappShareForm(request.POST, request.FILES)
        if form.is_valid():
            result = form.save(admin_user=request.user)
            if result["created"]:
                messages.success(request, f"{result['created']} rows shared.")
            for err in result["errors"]:
                messages.error(request, err)
            return redirect("bulk_pre_filled_share_whatsapp")
    else:
        form = BulkPreFilledWhatsappShareForm()

    return render(request, "sharing_management/bulk_prefilled_whatsapp_upload.html", {"form": form})

def bulk_prefilled_whatsapp_template_csv(request):
    """
    Download CSV template for bulk prefilled WhatsApp sharing
    """
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="bulk_prefilled_whatsapp_template.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['doctor_name', 'whatsapp_number', 'fieldrep_id', 'collateral_id', 'message_text'])
    writer.writerow(['Dr. John Doe', '+919876543210', '1', '42', 'Hi Doctor, please check this content.'])
    writer.writerow(['Dr. Jane Smith', '+919876543211', '2', '43', 'Hello Doctor, here is some useful information.'])
    
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
    from campaign_management.models import CampaignCollateral
    
    # Get existing campaign collateral records
    campaign_collaterals = CampaignCollateral.objects.select_related('campaign', 'collateral').all()
    
    # Check if we're editing an existing record
    edit_id = request.GET.get('id')
    print(f"Edit ID from URL: {edit_id}")
    if edit_id:
        try:
            existing_record = CampaignCollateral.objects.get(id=edit_id)
            if request.method == 'POST':
                print(f"POST data: {request.POST}")
                form = CampaignCollateralForm(request.POST, instance=existing_record)
                print(f"Form is valid: {form.is_valid()}")
                if form.is_valid():
                    print(f"Form cleaned_data: {form.cleaned_data}")
                    saved_instance = form.save()
                    print(f"Saved instance: {saved_instance}")
                    print(f"Start date: {saved_instance.start_date}, End date: {saved_instance.end_date}")
                    messages.success(request, 'Calendar dates updated successfully.')
                    return redirect(f'/share/edit-calendar/?id={edit_id}')
                else:
                    print(f"Form errors: {form.errors}")
                    # Add form errors to messages for debugging
                    for field, errors in form.errors.items():
                        for error in errors:
                            messages.error(request, f'{field}: {error}')
            else:
                form = CampaignCollateralForm(instance=existing_record)
        except CampaignCollateral.DoesNotExist:
            messages.error(request, 'Record not found.')
            return redirect('edit_campaign_calendar')
    else:
        # No ID provided - handle form submission to update existing records
        if request.method == 'POST':
            collateral_id = request.POST.get('collateral')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            
            print(f"POST data - Collateral ID: {collateral_id}, Start: {start_date}, End: {end_date}")
            
            if collateral_id:
                # Find existing CampaignCollateral record with this collateral
                existing_record = CampaignCollateral.objects.filter(collateral_id=collateral_id).first()
                
                if existing_record:
                    # Update existing record
                    form = CampaignCollateralForm(request.POST, instance=existing_record)
                    if form.is_valid():
                        print(f"Updating existing record: {existing_record}")
                        form.save()
                        messages.success(request, 'Calendar dates updated successfully!')
                        return redirect('edit_campaign_calendar')
                    else:
                        print(f"Form errors: {form.errors}")
                        for field, errors in form.errors.items():
                            for error in errors:
                                messages.error(request, f'{field}: {error}')
                else:
                    # Create new record
                    form = CampaignCollateralForm(request.POST)
                    if form.is_valid():
                        instance = form.save(commit=False)
                        
                        # Set campaign from first available campaign
                        from campaign_management.models import Campaign
                        first_campaign = Campaign.objects.first()
                        if first_campaign:
                            instance.campaign = first_campaign
                            instance.save()
                            messages.success(request, 'New campaign collateral created successfully!')
                            return redirect('edit_campaign_calendar')
                        else:
                            messages.error(request, 'No campaigns available. Please create a campaign first.')
            else:
                messages.error(request, 'Please select a collateral.')
        
        # Show empty form
        form = CampaignCollateralForm()
    
    return render(request, 'sharing_management/edit_calendar.html', {
        'form': form,
        'campaign_collaterals': campaign_collaterals,
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
    
    # Fetch security questions from database
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, question FROM security_question ORDER BY id")
            security_questions = cursor.fetchall()
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



def fieldrep_share_collateral(request):
    # Get user info from session
    field_rep_id = request.session.get('field_rep_id')
    field_rep_email = request.session.get('field_rep_email')
    field_rep_field_id = request.session.get('field_rep_field_id')
    
    if not field_rep_id:
        messages.error(request, 'Please login first.')
        return redirect('fieldrep_login')
    
    # Get real collaterals from database
    try:
        from collateral_management.models import Collateral
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
        'collaterals': collaterals_list
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
                    messages.success(request, 'Registration successful! Please login with your credentials.')
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

def prefilled_fieldrep_share_collateral(request):
    import urllib.parse
    
    # Get user info from session
    field_rep_id = request.session.get('field_rep_id')
    field_rep_email = request.session.get('field_rep_email')
    field_rep_field_id = request.session.get('field_rep_field_id')
    
    if not field_rep_id:
        messages.error(request, 'Please login first.')
        return redirect('fieldrep_login')
    
    # Get real prefilled doctors from database
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, full_name, phone, email, specialty, city
                FROM prefilled_doctor
                ORDER BY full_name
            """)
            doctors_data = cursor.fetchall()
            
        doctors_list = []
        for doctor in doctors_data:
            doctors_list.append({
                'id': doctor[0],
                'name': doctor[1],
                'phone': doctor[2],
                'email': doctor[3],
                'specialty': doctor[4],
                'city': doctor[5]
            })
    except Exception as e:
        print(f"Error fetching prefilled doctors: {e}")
        doctors_list = []
        messages.error(request, 'Error loading doctors. Please try again.')
    
    # Get real collaterals from database
    try:
        from collateral_management.models import Collateral
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
        doctor_id = int(request.POST.get('doctor_id'))
        collateral_id = int(request.POST.get('collateral'))
        
        # Find the selected doctor and collateral
        selected_doctor = next((d for d in doctors_list if d['id'] == doctor_id), None)
        selected_collateral = next((c for c in collaterals_list if c['id'] == collateral_id), None)
        
        if selected_doctor and selected_collateral:
            try:
                from .utils.db_operations import share_prefilled_doctor
                from collateral_management.models import Collateral
                
                # Get the short link for this collateral
                collateral_obj = Collateral.objects.get(id=collateral_id)
                short_link = find_or_create_short_link(collateral_obj, request.user)
                
                # Share the prefilled doctor
                success = share_prefilled_doctor(
                    rep_id=field_rep_id,
                    prefilled_doctor_id=doctor_id,
                    short_link_id=short_link.id,
                    collateral_id=collateral_id
                )
                
                if success:
                    # Get brand-specific message
                    message = get_brand_specific_message(collateral_id, selected_collateral['name'], selected_collateral['link'])
                    wa_url = f"https://wa.me/91{selected_doctor['phone']}?text={urllib.parse.quote(message)}"
                    
                    messages.success(request, f'Collateral shared successfully with {selected_doctor["name"]}!')
                    return redirect(wa_url)
                else:
                    messages.error(request, 'Error sharing collateral. Please try again.')
                    return redirect('prefilled_fieldrep_share_collateral')
                    
            except Exception as e:
                print(f"Error sharing prefilled doctor: {e}")
                messages.error(request, 'Error sharing collateral. Please try again.')
                return redirect('prefilled_fieldrep_share_collateral')
        else:
            messages.error(request, 'Please select valid doctor and collateral.')
            return redirect('prefilled_fieldrep_share_collateral')
    
    return render(request, 'sharing_management/prefilled_fieldrep_share_collateral.html', {
        'fieldrep_id': field_rep_field_id or 'Unknown',
        'fieldrep_email': field_rep_email,
        'doctors': doctors_list,
        'collaterals': collaterals_list
    })

def fieldrep_gmail_login(request):
    if request.method == 'POST':
        field_id = request.POST.get('field_id')
        gmail_id = request.POST.get('gmail_id')
        action = request.POST.get('action')  # Get which button was clicked
        
        # Check if Register button was clicked
        if 'register' in request.POST:
            # Redirect to registration flow with email
            if gmail_id:
                return redirect(f'/share/fieldrep-create-password/?email={gmail_id}')
            else:
                messages.error(request, 'Please provide Gmail ID to register.')
                return render(request, 'sharing_management/fieldrep_gmail_login.html')
        
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
                            # Prefilled user - redirect to prefilled share collateral
                            return redirect('prefilled_fieldrep_share_collateral')
                        else:
                            # Manual user - redirect to gmail share collateral
                            return redirect('fieldrep_gmail_share_collateral')
                    else:
                        messages.error(request, 'Invalid Field ID or Gmail ID. Please check and try again.')
            except Exception as e:
                print(f"Error in Gmail login: {e}")
                messages.error(request, 'Login failed. Please try again.')
        else:
            messages.error(request, 'Please provide both Field ID and Gmail ID.')
    
    return render(request, 'sharing_management/fieldrep_gmail_login.html')

def fieldrep_gmail_share_collateral(request):
    import urllib.parse
    
    # Get user info from session
    field_rep_id = request.session.get('field_rep_id')
    field_rep_email = request.session.get('field_rep_email')
    field_rep_field_id = request.session.get('field_rep_field_id')
    
    if not field_rep_id:
        messages.error(request, 'Please login first.')
        return redirect('fieldrep_login')
    
    # Get real collaterals from database
    try:
        from collateral_management.models import Collateral
        collaterals = Collateral.objects.filter(is_active=True)  # All collaterals from our imported data
        
        # Convert to list format for template
        collaterals_list = []
        for collateral in collaterals:
            # Create short link for each collateral - use field_rep_id instead of request.user
            try:
                # Get or create a user for this field rep
                from user_management.models import User
                user, created = User.objects.get_or_create(
                    username=f"field_rep_{field_rep_id}",
                    defaults={
                        'email': field_rep_email,
                        'first_name': f"Field Rep {field_rep_id}"
                    }
                )
                
                short_link = find_or_create_short_link(collateral, user)
                collaterals_list.append({
                    'id': collateral.id,
                    'name': collateral.title,  # Use item_name from our model
                    'description': collateral.description,
                    'link': request.build_absolute_uri(f"/shortlinks/go/{short_link.short_code}/")
                })
            except Exception as e:
                print(f"Error creating short link for collateral {collateral.id}: {e}")
                # Skip this collateral if there's an error
                continue
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
        
        if selected_collateral and doctor_name and doctor_whatsapp:
            try:
                from .utils.db_operations import log_manual_doctor_share
                from collateral_management.models import Collateral
                
                # Get the short link for this collateral
                collateral_obj = Collateral.objects.get(id=collateral_id)
                short_link = find_or_create_short_link(collateral_obj, request.user)
                
                # Log the manual doctor share
                success = log_manual_doctor_share(
                    short_link_id=short_link.id,
                    field_rep_id=field_rep_id,
                    phone_e164=doctor_whatsapp,
                    collateral_id=collateral_id
                )
                
                if success:
                    # Get brand-specific message
                    message = get_brand_specific_message(collateral_id, selected_collateral['name'], selected_collateral['link'])
                    wa_url = f"https://wa.me/91{doctor_whatsapp}?text={urllib.parse.quote(message)}"
                    
                    messages.success(request, f'Collateral shared successfully with {doctor_name}!')
                    return redirect(wa_url)
                else:
                    messages.error(request, 'Error sharing collateral. Please try again.')
                    return redirect('fieldrep_gmail_share_collateral')
                    
            except Exception as e:
                print(f"Error sharing manual doctor: {e}")
                messages.error(request, 'Error sharing collateral. Please try again.')
                return redirect('fieldrep_gmail_share_collateral')
        else:
            messages.error(request, 'Please fill all required fields.')
            return redirect('fieldrep_gmail_share_collateral')
    
    return render(request, 'sharing_management/fieldrep_gmail_share_collateral.html', {
        'fieldrep_id': field_rep_field_id or 'Unknown',
        'fieldrep_email': field_rep_email,
        'collaterals': collaterals_list
    })

def prefilled_fieldrep_gmail_login(request):
    if request.method == 'POST':
        field_id = request.POST.get('field_id')
        gmail_id = request.POST.get('gmail_id')
        
        if field_id and gmail_id:
            # Authenticate using database
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
                    return redirect('prefilled_fieldrep_gmail_share_collateral')
                else:
                    messages.error(request, 'Invalid Field ID or Gmail ID. Please check and try again.')
            except Exception as e:
                print(f"Error in prefilled gmail login: {e}")
                messages.error(request, 'Login failed. Please try again.')
        else:
            messages.error(request, 'Please provide both Field ID and Gmail ID.')
    
    return render(request, 'sharing_management/prefilled_fieldrep_gmail_login.html')

def prefilled_fieldrep_gmail_share_collateral(request):
    import urllib.parse
    
    # Get user info from session
    field_rep_id = request.session.get('field_rep_id')
    field_rep_email = request.session.get('field_rep_email')
    field_rep_field_id = request.session.get('field_rep_field_id')
    
    if not field_rep_id:
        messages.error(request, 'Please login first.')
        return redirect('fieldrep_login')
    
    # Get real prefilled doctors from database
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, full_name, phone, email, specialty, city
                FROM prefilled_doctor
                ORDER BY full_name
            """)
            doctors_data = cursor.fetchall()
            
        doctors_list = []
        for doctor in doctors_data:
            doctors_list.append({
                'id': doctor[0],
                'name': doctor[1],
                'phone': doctor[2],
                'email': doctor[3],
                'specialty': doctor[4],
                'city': doctor[5]
            })
    except Exception as e:
        print(f"Error fetching prefilled doctors: {e}")
        doctors_list = []
        messages.error(request, 'Error loading doctors. Please try again.')
    
    # Get real collaterals from database
    try:
        from collateral_management.models import Collateral
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
        doctor_id = int(request.POST.get('doctor_id'))
        collateral_id = int(request.POST.get('collateral'))
        
        # Find the selected doctor and collateral
        selected_doctor = next((d for d in doctors_list if d['id'] == doctor_id), None)
        selected_collateral = next((c for c in collaterals_list if c['id'] == collateral_id), None)
        
        if selected_doctor and selected_collateral:
            try:
                from .utils.db_operations import share_prefilled_doctor
                from collateral_management.models import Collateral
                
                # Get the short link for this collateral
                collateral_obj = Collateral.objects.get(id=collateral_id)
                short_link = find_or_create_short_link(collateral_obj, request.user)
                
                # Share the prefilled doctor
                success = share_prefilled_doctor(
                    rep_id=field_rep_id,
                    prefilled_doctor_id=doctor_id,
                    short_link_id=short_link.id,
                    collateral_id=collateral_id
                )
                
                if success:
                    # Get brand-specific message
                    message = get_brand_specific_message(collateral_id, selected_collateral['name'], selected_collateral['link'])
                    wa_url = f"https://wa.me/91{selected_doctor['phone']}?text={urllib.parse.quote(message)}"
                    
                    messages.success(request, f'Collateral shared successfully with {selected_doctor["name"]}!')
                    return redirect(wa_url)
                else:
                    messages.error(request, 'Error sharing collateral. Please try again.')
                    return redirect('prefilled_fieldrep_gmail_share_collateral')
                    
            except Exception as e:
                print(f"Error sharing prefilled doctor: {e}")
                messages.error(request, 'Error sharing collateral. Please try again.')
                return redirect('prefilled_fieldrep_gmail_share_collateral')
        else:
            messages.error(request, 'Please select valid doctor and collateral.')
            return redirect('prefilled_fieldrep_gmail_share_collateral')
    
    return render(request, 'sharing_management/prefilled_fieldrep_gmail_share_collateral.html', {
        'fieldrep_id': field_rep_field_id or 'Unknown',
        'fieldrep_email': field_rep_email,
        'doctors': doctors_list,
        'collaterals': collaterals_list
    })

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

def fieldrep_whatsapp_share_collateral(request):
    import urllib.parse
    
    # Get user info from session
    field_rep_id = request.session.get('field_rep_id')
    field_rep_email = request.session.get('field_rep_email')
    field_rep_field_id = request.session.get('field_rep_field_id')
    
    print(f"DEBUG: Share collateral view - Session data: ID={field_rep_id}, Email={field_rep_email}, Field_ID={field_rep_field_id}")
    
    if not field_rep_id:
        print(f"DEBUG: No field_rep_id in session, redirecting to login")
        messages.error(request, 'Please login first.')
        return redirect('fieldrep_whatsapp_login')
    
    # Get real collaterals from database
    try:
        from collateral_management.models import Collateral
        from user_management.models import User
        collaterals = Collateral.objects.filter(is_active=True)
        
        # Get the actual user object for short link creation
        try:
            actual_user = User.objects.get(id=field_rep_id)
        except User.DoesNotExist:
            actual_user = request.user  # fallback
        
        # Convert to list format for template
        collaterals_list = []
        for collateral in collaterals:
            # Create short link for each collateral
            short_link = find_or_create_short_link(collateral, actual_user)
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
        print(f"POST request received: {request.POST}")
        doctor_name = request.POST.get('doctor_name')
        doctor_whatsapp = request.POST.get('doctor_whatsapp')
        collateral_id = request.POST.get('collateral')
        
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
        
        if selected_collateral and doctor_name and doctor_whatsapp:
            try:
                from .utils.db_operations import log_manual_doctor_share
                from collateral_management.models import Collateral
                
                # Get the short link for this collateral
                collateral_obj = Collateral.objects.get(id=collateral_id)
                short_link = find_or_create_short_link(collateral_obj, actual_user)
                print(f"Short link created: {short_link.short_code}")
                
                # Log the manual doctor share
                print(f"Logging share - short_link_id: {short_link.id}, field_rep_id: {field_rep_id}, phone: {doctor_whatsapp}, collateral_id: {collateral_id}")
                success = log_manual_doctor_share(
                    short_link_id=short_link.id,
                    field_rep_id=field_rep_id,
                    phone_e164=doctor_whatsapp,
                    collateral_id=collateral_id
                )
                
                if success:
                    # Get brand-specific message
                    message = get_brand_specific_message(collateral_id, selected_collateral['name'], selected_collateral['link'])
                    
                    # Clean phone number for WhatsApp URL
                    clean_phone = doctor_whatsapp.replace('+91', '').replace('+', '')
                    wa_url = f"https://wa.me/91{clean_phone}?text={urllib.parse.quote(message)}"
                    
                    messages.success(request, f'Collateral shared successfully with {doctor_name}!')
                    return redirect(wa_url)
                else:
                    messages.error(request, 'Error sharing collateral. Please try again.')
                    return redirect('fieldrep_whatsapp_share_collateral')
                    
            except Exception as e:
                import traceback
                traceback.print_exc()
                messages.error(request, f'Error sharing collateral: {str(e)}')
                return redirect('fieldrep_whatsapp_share_collateral')
        else:
            missing_fields = []
            if not doctor_name: missing_fields.append('Doctor Name')
            if not doctor_whatsapp: missing_fields.append('WhatsApp Number')
            if not selected_collateral: missing_fields.append('Valid Collateral')
            
            messages.error(request, f'Please fill all required fields: {", ".join(missing_fields)}')
            return redirect('fieldrep_whatsapp_share_collateral')
    
    return render(request, 'sharing_management/fieldrep_whatsapp_share_collateral.html', {
        'fieldrep_id': field_rep_field_id or 'Unknown',
        'fieldrep_email': field_rep_email,
        'collaterals': collaterals_list
    })

def prefilled_fieldrep_whatsapp_login(request):
    # Get existing field reps from database for dropdown
    existing_field_reps = []
    try:
        from user_management.models import User
        field_reps = User.objects.filter(role='field_rep', active=True).values('field_id', 'email', 'phone_number')
        existing_field_reps = list(field_reps)
        print(f"Found {len(existing_field_reps)} existing field reps")
    except Exception as e:
        print(f"Error fetching field reps: {e}")
    
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
            
            # Direct authentication without OTP
            success, user_id, user_data = authenticate_field_representative_direct(field_id, whatsapp_number, ip_address, user_agent)
            
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
                
                messages.success(request, f'Welcome back, {user_data["field_id"]}!')
                return redirect('prefilled_fieldrep_whatsapp_share_collateral')
            else:
                messages.error(request, 'Invalid Field ID or WhatsApp number. Please check and try again.')
        else:
            messages.error(request, 'Please provide both Field ID and WhatsApp number.')
    
    return render(request, 'sharing_management/prefilled_fieldrep_whatsapp_login.html', {
        'existing_field_reps': existing_field_reps
    })

def prefilled_fieldrep_whatsapp_share_collateral(request):
    import urllib.parse
    
    # Get user info from session
    field_rep_id = request.session.get('field_rep_id')
    field_rep_email = request.session.get('field_rep_email')
    field_rep_field_id = request.session.get('field_rep_field_id')
    
    if not field_rep_id:
        messages.error(request, 'Please login first.')
        return redirect('fieldrep_login')
    
    # Get real prefilled doctors from database
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, full_name, phone, email, specialty, city
                FROM prefilled_doctor
                ORDER BY full_name
            """)
            doctors_data = cursor.fetchall()
            
        doctors_list = []
        for doctor in doctors_data:
            doctors_list.append({
                'id': doctor[0],
                'name': doctor[1],
                'phone': doctor[2],
                'email': doctor[3],
                'specialty': doctor[4],
                'city': doctor[5]
            })
    except Exception as e:
        print(f"Error fetching prefilled doctors: {e}")
        doctors_list = []
        messages.error(request, 'Error loading doctors. Please try again.')
    
    # Get real collaterals from database
    try:
        from collateral_management.models import Collateral
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
        doctor_id = int(request.POST.get('doctor_id'))
        collateral_id = int(request.POST.get('collateral'))
        
        # Find the selected doctor and collateral
        selected_doctor = next((d for d in doctors_list if d['id'] == doctor_id), None)
        selected_collateral = next((c for c in collaterals_list if c['id'] == collateral_id), None)
        
        if selected_doctor and selected_collateral:
            try:
                from .utils.db_operations import share_prefilled_doctor
                from collateral_management.models import Collateral
                
                # Get the short link for this collateral
                collateral_obj = Collateral.objects.get(id=collateral_id)
                short_link = find_or_create_short_link(collateral_obj, request.user)
                
                # Share the prefilled doctor
                success = share_prefilled_doctor(
                    rep_id=field_rep_id,
                    prefilled_doctor_id=doctor_id,
                    short_link_id=short_link.id,
                    collateral_id=collateral_id
                )
                
                if success:
                    # Get brand-specific message
                    message = get_brand_specific_message(collateral_id, selected_collateral['name'], selected_collateral['link'])
                    wa_url = f"https://wa.me/91{selected_doctor['phone']}?text={urllib.parse.quote(message)}"
                    
                    messages.success(request, f'Collateral shared successfully with {selected_doctor["name"]}!')
                    return redirect(wa_url)
                else:
                    messages.error(request, 'Error sharing collateral. Please try again.')
                    return redirect('prefilled_fieldrep_whatsapp_share_collateral')
                    
            except Exception as e:
                print(f"Error sharing prefilled doctor: {e}")
                messages.error(request, 'Error sharing collateral. Please try again.')
                return redirect('prefilled_fieldrep_whatsapp_share_collateral')
        else:
            messages.error(request, 'Please select valid doctor and collateral.')
            return redirect('prefilled_fieldrep_whatsapp_share_collateral')
    
    return render(request, 'sharing_management/prefilled_fieldrep_whatsapp_share_collateral.html', {
        'fieldrep_id': field_rep_field_id or 'Unknown',
        'fieldrep_email': field_rep_email,
        'doctors': doctors_list,
        'collaterals': collaterals_list
    })

@csrf_exempt
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
        VideoTrackingLog.objects.create(
            share_log=share_log,
            user_id=user_id,
            video_status=video_status,
            video_percentage=video_percentage,
            comment=comment
        )
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
                    f"Doctors created: {result['created']}. Mappings created/updated: {result.get('updated', 0)}."
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
    response["Content-Disposition"] = "attachment; filename=premapped_by_login_template.csv"
    w = csv.writer(response)
    # Header is REQUIRED for clarity and robustness
    w.writerow(["doctor_name", "whatsapp_number", "fieldrep_id", "collateral_id"])
    w.writerow(["Dr Jane Doe", "+919999998888", "42", "99"])
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