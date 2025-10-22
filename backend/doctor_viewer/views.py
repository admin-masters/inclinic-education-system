import json, math, os
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from shortlink_management.models import ShortLink
from collateral_management.models import Collateral
from collateral_management.models import CampaignCollateral as CollateralCampaignLink
from .models import DoctorEngagement

# ──────────────────────────────────────────────────────────────
# Safe page count helper – works with local + remote storage
# ──────────────────────────────────────────────────────────────
def _page_count(collateral: Collateral) -> int:
    """Return page count or 0 on any failure (S3, corrupt file…)"""
    if collateral.type != "pdf":
        return 0
    try:
        from PyPDF2 import PdfReader
        # Local file?
        if collateral.file and hasattr(collateral.file, "path") and os.path.exists(collateral.file.path):
            return len(PdfReader(collateral.file.path).pages)
        # Remote file (S3 or other)
        resp = collateral.file.open(mode="rb")
        return len(PdfReader(resp).pages)
    except Exception:
        return 0

# ──────────────────────────────────────────────────────────────
# GET  /view/<code>/   → render PDF or video template
# ──────────────────────────────────────────────────────────────
def resolve_view(request, code: str):
    short_link = get_object_or_404(ShortLink, short_code=code, is_active=True)
    collateral = short_link.get_collateral()
    if not collateral or not collateral.is_active:
        return render(request, 'doctor_viewer/error.html', {'msg': 'Collateral unavailable'})

    engagement = DoctorEngagement.objects.create(short_link=short_link)

    context = {
        'collateral': collateral,
        'engagement_id': engagement.id,
        'short_code': code,
    }
    return render(request, 'doctor_viewer/view.html', context)

# ──────────────────────────────────────────────────────────────
# POST /view/log/        JSON body → update DoctorEngagement
# ──────────────────────────────────────────────────────────────
@csrf_exempt
def log_engagement(request):
    if request.method != 'POST':
        return HttpResponseBadRequest("POST required")

    try:
        data = json.loads(request.body.decode())
        engagement_id = int(data['engagement_id'])
    except (KeyError, ValueError, json.JSONDecodeError):
        return HttpResponseBadRequest("Invalid JSON")

    engagement = get_object_or_404(DoctorEngagement, id=engagement_id)
    collateral = engagement.short_link.get_collateral()

    engagement.last_page_scrolled = max(engagement.last_page_scrolled, data.get('last_page', 0))
    engagement.pdf_completed = engagement.pdf_completed or data.get('pdf_completed', False)
    engagement.video_watch_percentage = max(
        engagement.video_watch_percentage, data.get('video_pct', 0)
    )

    # Use provided page count if available, otherwise fallback
    pdf_total_pages = data.get('pdf_total_pages') or _page_count(collateral)
    if pdf_total_pages:
        last_page = engagement.last_page_scrolled
        if last_page == 0:
            engagement.status = 0
        elif last_page < pdf_total_pages:
            engagement.status = 1
        else:
            engagement.status = 2

    engagement.updated_at = timezone.now()
    engagement.save(update_fields=[
        'last_page_scrolled',
        'pdf_completed',
        'video_watch_percentage',
        'status',
        'updated_at'
    ])
    return JsonResponse({'status': 'ok'})

# ──────────────────────────────────────────────────────────────
# GET  /view/report/<code>/     → JSON report for admin or reps
# ──────────────────────────────────────────────────────────────
def doctor_report(request, code: str):
    short_link = get_object_or_404(ShortLink, short_code=code, is_active=True)
    qry = (
        DoctorEngagement.objects
        .filter(short_link=short_link)
        .values(
            'id',
            'view_timestamp',
            'status',
            'last_page_scrolled',
            'pdf_completed',
            'video_watch_percentage'
        )
    )
    return JsonResponse(list(qry), safe=False)

def doctor_collateral_verify(request):
    # Handle GET request - fetch short_link_id from query params
    if request.method == 'GET':
        short_link_id = request.GET.get('short_link_id')
        if short_link_id:
            try:
                short_link = get_object_or_404(ShortLink, id=short_link_id, is_active=True)
                collateral = short_link.get_collateral()
                if collateral and collateral.is_active:
                    # Generate PDF preview URL for the first page
                    pdf_preview_url = None
                    if collateral.type == 'pdf' and collateral.file:
                        # Build absolute URL using current host + MEDIA_URL to avoid embedded 127.0.0.1
                        from django.conf import settings
                        media_path = collateral.file.name  # path relative to MEDIA_ROOT
                        absolute_pdf = request.build_absolute_uri(f"{settings.MEDIA_URL}{media_path}")
                        # Hide sidebar/thumbs and toolbar; lock to page 1
                        pdf_preview_url = (
                            f"{absolute_pdf}#page=1&zoom=85&toolbar=0&navpanes=0&pagemode=none&view=FitH"
                        )
                    
                    return render(request, 'doctor_viewer/doctor_collateral_verify.html', {
                        'short_link': short_link,
                        'collateral': collateral,
                        'short_link_id': short_link_id,
                        'pdf_preview_url': pdf_preview_url
                    })
                else:
                    from django.contrib import messages
                    messages.error(request, 'Collateral not found or inactive.')
            except Exception as e:
                from django.contrib import messages
                messages.error(request, 'Invalid short link.')
                print(f"DEBUG: Error: {e}")
        else:
            from django.contrib import messages
            messages.error(request, 'Short link ID is required.')
    
    # Handle POST request - WhatsApp number verification
    elif request.method == 'POST':
        whatsapp_number = request.POST.get('whatsapp_number')
        short_link_id = request.POST.get('short_link_id')
        
        if whatsapp_number and short_link_id:
            try:
                print(f"DEBUG: Verifying WhatsApp number: {whatsapp_number} for short_link_id: {short_link_id}")
                
                # Check if this WhatsApp number was used to share this collateral
                from sharing_management.utils.db_operations import verify_doctor_whatsapp_number
                
                # Verify WhatsApp number matches the one used in sharing
                success = verify_doctor_whatsapp_number(whatsapp_number, short_link_id)
                print(f"DEBUG: Verification result: {success}")
                
                if success:
                    # Grant download access
                    from sharing_management.utils.db_operations import grant_download_access
                    grant_success = grant_download_access(short_link_id)
                    
                    if grant_success:
                        # Get short link and collateral info
                        short_link = get_object_or_404(ShortLink, id=short_link_id, is_active=True)
                        collateral = short_link.get_collateral()
                        
                        if collateral:
                            # Build Archives list (same logic as OTP flow)
                            campaign_id = None
                            if getattr(collateral, 'campaign_id', None):
                                campaign_id = collateral.campaign_id
                            else:
                                link = CollateralCampaignLink.objects.filter(collateral=collateral).select_related('campaign').first()
                                if link:
                                    campaign_id = link.campaign_id

                            archives = []
                            if campaign_id:
                                older_qs = Collateral.objects.filter(
                                    campaign_id=campaign_id,
                                    is_active=True,
                                    upload_date__lt=collateral.upload_date
                                ).exclude(pk=collateral.pk).order_by('-upload_date')

                                n_prev = older_qs.count()
                                limit = 3 if n_prev >= 3 else n_prev
                                older_items = list(older_qs[:limit])

                                for c in older_items:
                                    sl = ShortLink.objects.filter(
                                        resource_type='collateral',
                                        resource_id=c.id,
                                        is_active=True
                                    ).order_by('-date_created').first()
                                    archives.append({
                                        'obj': c,
                                        'short_code': sl.short_code if sl else None
                                    })

                            return render(request, 'doctor_viewer/doctor_collateral_view.html', {
                                'collateral': collateral,
                                'short_link': short_link,
                                'verified': True,
                                'archives': archives,
                            })
                        else:
                            from django.contrib import messages
                            messages.error(request, 'Collateral not found.')
                    else:
                        from django.contrib import messages
                        messages.error(request, 'Error granting access.')
                else:
                    from django.contrib import messages
                    messages.error(request, 'WhatsApp number not found in sharing records. Please check the number.')
                    
            except Exception as e:
                from django.contrib import messages
                messages.error(request, 'Error verifying WhatsApp number. Please try again.')
                print(f"DEBUG: Error: {e}")
        else:
            from django.contrib import messages
            messages.error(request, 'Please provide WhatsApp number.')
    
    return render(request, 'doctor_viewer/doctor_collateral_verify.html')

def doctor_collateral_view(request):
    if request.method == 'POST':
        whatsapp_number = request.POST.get('whatsapp_number')
        short_link_id = request.POST.get('short_link_id')
        otp = request.POST.get('otp')
        
        if whatsapp_number and short_link_id and otp:
            try:
                from sharing_management.utils.db_operations import verify_doctor_otp, grant_download_access
                
                # Verify OTP
                success, row_id = verify_doctor_otp(whatsapp_number, short_link_id, otp)
                
                if success:
                    # Grant download access
                    grant_success = grant_download_access(short_link_id)
                    
                    if grant_success:
                        # Get short link and collateral info
                        short_link = get_object_or_404(ShortLink, id=short_link_id)
                        collateral = short_link.get_collateral()
                        
                        if collateral:
                            # === NEW: Build Archives list ===
                            campaign_id = None
                            # Prefer direct FK if present
                            if getattr(collateral, 'campaign_id', None):
                                campaign_id = collateral.campaign_id
                            else:
                                # Fallback via link table
                                link = CollateralCampaignLink.objects.filter(collateral=collateral).select_related('campaign').first()
                                if link:
                                    campaign_id = link.campaign_id

                            archives = []
                            if campaign_id:
                                older_qs = Collateral.objects.filter(
                                    campaign_id=campaign_id,
                                    is_active=True,
                                    upload_date__lt=collateral.upload_date
                                ).exclude(pk=collateral.pk).order_by('-upload_date')

                                n_prev = older_qs.count()
                                if n_prev >= 3:
                                    limit = 3
                                else:
                                    limit = n_prev  # 0, 1 or 2
                                older_items = list(older_qs[:limit])

                                # Attach short links if any
                                archives = []
                                for c in older_items:
                                    sl = ShortLink.objects.filter(
                                        resource_type='collateral',
                                        resource_id=c.id,
                                        is_active=True
                                    ).order_by('-date_created').first()
                                    archives.append({
                                        'obj': c,
                                        'short_code': sl.short_code if sl else None
                                    })

                            return render(request, 'doctor_viewer/doctor_collateral_view.html', {
                                'collateral': collateral,
                                'short_link': short_link,
                                'verified': True,
                                'archives': archives,   # NEW
                            })
                        else:
                            from django.contrib import messages
                            messages.error(request, 'Collateral not found.')
                    else:
                        from django.contrib import messages
                        messages.error(request, 'Error granting access.')
                else:
                    from django.contrib import messages
                    messages.error(request, 'Invalid OTP. Please try again.')
                    
            except Exception as e:
                from django.contrib import messages
                messages.error(request, 'Error verifying OTP. Please try again.')
        else:
            from django.contrib import messages
            messages.error(request, 'Please provide all required information.')
    
    # If no POST or verification failed, show verification form
    return render(request, 'doctor_viewer/doctor_collateral_verify.html')

def tracking_dashboard(request):
    """
    Comprehensive tracking dashboard showing all doctor engagement data
    """
    # Get all doctor engagements with related data
    engagements = DoctorEngagement.objects.select_related(
        'short_link'
    ).order_by('-view_timestamp')
    
    # Get summary statistics
    total_engagements = engagements.count()
    pdf_engagements = engagements.filter(pdf_completed=True).count()
    video_engagements = engagements.filter(video_watch_percentage__gte=90).count()
    
    # Get collateral-wise statistics (instead of campaign-wise)
    collateral_stats = {}
    for engagement in engagements:
        collateral = engagement.short_link.get_collateral()
        if collateral:
            collateral_name = collateral.title if hasattr(collateral, 'title') else str(collateral)
            
            if collateral_name not in collateral_stats:
                collateral_stats[collateral_name] = {
                    'pdf_completed': 0,
                    'video_completed': 0,
                    'total_views': 0,
                    'type': collateral.type if hasattr(collateral, 'type') else 'unknown'
                }
            
            collateral_stats[collateral_name]['total_views'] += 1
            if engagement.pdf_completed:
                collateral_stats[collateral_name]['pdf_completed'] += 1
            if engagement.video_watch_percentage >= 90:
                collateral_stats[collateral_name]['video_completed'] += 1
    
    # Get recent engagements for detailed view
    recent_engagements = engagements[:50]  # Last 50 engagements
    
    context = {
        'total_engagements': total_engagements,
        'pdf_engagements': pdf_engagements,
        'video_engagements': video_engagements,
        'collateral_stats': collateral_stats,  # Changed from campaign_stats
        'recent_engagements': recent_engagements,
    }
    
    return render(request, 'doctor_viewer/tracking_dashboard.html', context)
