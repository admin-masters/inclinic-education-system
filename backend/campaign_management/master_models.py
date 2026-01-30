# campaign_management/master_models.py

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password as django_check_password


# ─────────────────────────────────────────────────────────
# Master DB configuration
# ─────────────────────────────────────────────────────────
MASTER_DB_ALIAS = getattr(settings, "MASTER_DB_ALIAS", "master")

MASTER_BRAND_DB_TABLE = getattr(settings, "MASTER_BRAND_DB_TABLE", "campaign_brand")
MASTER_CAMPAIGN_DB_TABLE = getattr(settings, "MASTER_CAMPAIGN_DB_TABLE", "campaign_campaign")

# Master auth + fieldrep tables
MASTER_AUTH_USER_TABLE = getattr(settings, "MASTER_AUTH_USER_TABLE", "auth_user")
MASTER_FIELD_REP_TABLE = getattr(settings, "MASTER_DB_FIELD_REP_TABLE", "campaign_fieldrep")
MASTER_CAMPAIGN_FIELD_REP_TABLE = getattr(
    settings, "MASTER_DB_CAMPAIGN_FIELD_REP_TABLE", "campaign_campaignfieldrep"
)


# ─────────────────────────────────────────────────────────
# Master Brand / Campaign (existing in your setup)
# ─────────────────────────────────────────────────────────
class MasterBrand(models.Model):
    """
    Master DB brand table.
    NOTE: Keep the fields aligned with your master DB.
    """
    id = models.CharField(max_length=36, primary_key=True)  # often UUID with hyphens
    name = models.CharField(max_length=255, blank=True, default="")
    company_name = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        managed = False
        db_table = MASTER_BRAND_DB_TABLE

    def __str__(self) -> str:
        return self.name or str(self.id)


class MasterCampaign(models.Model):
    """
    Master DB campaign table.

    IMPORTANT: master campaign `id` is UUID without hyphens (32 hex chars),
    while portal uses dashed UUID (brand_campaign_id).
    """
    id = models.CharField(max_length=32, primary_key=True)  # dashless uuid hex
    name = models.CharField(max_length=255, blank=True, default="")
    brand = models.ForeignKey(
        MasterBrand,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="campaigns",
    )

    # Optional fields (keep if present in master DB)
    company_name = models.CharField(max_length=255, blank=True, default="")
    brand_name = models.CharField(max_length=255, blank=True, default="")
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    register_message = models.TextField(blank=True, default="")
    add_to_campaign_message = models.TextField(blank=True, default="")
    num_doctors_supported = models.IntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = MASTER_CAMPAIGN_DB_TABLE

    @property
    def brand_campaign_id(self) -> str:
        """
        Convenience: dashed UUID string used by the portal.
        """
        try:
            return str(uuid.UUID(hex=str(self.id)))
        except Exception:
            return str(self.id)

    def __str__(self) -> str:
        return self.name or self.brand_campaign_id


# ─────────────────────────────────────────────────────────
# Master auth_user (minimal)
# ─────────────────────────────────────────────────────────
class MasterAuthUser(models.Model):
    """
    Minimal mapping for master DB `auth_user`.
    We only need enough fields to create/update and link to campaign_fieldrep.
    """
    id = models.AutoField(primary_key=True)
    password = models.CharField(max_length=128, default="")
    last_login = models.DateTimeField(null=True, blank=True)

    is_superuser = models.BooleanField(default=False)
    username = models.CharField(max_length=150, unique=True)

    first_name = models.CharField(max_length=150, blank=True, default="")
    last_name = models.CharField(max_length=150, blank=True, default="")
    email = models.EmailField(blank=True, default="")

    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    date_joined = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = MASTER_AUTH_USER_TABLE

    def __str__(self) -> str:
        return self.email or self.username or str(self.id)


# ─────────────────────────────────────────────────────────
# Master FieldRep + CampaignFieldRep
# ─────────────────────────────────────────────────────────
class MasterFieldRep(models.Model):
    """
    Master table: campaign_fieldrep
    """
    user = models.OneToOneField(
        MasterAuthUser,
        on_delete=models.CASCADE,
        db_constraint=False,
    )
    brand = models.ForeignKey(
        MasterBrand,
        on_delete=models.CASCADE,
        related_name="field_reps",
        db_constraint=False,
    )

    full_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=50, blank=True)
    brand_supplied_field_rep_id = models.CharField(max_length=100, blank=True)

    is_active = models.BooleanField(default=True)

    # hashed password for field-rep portal (per your snippet)
    password_hash = models.CharField(max_length=128, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = MASTER_FIELD_REP_TABLE

    def set_password(self, raw_password: str) -> None:
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        if not self.password_hash:
            return False
        return django_check_password(raw_password, self.password_hash)

    def has_password(self) -> bool:
        return bool(self.password_hash)

    def __str__(self) -> str:
        return f"{self.full_name} ({self.user.email})"


class MasterCampaignFieldRep(models.Model):
    """
    Master join table: campaign_campaignfieldrep
    """
    campaign = models.ForeignKey(
        MasterCampaign,
        on_delete=models.CASCADE,
        related_name="fieldrep_links",
        db_constraint=False,
    )
    field_rep = models.ForeignKey(
        MasterFieldRep,
        on_delete=models.CASCADE,
        related_name="campaign_links",
        db_constraint=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = MASTER_CAMPAIGN_FIELD_REP_TABLE
        unique_together = ("campaign", "field_rep")
        indexes = [models.Index(fields=["campaign", "field_rep"])]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.campaign_id} / {self.field_rep_id}"
