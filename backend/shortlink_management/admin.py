# shortlink_management/admin.py

from django.contrib import admin
from .models import ShortLink, DoctorVerificationOTP

@admin.register(ShortLink)
class ShortLinkAdmin(admin.ModelAdmin):
    list_display = ('short_code', 'resource_type', 'resource_id', 'is_active', 'created_by', 'date_created')
    list_filter = ('resource_type', 'is_active')
    search_fields = ('short_code',)


@admin.register(DoctorVerificationOTP)
class DoctorVerificationOTPAdmin(admin.ModelAdmin):
    list_display = ('phone_e164', 'short_link', 'expires_at', 'verified_at', 'is_expired', 'is_verified')
    list_filter = ('expires_at', 'verified_at', 'created_at')
    search_fields = ('phone_e164', 'short_link__short_code')
    readonly_fields = ('otp_hash', 'created_at')
    ordering = ('-created_at',)
    
    def is_expired(self, obj):
        return obj.is_expired()
    is_expired.boolean = True
    is_expired.short_description = 'Expired'
    
    def is_verified(self, obj):
        return obj.is_verified()
    is_verified.boolean = True
    is_verified.short_description = 'Verified'