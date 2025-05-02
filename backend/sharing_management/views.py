from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Q

from .decorators import field_rep_required
from .forms import ShareForm
from .models import ShareLog
from shortlink_management.models import ShortLink
from shortlink_management.utils import generate_short_code
from collateral_management.models import Collateral, CampaignCollateral
from campaign_management.models import CampaignAssignment
from doctor_viewer.models import DoctorEngagement
from utils.recaptcha import recaptcha_required
@field_rep_required
@recaptcha_required 
def share_content(request):
    """
    Field rep chooses which collateral to share, enters doctor info,
    and we create (or reuse) a short link, then log the share event.
    Finally, we show them a "WhatsApp link" to send to the doctor.
    """
    if request.method == 'POST':
        form = ShareForm(request.POST)
        if form.is_valid():
            collateral = form.cleaned_data['collateral']
            doctor_identifier = form.cleaned_data['doctor_identifier']
            share_channel = form.cleaned_data['share_channel']
            message_text = form.cleaned_data['message_text']

            # 1) Find or create a short link for this collateral
            short_link = find_or_create_short_link(collateral, request.user)

            # 2) Log the share in ShareLog
            share_log = ShareLog.objects.create(
                short_link=short_link,
                field_rep=request.user,
                doctor_identifier=doctor_identifier,
                share_channel=share_channel,
                share_timestamp=timezone.now(),
                message_text=message_text
            )

            messages.success(request, "Share logged successfully!")

            # 3) Generate the pre-populated WhatsApp link
            # Typically: https://wa.me/<PHONE>?text=<URL-ENCODED MESSAGE>
            # We'll do a simple approach with phone=doctor_identifier (if that's a phone).
            # You can parse or store it differently if needed.

            wa_link = ""
            if share_channel == 'WhatsApp':
                # The short link might be something like /shortlinks/go/ABC123
                short_url = request.build_absolute_uri(
                    f"/shortlinks/go/{short_link.short_code}/"
                )
                base_wa = "https://wa.me/"
                # If doctor_identifier is a phone number:
                phone_number = doctor_identifier
                # Construct the full message
                # If there's a custom message, combine it with the short link
                if message_text:
                    full_msg = f"{message_text} {short_url}"
                else:
                    full_msg = f"Hello Doctor, please check this: {short_url}"

                import urllib.parse
                encoded_msg = urllib.parse.quote(full_msg, safe='')
                wa_link = f"{base_wa}{phone_number}?text={encoded_msg}"

            # # 4) Redirect to a success page that shows the "Open WhatsApp" link
            # return redirect('share_success', share_log_id=share_log.id, wa_link=wa_link)
            if wa_link:
               return redirect(
    'share_success_with_link',
    share_log_id=share_log.id,
    wa_link=wa_link
)



            else:
                return redirect('share_success', share_log_id=share_log.id)

    else:
        form = ShareForm()

    return render(request, 'sharing_management/share_form.html', {'form': form})

def find_or_create_short_link(collateral, user):
    """
    Utility to see if there's an existing short link for this collateral.
    If not found, create one.  In real usage, you might create a new short link
    each time or you might reuse the same short link for everyone.
    """
    # Check if we want one global short link or a brand-new for each share
    # For example, let's say we reuse the same link if it exists and is active:
    existing = ShortLink.objects.filter(
        resource_type='collateral',
        resource_id=collateral.id,
        is_active=True
    ).first()
    if existing:
        return existing
    # Otherwise, create
    from django.utils import timezone
    short_code = generate_short_code(length=8)
    short_link = ShortLink.objects.create(
        short_code=short_code,
        resource_type='collateral',
        resource_id=collateral.id,
        created_by=user,
        date_created=timezone.now(),
        is_active=True
    )
    return short_link

@field_rep_required
def share_success(request, share_log_id, wa_link=None):
    share_log = get_object_or_404(ShareLog, id=share_log_id, field_rep=request.user)
    return render(request, 'sharing_management/share_success.html',
                  {'share_log': share_log, 'wa_link': wa_link})


@field_rep_required
def list_share_logs(request):
    """
    Simple view for a field rep to see their own share history.
    """
    logs = ShareLog.objects.filter(field_rep=request.user).order_by('-share_timestamp')
    return render(request, 'sharing_management/share_logs.html', {'logs': logs})

@field_rep_required
def fieldrep_dashboard(request):
    rep = request.user

    # Campaigns assigned to this rep
    assigned = CampaignAssignment.objects.filter(field_rep=rep) \
                .select_related('campaign')

    campaign_ids = [a.campaign_id for a in assigned]

    # aggregate stats from ShareLog & DoctorEngagement
    share_cnts = ShareLog.objects.filter(
        field_rep=rep,
        short_link__resource_type='collateral',
        short_link__resource_id__in=CampaignCollateral.objects.filter(
            campaign_id__in=campaign_ids
        ).values_list('collateral_id', flat=True)
    ).values('short_link__resource_id') \
     .annotate(cnt=Count('id'))
    
    share_map = {r['short_link__resource_id']: r['cnt'] for r in share_cnts}

    pdf_cnts = DoctorEngagement.objects.filter(
        short_link__resource_type='collateral',
        pdf_completed=True,
        short_link__resource_id__in=CampaignCollateral.objects.filter(
            campaign_id__in=campaign_ids
        ).values_list('collateral_id', flat=True)
    ).values('short_link__resource_id') \
     .annotate(cnt=Count('id'))
    
    pdf_map = {r['short_link__resource_id']: r['cnt'] for r in pdf_cnts}

    vid_cnts = DoctorEngagement.objects.filter(
        video_watch_percentage__gte=90,
        short_link__resource_type='collateral',
        short_link__resource_id__in=CampaignCollateral.objects.filter(
            campaign_id__in=campaign_ids
        ).values_list('collateral_id', flat=True)
    ).values('short_link__resource_id') \
     .annotate(cnt=Count('id'))
    
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

    return render(request, 'sharing_management/fieldrep_dashboard.html',
                  {'stats': stats})

@field_rep_required
def fieldrep_campaign_detail(request, campaign_id):
    rep = request.user
    # verify assignment
    get_object_or_404(CampaignAssignment, field_rep=rep, campaign_id=campaign_id)

    # collaterals in the campaign
    ccols = CampaignCollateral.objects.filter(campaign_id=campaign_id) \
             .select_related('collateral')

    # map collateral_id → shares / pdf / vid
    col_ids = [cc.collateral_id for cc in ccols]

    shares = ShareLog.objects.filter(
        field_rep=rep,
        short_link__resource_type='collateral',
        short_link__resource_id__in=col_ids
    ).values('short_link__resource_id') \
     .annotate(cnt=Count('id'))
    
    share_map = {r['short_link__resource_id']: r['cnt'] for r in shares}

    eng = DoctorEngagement.objects.filter(
            short_link__resource_id__in=col_ids,
            short_link__resource_type='collateral')
            
    pdf_map = eng.filter(pdf_completed=True) \
            .values('short_link__resource_id') \
            .annotate(cnt=Count('id'))
    pdf_map = {r['short_link__resource_id']: r['cnt'] for r in pdf_map}

    vid_map = eng.filter(video_watch_percentage__gte=90) \
            .values('short_link__resource_id') \
            .annotate(cnt=Count('id'))
    vid_map = {r['short_link__resource_id']: r['cnt'] for r in vid_map}

    rows = []
    for cc in ccols:
        col = cc.collateral
        cid = col.id
        rows.append({
            'collateral': col,
            'shares': share_map.get(cid,0),
            'pdfs': pdf_map.get(cid,0),
            'videos': vid_map.get(cid,0),
        })

    return render(request, 'sharing_management/fieldrep_campaign_detail.html',
                  {'rows': rows})
