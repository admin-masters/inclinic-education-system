# user_management/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

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