import json, math
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from shortlink_management.models import ShortLink
from collateral_management.models import Collateral
from .models import DoctorEngagement

# ──────────────────────────────────────────────────────────────
# GET  /view/<code>/   → render PDF or video template
# ──────────────────────────────────────────────────────────────
def resolve_view(request, code: str):
    short_link = get_object_or_404(ShortLink, short_code=code, is_active=True)
    collateral = short_link.get_collateral()
    if not collateral or not collateral.is_active:
        return render(request, 'doctor_viewer/error.html', {'msg': 'Collateral unavailable'})

    # Create an engagement row now → we’ll update it later via AJAX
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

    # Update fields that may be present
    engagement.last_page_scrolled      = max(engagement.last_page_scrolled, data.get('last_page', 0))
    engagement.pdf_completed           = engagement.pdf_completed or data.get('pdf_completed', False)
    engagement.video_watch_percentage  = max(engagement.video_watch_percentage, data.get('video_pct', 0))
    engagement.updated_at              = timezone.now()
    engagement.save(update_fields=['last_page_scrolled',
                                   'pdf_completed',
                                   'video_watch_percentage',
                                   'updated_at'])
    return JsonResponse({'status': 'ok'})