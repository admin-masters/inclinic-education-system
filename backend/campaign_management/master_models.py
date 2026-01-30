# master_models.py
from __future__ import annotations

from django.conf import settings
from django.db import models


class MasterBrand(models.Model):
    id = models.CharField(max_length=36, primary_key=True)  # was UUIDField
    name = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        managed = False
        db_table = getattr(settings, "MASTER_BRAND_DB_TABLE", "campaign_brand")


class MasterCampaign(models.Model):
    id = models.CharField(max_length=32, primary_key=True)  # was UUIDField, now dashless string
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


# campaign_management/master_models.py  (APPEND BELOW YOUR EXISTING MasterBrand / MasterCampaign)

from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password as django_check_password
from django.db import models
from django.utils import timezone

# Table names are configurable via settings (you already have these in settings.py)
MASTER_AUTH_USER_TABLE = getattr(settings, "MASTER_AUTH_USER_TABLE", "auth_user")
MASTER_FIELDREP_TABLE = getattr(settings, "MASTER_DB_FIELD_REP_TABLE", "campaign_fieldrep")
MASTER_CAMPAIGN_FIELDREP_TABLE = getattr(settings, "MASTER_DB_CAMPAIGN_FIELD_REP_TABLE", "campaign_campaignfieldrep")


class MasterAuthUser(models.Model):
    """
    Mirrors the master DB Django auth_user table (per your note).
    This is required because your portal AUTH_USER_MODEL is user_management.User,
    but master DB uses auth_user.
    """
    id = models.AutoField(primary_key=True)
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(null=True, blank=True)
    is_superuser = models.BooleanField(default=False)

    username = models.CharField(max_length=150, unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = MASTER_AUTH_USER_TABLE

    def __str__(self) -> str:
        return f"{self.username} ({self.email})"


class MasterFieldRep(models.Model):
    """
    Master DB table: campaign_fieldrep
    Links master auth_user to a brand + rep metadata.
    """
    user = models.OneToOneField(
        MasterAuthUser,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="field_rep",
        db_constraint=False,
    )
    brand = models.ForeignKey(
        "MasterBrand",
        on_delete=models.CASCADE,
        db_column="brand_id",
        related_name="field_reps",
        db_constraint=False,
    )

    full_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=50, blank=True)
    brand_supplied_field_rep_id = models.CharField(max_length=100, blank=True)

    is_active = models.BooleanField(default=True)

    # hashed password for field-rep portal (if you use it)
    password_hash = models.CharField(max_length=128, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = MASTER_FIELDREP_TABLE

    def set_password(self, raw_password: str) -> None:
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        if not self.password_hash:
            return False
        return django_check_password(raw_password, self.password_hash)

    def has_password(self) -> bool:
        return bool(self.password_hash)

    def __str__(self) -> str:
        return f"{self.full_name} ({getattr(self.user, 'email', '')})"


class MasterCampaignFieldRep(models.Model):
    """
    Master join table: campaign_campaignfieldrep
    Maps field reps to master campaigns (campaign_id stored as 32 hex without hyphens).
    """
    campaign = models.ForeignKey(
        "MasterCampaign",
        on_delete=models.CASCADE,
        db_column="campaign_id",
        related_name="fieldrep_links",
        db_constraint=False,
    )
    field_rep = models.ForeignKey(
        MasterFieldRep,
        on_delete=models.CASCADE,
        db_column="field_rep_id",
        related_name="campaign_links",
        db_constraint=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = MASTER_CAMPAIGN_FIELDREP_TABLE
        unique_together = ("campaign", "field_rep")
        indexes = [models.Index(fields=["campaign", "field_rep"])]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.campaign_id} / {self.field_rep_id}"
