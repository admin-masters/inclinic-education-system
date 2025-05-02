from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.shortcuts import render, redirect
from django.contrib import messages

from campaign_management.models import Campaign
from sharing_management.models import ShareLog
from doctor_viewer.models import DoctorEngagement
from .forms import FieldRepBulkUploadForm

# ✅ reCAPTCHA decorator
from utils.recaptcha import recaptcha_required


# ─────────────────────────────────────────────────────────
# DASHBOARD  – usage summaries + links to CRUD pages
# ─────────────────────────────────────────────────────────
@staff_member_required
def dashboard(request):
    shares = ShareLog.objects.values('short_link__resource_id') \
              .annotate(share_cnt=Count('id'))

    pdfs   = DoctorEngagement.objects.filter(pdf_completed=True) \
              .values('short_link__resource_id') \
              .annotate(pdf_impr=Count('id'))

    vids   = DoctorEngagement.objects.filter(video_watch_percentage__gte=90) \
              .values('short_link__resource_id') \
              .annotate(vid_comp=Count('id'))

    share_map = {s['short_link__resource_id']: s['share_cnt']   for s in shares}
    pdf_map   = {p['short_link__resource_id']: p['pdf_impr']    for p in pdfs}
    vid_map   = {v['short_link__resource_id']: v['vid_comp']    for v in vids}

    campaign_stats = []
    for c in Campaign.objects.all():
        coll_ids = list(c.campaign_collaterals.values_list('collateral_id', flat=True))
        campaign_stats.append({
            'campaign': c,
            'shares' : sum(share_map.get(cid, 0) for cid in coll_ids),
            'pdfs'   : sum(pdf_map.get(cid, 0)   for cid in coll_ids),
            'videos' : sum(vid_map.get(cid, 0)   for cid in coll_ids),
        })

    return render(request, 'admin_dashboard/dashboard.html',
                  {'campaign_stats': campaign_stats})


# ─────────────────────────────────────────────────────────
# BULK UPLOAD – Field-Rep CSV  (reCAPTCHA protected)
# ─────────────────────────────────────────────────────────
@staff_member_required
@recaptcha_required                     # ← re-enabled
def bulk_upload_fieldreps(request):
    if request.method == 'POST':
        form = FieldRepBulkUploadForm(request.POST, request.FILES)
        if form.is_valid():
            created, updated, errors = form.save(request.user)
            messages.success(request, f"Created {created}, updated {updated}.")
            for err in errors:
                messages.warning(request, err)
            return redirect('admin_dashboard:bulk_upload')
    else:
        form = FieldRepBulkUploadForm()

    return render(request, 'admin_dashboard/bulk_upload.html',
                  {'form': form})