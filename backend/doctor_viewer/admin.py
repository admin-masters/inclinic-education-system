# doctor_viewer/admin.py
from django.contrib import admin
from .models import DoctorEngagement

@admin.register(DoctorEngagement)
class DoctorEngagementAdmin(admin.ModelAdmin):
    list_display = ('short_link', 'pdf_completed', 'video_watch_percentage', 'view_timestamp')
    list_filter  = ('pdf_completed',)
    search_fields= ('short_link__short_code',)