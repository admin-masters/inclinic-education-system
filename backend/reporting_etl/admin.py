# reporting_etl/admin.py
from django.contrib import admin
from reporting_etl.models import EtlState

@admin.register(EtlState)
class EtlStateAdmin(admin.ModelAdmin):
    list_display = ('model_name', 'last_synced')