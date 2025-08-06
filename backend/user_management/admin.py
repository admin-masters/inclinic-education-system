# user_management/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Secret, SecurityQuestion, UserSecurityAnswer, PrefilledDoctor, RepLoginOTP, LoginAuditWhatsApp
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Display extra fields in admin list
    list_display = ('username', 'email', 'role', 'active', 'is_staff', 'is_superuser')
    list_filter = ('role', 'active', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email', 'phone')

    # Make sure 'role', 'phone', and 'active' are editable in admin
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('role', 'phone', 'active', 'google_auth_id')}),
    )

@admin.register(Secret)
class SecretAdmin(admin.ModelAdmin):
    list_display = ('key_name', 'environment', 'updated_at')
    search_fields = ('key_name',)


@admin.register(SecurityQuestion)
class SecurityQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'question')
    search_fields = ('question',)
    ordering = ('id',)


@admin.register(UserSecurityAnswer)
class UserSecurityAnswerAdmin(admin.ModelAdmin):
    list_display = ('user', 'question', 'security_answer_hash')
    list_filter = ('question',)
    search_fields = ('user__username', 'user__email', 'question__question')
    readonly_fields = ('security_answer_hash',)


@admin.register(PrefilledDoctor)
class PrefilledDoctorAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'phone', 'specialty', 'city')
    list_filter = ('specialty', 'city')
    search_fields = ('full_name', 'email', 'phone', 'specialty', 'city')
    readonly_fields = ('id',)


@admin.register(RepLoginOTP)
class RepLoginOTPAdmin(admin.ModelAdmin):
    list_display = ('user', 'expires_at', 'sent_at', 'retry_count', 'is_expired')
    list_filter = ('expires_at', 'sent_at')
    search_fields = ('user__username', 'user__email', 'user__field_id')
    readonly_fields = ('otp_hash', 'sent_at')
    
    def is_expired(self, obj):
        return obj.is_expired()
    is_expired.boolean = True
    is_expired.short_description = 'Expired'    

@admin.register(LoginAuditWhatsApp)
class LoginAuditWhatsAppAdmin(admin.ModelAdmin):
    list_display = ('user', 'success', 'ip_address', 'created_at')
    list_filter = ('success', 'created_at')
    search_fields = ('user__username', 'user__email', 'user__field_id', 'ip_address')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
    
    def has_add_permission(self, request):
        return False  # Audit records should only be created by the system    