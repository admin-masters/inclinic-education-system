from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count
from urllib.parse import quote
from django.core.paginator import Paginator  # ✅ added

from django.core.mail import send_mail
from django.conf import settings
import django.forms as forms

from .decorators import field_rep_required
from .forms import ShareForm
from .models import ShareLog
from shortlink_management.models import ShortLink
from shortlink_management.utils import generate_short_code
from collateral_management.models import Collateral, CampaignCollateral
from campaign_management.models import CampaignAssignment
from doctor_viewer.models import DoctorEngagement
from utils.recaptcha import recaptcha_required


def _send_email(to_addr: str, subject: str, body: str) -> None:
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[to_addr],
        fail_silently=False,
    )


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
        # Hide collateral field if pre-selected
        if collateral_id:
            form.fields['collateral'].widget = forms.HiddenInput()

    return render(request, 'sharing_management/share_form.html', {'form': form})


def find_or_create_short_link(collateral, user):
    existing = ShortLink.objects.filter(
        resource_type='collateral',
        resource_id=collateral.id,
        is_active=True
    ).first()
    if existing:
        return existing

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
    paginator = Paginator(logs_list, 10)  # ✅ 10 logs per page

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
        pdf_completed=True,
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

    return render(request, 'sharing_management/fieldrep_dashboard.html', {'stats': stats})


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
    ).values('short_link__resource_id').annotate(cnt=Count('id'))
    share_map = {r['short_link__resource_id']: r['cnt'] for r in shares}

    eng = DoctorEngagement.objects.filter(
        short_link__resource_id__in=col_ids,
        short_link__resource_type='collateral')

    pdf_map = eng.filter(pdf_completed=True).values('short_link__resource_id').annotate(cnt=Count('id'))
    pdf_map = {r['short_link__resource_id']: r['cnt'] for r in pdf_map}

    vid_map = eng.filter(video_watch_percentage__gte=90).values('short_link__resource_id').annotate(cnt=Count('id'))
    vid_map = {r['short_link__resource_id']: r['cnt'] for r in vid_map}

    rows = []
    for cc in ccols:
        col = cc.collateral
        cid = col.id
        rows.append({
            'collateral': col,
            'shares': share_map.get(cid, 0),
            'pdfs': pdf_map.get(cid, 0),
            'videos': vid_map.get(cid, 0),
        })

    return render(request, 'sharing_management/fieldrep_campaign_detail.html', {'rows': rows})
