from django.contrib import admin
from .models import FieldRepCampaign
from django.utils.html import format_html

@admin.register(FieldRepCampaign)
class FieldRepCampaignAdmin(admin.ModelAdmin):
    list_display = (
        "uid",
        "field_id",
        "gmail",
        "phone",
        "campaign",
        "brand_campaign_id",
        "assigned_at",
        "action_buttons",  # ✅ updated here
    )
    list_filter = ("campaign__brand_campaign_id",)
    search_fields = (
        "field_rep__username",
        "field_rep__field_id",
        "field_rep__email",
        "campaign__name",
        "campaign__brand_campaign_id",
        "uid",
    )
    readonly_fields = ("uid",)

    # --- columns supplied by model properties ---
    def field_id(self, obj):
        return obj.field_rep.field_id

    def gmail(self, obj):
        return obj.field_rep.email

    def phone(self, obj):
        return obj.field_rep.phone_number

    def brand_campaign_id(self, obj):
        return obj.campaign.brand_campaign_id

    # --- renamed from `actions` to avoid Django conflict ---
    def action_buttons(self, obj):  # ✅ renamed
        edit_url = f"/admin/admin_dashboard/fieldrepcampaign/{obj.pk}/change/"
        delete_url = f"/admin/admin_dashboard/fieldrepcampaign/{obj.pk}/delete/"
        return format_html(
            '<a class="button" href="{}">Edit</a>&nbsp;'
            '<a class="button" href="{}">Delete</a>',
            edit_url,
            delete_url,
        )
    action_buttons.short_description = "Actions"
    action_buttons.allow_tags = True
