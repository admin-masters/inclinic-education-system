from __future__ import annotations

import re
import uuid
from datetime import datetime, time

from django.conf import settings
from django.utils import timezone

_CAMPAIGN_UUID_DASHED_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_CAMPAIGN_HEX32_RE = re.compile(r"^[0-9a-fA-F]{32}$")


def _trim(value) -> str:
    return str(value or "").strip()


def _uuid_from_value(raw: str) -> uuid.UUID | None:
    value = _trim(raw)
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except Exception:
        compact = re.sub(r"[^0-9a-fA-F]", "", value)
        if len(compact) == 32 and _CAMPAIGN_HEX32_RE.match(compact):
            try:
                return uuid.UUID(compact)
            except Exception:
                return None
    return None


def normalize_campaign_id(raw: str) -> str:
    """
    Canonical local representation for master UUID campaign IDs is dashless hex.
    Non-UUID campaign IDs are returned unchanged except for trimming.
    """
    value = _trim(raw)
    if not value:
        return ""

    parsed_uuid = _uuid_from_value(value)
    if parsed_uuid:
        return parsed_uuid.hex

    if _CAMPAIGN_UUID_DASHED_RE.match(value):
        return value.lower().replace("-", "")
    if _CAMPAIGN_HEX32_RE.match(value):
        return value.lower()
    return value


def campaign_id_variants(raw: str) -> list[str]:
    value = _trim(raw)
    if not value:
        return []

    variants: list[str] = []

    def add(candidate: str):
        candidate = _trim(candidate)
        if candidate and candidate not in variants:
            variants.append(candidate)

    add(value)

    parsed_uuid = _uuid_from_value(value)
    if parsed_uuid:
        add(parsed_uuid.hex)
        add(str(parsed_uuid))
    else:
        normalized = normalize_campaign_id(value)
        if normalized != value:
            add(normalized)

    return variants


def master_db_alias() -> str:
    alias = getattr(settings, "MASTER_DB_ALIAS", None)
    if alias:
        return alias
    for candidate in ("master", "master_db", "MASTER"):
        if candidate in getattr(settings, "DATABASES", {}):
            return candidate
    return "master"


def _coerce_campaign_datetime(value, *, is_end: bool = False):
    if not value:
        return timezone.now()
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            return timezone.make_aware(value, timezone.get_current_timezone())
        return value
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        base_time = time.max.replace(microsecond=0) if is_end else time.min
        dt = datetime.combine(value, base_time)
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return timezone.now()


def resolve_portal_campaign(brand_campaign_id: str, *, using: str = "default", sync_from_master: bool = False):
    from campaign_management.models import Campaign

    raw_value = _trim(brand_campaign_id)
    variants = campaign_id_variants(brand_campaign_id)
    campaign = None

    if variants:
        campaign = (
            Campaign.objects.using(using)
            .filter(brand_campaign_id__in=variants)
            .order_by("-updated_at", "-id")
            .first()
        )
    if not campaign and raw_value.isdigit():
        campaign = (
            Campaign.objects.using(using)
            .filter(id=int(raw_value))
            .order_by("-updated_at", "-id")
            .first()
        )
    if campaign or not sync_from_master or using != "default":
        return campaign

    return ensure_portal_campaign(brand_campaign_id)


def canonical_brand_campaign_id(brand_campaign_id: str, *, using: str = "default", sync_from_master: bool = False) -> str:
    """
    Canonical local storage value for campaign references.
    UUID-based campaign IDs are stored as dashless 32-char strings.
    Legacy marketing IDs are preserved as-is.
    Numeric local campaign PKs are resolved to the campaign's brand_campaign_id.
    """
    raw_value = _trim(brand_campaign_id)
    if not raw_value:
        return ""

    campaign = resolve_portal_campaign(raw_value, using=using, sync_from_master=sync_from_master)
    if campaign and getattr(campaign, "brand_campaign_id", None):
        return normalize_campaign_id(campaign.brand_campaign_id)

    return normalize_campaign_id(raw_value)


def tracking_campaign_id_variants(brand_campaign_id: str, *, using: str = "default", sync_from_master: bool = False) -> list[str]:
    """
    Variants to match historical tracking rows.
    Includes:
    - dashed/dashless/legacy campaign IDs
    - local campaign PK as string (for older ShareLog rows that stored it incorrectly)
    """
    variants = campaign_id_variants(brand_campaign_id)
    campaign = resolve_portal_campaign(brand_campaign_id, using=using, sync_from_master=sync_from_master)
    if campaign:
        pk_value = _trim(getattr(campaign, "pk", ""))
        if pk_value and pk_value not in variants:
            variants.append(pk_value)
    return variants


def ensure_portal_campaign(brand_campaign_id: str):
    from campaign_management.master_models import MasterCampaign
    from campaign_management.models import Campaign

    campaign = resolve_portal_campaign(brand_campaign_id, sync_from_master=False)
    if campaign:
        return campaign

    variants = campaign_id_variants(brand_campaign_id)
    if not variants:
        return None

    alias = master_db_alias()
    master_campaign = None
    base_qs = MasterCampaign.objects.using(alias).select_related("brand")

    for candidate in variants:
        try:
            parsed_uuid = _uuid_from_value(candidate)
            master_campaign = base_qs.filter(id=parsed_uuid or candidate).first()
        except Exception:
            master_campaign = None
        if master_campaign:
            break

    if not master_campaign:
        return None

    normalized_bcid = normalize_campaign_id(str(getattr(master_campaign, "id", "") or brand_campaign_id))
    campaign = resolve_portal_campaign(normalized_bcid, sync_from_master=False)
    if campaign:
        return campaign

    master_brand = getattr(master_campaign, "brand", None)
    master_status = (getattr(master_campaign, "status", "") or "").strip().lower()
    status_map = {
        "draft": "Draft",
        "published": "Active",
        "active": "Active",
        "archived": "Completed",
        "completed": "Completed",
    }

    campaign = Campaign.objects.create(
        name=(getattr(master_campaign, "name", "") or normalized_bcid or "Campaign").strip() or "Campaign",
        brand_name=(getattr(master_brand, "name", "") or "").strip() or None,
        brand_campaign_id=normalized_bcid,
        start_date=_coerce_campaign_datetime(getattr(master_campaign, "start_date", None), is_end=False),
        end_date=_coerce_campaign_datetime(getattr(master_campaign, "end_date", None), is_end=True),
        description=(getattr(master_campaign, "add_to_campaign_message", "") or "").strip(),
        company_name=(getattr(master_brand, "name", "") or "").strip() or None,
        incharge_name=(getattr(master_campaign, "contact_person_name", "") or "").strip() or None,
        incharge_contact=(getattr(master_campaign, "contact_person_phone", "") or "").strip() or None,
        num_doctors=getattr(master_campaign, "num_doctors_supported", None) or None,
        status=status_map.get(master_status, "Draft"),
    )
    return campaign
