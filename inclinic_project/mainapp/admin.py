from django.contrib import admin
from .models import Profile, Campaign, CampaignContent, DoctorShare, PDFEvent, VideoEvent

admin.site.register(Profile)
admin.site.register(Campaign)
admin.site.register(CampaignContent)
admin.site.register(DoctorShare)
admin.site.register(PDFEvent)
admin.site.register(VideoEvent)
