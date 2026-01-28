from __future__ import annotations

from django.conf import settings
from django.db import models


class MasterBrand(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    name = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        managed = False
        db_table = getattr(settings, "MASTER_BRAND_DB_TABLE", "Brand")


class MasterCampaign(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)

    brand = models.ForeignKey(
        MasterBrand,
        on_delete=models.DO_NOTHING,
        related_name="campaigns",
        null=True,
        blank=True,
        db_constraint=False,
        db_column="brand_id",
    )

    name = models.CharField(max_length=200, blank=True, default="")

    contact_person_name = models.CharField(max_length=200, blank=True, default="")
    contact_person_phone = models.CharField(max_length=50, blank=True, default="")
    contact_person_email = models.EmailField(blank=True, default="")

    num_doctors_supported = models.PositiveIntegerField(default=0)

    class Meta:
        managed = False
        db_table = getattr(settings, "MASTER_CAMPAIGN_DB_TABLE", "campaign_campaign")
