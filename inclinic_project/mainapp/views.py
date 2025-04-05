from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .forms import ExampleForm
from .models import Campaign, CampaignContent, DoctorShare, Profile
from django.contrib.auth.models import User
import datetime

def home(request):
    # Public home, or doc login link
    return render(request, 'mainapp/home.html')

@login_required
def logged_in(request):
    if request.method == 'POST':
        form = ExampleForm(request.POST)
        if form.is_valid():
            # form validated with captcha
            return render(request, 'mainapp/logged_in.html', {'message': 'Form successful!'})
        else:
            return render(request, 'mainapp/logged_in.html', {'form': form})
    else:
        form = ExampleForm()
        return render(request, 'mainapp/logged_in.html', {'form': form})

@login_required
def create_campaign(request):
    if request.method == 'POST':
        campaign_name = request.POST['campaign_name']
        therapy_area = request.POST['therapy_area']
        start_date = request.POST['start_date']
        end_date = request.POST['end_date']

        Campaign.objects.create(
            campaign_name=campaign_name,
            therapy_area=therapy_area,
            start_date=start_date,
            end_date=end_date,
            created_by=request.user
        )
        return redirect('list_campaigns')
    return render(request, 'mainapp/create_campaign.html')

@login_required
def list_campaigns(request):
    all_camps = Campaign.objects.filter(status='ACTIVE')
    return render(request, 'mainapp/list_campaigns.html', {'campaigns': all_camps})

@login_required
def edit_campaign(request, campaign_id):
    camp = get_object_or_404(Campaign, pk=campaign_id)
    if request.method == 'POST':
        camp.campaign_name = request.POST['campaign_name']
        camp.therapy_area = request.POST['therapy_area']
        camp.start_date = request.POST['start_date']
        camp.end_date = request.POST['end_date']
        camp.save()
        return redirect('list_campaigns')
    return render(request, 'mainapp/edit_campaign.html', {'campaign': camp})

@login_required
def archive_campaign(request, campaign_id):
    camp = get_object_or_404(Campaign, pk=campaign_id)
    camp.status = 'ARCHIVED'
    camp.save()
    return redirect('list_campaigns')

@login_required
def create_content(request, campaign_id):
    camp = get_object_or_404(Campaign, pk=campaign_id)
    if request.method == 'POST':
        content_type = request.POST['content_type']  # 'PDF' or 'VIDEO'
        content_title = request.POST['content_title']
        if content_type == 'PDF':
            # We'll store the file reference only, actual PDF is on external file server
            file_path = request.POST['file_path']
            new_content = CampaignContent.objects.create(
                campaign=camp,
                content_type='PDF',
                content_title=content_title,
                file_path=file_path
            )
        else:  # VIDEO
            vimeo_url = request.POST['vimeo_url']
            new_content = CampaignContent.objects.create(
                campaign=camp,
                content_type='VIDEO',
                content_title=content_title,
                vimeo_url=vimeo_url
            )
        return redirect('view_campaign_contents', campaign_id=camp.id)
    return render(request, 'mainapp/create_content.html', {'campaign': camp})

@login_required
def view_campaign_contents(request, campaign_id):
    camp = get_object_or_404(Campaign, pk=campaign_id)
    contents = CampaignContent.objects.filter(campaign=camp)
    return render(request, 'mainapp/view_contents.html', {'contents': contents, 'campaign': camp})

@login_required
def share_collateral(request, campaign_id):
    camp = get_object_or_404(Campaign, pk=campaign_id)
    if request.method == 'POST':
        content_id = request.POST['content_id']
        doctor_phone = request.POST['doctor_phone']
        content_obj = get_object_or_404(CampaignContent, pk=content_id, campaign=camp)
        DoctorShare.objects.create(
            campaign=camp,
            content=content_obj,
            rep=request.user,    # The field rep currently logged in
            doctor_phone=doctor_phone
        )
        return redirect('view_campaign_contents', campaign_id=camp.id)
    else:
        contents = CampaignContent.objects.filter(campaign=camp)
        return render(request, 'mainapp/share_collateral.html', {'campaign': camp, 'contents': contents})

