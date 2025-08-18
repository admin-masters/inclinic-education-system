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
)
from campaign_management.models import CampaignAssignment
from campaign_management.models import Collateral, CampaignCollateral
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

    all_collaterals = Collateral.objects.all()
    
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


@staff_member_required
def bulk_manual_upload(request):
    if request.method == "POST":
        form = BulkManualShareForm(request.POST, request.FILES)
        if form.is_valid():
            created, errors = form.save(user_request=request.user)
            if created:
                messages.success(request, f"{created} rows imported.")
            for err in errors:
                messages.error(request, f"{err}")
            return redirect("bulk_manual_upload")
    else:
        form = BulkManualShareForm()

    return render(request, "sharing_management/bulk_manual_upload.html", {"form": form})


@staff_member_required
def bulk_template_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=bulk_manual_template.csv"
    writer = csv.writer(response)
    writer.writerow([
        "rep@example.com",
        "Dr John Doe",
        "+919812345678",
        "42",
        "WhatsApp",
        "Hi Doctor, please see this.",
    ])
    return response


@staff_member_required
def bulk_pre_mapped_upload(request):
    if request.method == "POST":
        form = BulkPreMappedUploadForm(request.POST, request.FILES)
        if form.is_valid():
            created, errors = form.save(user_request=request.user)
            if created:
                messages.success(request, f"{created} rows imported.")
            for err in errors:
                messages.error(request, err)
            return redirect("bulk_pre_mapped_upload")
    else:
        form = BulkPreMappedUploadForm()
    return render(request, "sharing_management/bulk_premapped_upload.html", {"form": form})


@staff_member_required
def bulk_pre_mapped_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=premapped_template.csv"
    writer = csv.writer(response)
    writer.writerow(["doctor_name", "whatsapp_number", "fieldrep_id", "collateral_id"])
    writer.writerow(["Dr Jane Doe", "+919999998888", "42", "99"])
    return response

# ─── Bulk manual (WhatsApp‑only) UI ──────────────────────────────────────────
@staff_member_required
def bulk_manual_upload_whatsapp(request):
    if request.method == "POST":
        form = BulkManualWhatsappShareForm(request.POST, request.FILES)
        if form.is_valid():
            created, errors = form.save(user_request=request.user)
            if created:
                messages.success(request, f"{created} WhatsApp rows imported.")
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


@staff_member_required
def bulk_whatsapp_template_csv(request):
    """
    Example CSV for WhatsApp‑only bulk upload.
    """
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=bulk_manual_whatsapp_template.csv"
    writer = csv.writer(response)
    writer.writerow([
        "rep@example.com",
        "Dr Jane Doe",
        "+919876543210",
        "42",                  # collateral_id
        "Hi Doctor, please see this.",
    ])
    return response
@staff_member_required
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
    if edit_id:
        try:
            existing_record = CampaignCollateral.objects.get(id=edit_id)
            if request.method == 'POST':
                form = CampaignCollateralForm(request.POST, instance=existing_record)
                if form.is_valid():
                    form.save()
                    messages.success(request, 'Calendar dates updated successfully.')
                    return redirect('edit_campaign_calendar')
            else:
                form = CampaignCollateralForm(instance=existing_record)
        except CampaignCollateral.DoesNotExist:
            messages.error(request, 'Record not found.')
            return redirect('edit_campaign_calendar')
    else:
        # Adding new record
        if request.method == 'POST':
            form = CampaignCollateralForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Campaign collateral added successfully.')
                return redirect('edit_campaign_calendar')
        else:
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
        from campaign_management.models import Collateral
        collaterals = Collateral.objects.all()
        
        # Convert to list format for template
        collaterals_list = []
        for collateral in collaterals:
            # Create short link for each collateral
            short_link = find_or_create_short_link(collateral, request.user)
            collaterals_list.append({
                'id': collateral.id,
                'name': collateral.item_name,
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
        from campaign_management.models import Collateral
        collaterals = Collateral.objects.all()
        
        # Convert to list format for template
        collaterals_list = []
        for collateral in collaterals:
            # Create short link for each collateral
            short_link = find_or_create_short_link(collateral, request.user)
            collaterals_list.append({
                'id': collateral.id,
                'name': collateral.item_name,
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
                from campaign_management.models import Collateral
                
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
        from campaign_management.models import Collateral
        collaterals = Collateral.objects.all()  # All collaterals from our imported data
        
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
                    'name': collateral.item_name,  # Use item_name from our model
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
                from campaign_management.models import Collateral
                
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
        from campaign_management.models import Collateral
        collaterals = Collateral.objects.all()
        
        # Convert to list format for template
        collaterals_list = []
        for collateral in collaterals:
            # Create short link for each collateral
            short_link = find_or_create_short_link(collateral, request.user)
            collaterals_list.append({
                'id': collateral.id,
                'name': collateral.item_name,
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
                from campaign_management.models import Collateral
                
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
        whatsapp_number = request.POST.get('whatsapp_number')
        
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
                
                # Check if user is prefilled or manual based on field_id
                if user_data['field_id'] and user_data['field_id'].startswith('PREFILLED_'):
                    # Prefilled user - redirect to prefilled share collateral
                    return redirect('prefilled_fieldrep_share_collateral')
                else:
                    # Manual user - redirect to whatsapp share collateral
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
    
    if not field_rep_id:
        messages.error(request, 'Please login first.')
        return redirect('fieldrep_login')
    
    # Get real collaterals from database
    try:
        from campaign_management.models import Collateral
        collaterals = Collateral.objects.all()
        
        # Convert to list format for template
        collaterals_list = []
        for collateral in collaterals:
            # Create short link for each collateral
            short_link = find_or_create_short_link(collateral, request.user)
            collaterals_list.append({
                'id': collateral.id,
                'name': collateral.item_name,
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
        
        if selected_collateral and doctor_name and doctor_whatsapp:
            try:
                from .utils.db_operations import log_manual_doctor_share
                from campaign_management.models import Collateral
                
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
                    return redirect('fieldrep_whatsapp_share_collateral')
                    
            except Exception as e:
                print(f"Error sharing manual doctor: {e}")
                messages.error(request, 'Error sharing collateral. Please try again.')
                return redirect('fieldrep_whatsapp_share_collateral')
        else:
            messages.error(request, 'Please fill all required fields.')
            return redirect('fieldrep_whatsapp_share_collateral')
    
    return render(request, 'sharing_management/fieldrep_whatsapp_share_collateral.html', {
        'fieldrep_id': field_rep_field_id or 'Unknown',
        'fieldrep_email': field_rep_email,
        'collaterals': collaterals_list
    })

def prefilled_fieldrep_whatsapp_login(request):
    if request.method == 'POST':
        field_id = request.POST.get('field_id')
        whatsapp_number = request.POST.get('whatsapp_number')
        otp = request.POST.get('otp')
        
        # Step 1: Generate OTP
        if not otp:
            if field_id and whatsapp_number:
                # Generate and store OTP
                success, otp_code, user_id, user_data = generate_and_store_otp(field_id, whatsapp_number)
                
                if success:
                    # In a real implementation, send OTP via WhatsApp API
                    # For now, we'll show it in a message (in production, remove this)
                    messages.success(request, f'OTP sent to your WhatsApp! OTP: {otp_code}')
                    return render(request, 'sharing_management/prefilled_fieldrep_whatsapp_login.html', {
                        'field_id': field_id,
                        'whatsapp_number': whatsapp_number,
                        'show_otp_field': True
                    })
                else:
                    messages.error(request, 'Invalid Field ID or WhatsApp number. Please check and try again.')
            else:
                messages.error(request, 'Please provide both Field ID and WhatsApp number.')
        else:
            # Step 2: Verify OTP
            if field_id and whatsapp_number and otp:
                # Get client IP and user agent for audit logging
                ip_address = request.META.get('REMOTE_ADDR')
                user_agent = request.META.get('HTTP_USER_AGENT', '')
                
                success, user_id, user_data = verify_otp(field_id, whatsapp_number, otp, ip_address, user_agent)
                
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
                    messages.error(request, 'Invalid OTP. Please try again.')
                    return render(request, 'sharing_management/prefilled_fieldrep_whatsapp_login.html', {
                        'field_id': field_id,
                        'whatsapp_number': whatsapp_number,
                        'show_otp_field': True
                    })
            else:
                messages.error(request, 'Please provide all required information.')
    
    return render(request, 'sharing_management/prefilled_fieldrep_whatsapp_login.html')

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
        from campaign_management.models import Collateral
        collaterals = Collateral.objects.all()
        
        # Convert to list format for template
        collaterals_list = []
        for collateral in collaterals:
            # Create short link for each collateral
            short_link = find_or_create_short_link(collateral, request.user)
            collaterals_list.append({
                'id': collateral.id,
                'name': collateral.item_name,
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
                from campaign_management.models import Collateral
                
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