# shortlink_management/admin.py

from django.contrib import admin
from .models import ShortLink

@admin.register(ShortLink)
class ShortLinkAdmin(admin.ModelAdmin):
    list_display = ('short_code', 'resource_type', 'resource_id', 'is_active', 'created_by', 'date_created')
    list_filter = ('resource_type', 'is_active')
    search_fields = ('short_code',)