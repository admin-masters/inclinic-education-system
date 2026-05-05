import re
import uuid

_CAMPAIGN_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_CAMPAIGN_HEX32_RE = re.compile(r"^[0-9a-fA-F]{32}$")


def normalize_campaign_id(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if _CAMPAIGN_UUID_RE.match(lowered):
        return lowered.replace("-", "")
    if _CAMPAIGN_HEX32_RE.match(lowered):
        return lowered
    compact = re.sub(r"[^0-9a-f]", "", lowered)
    if len(compact) == 32:
        return compact
    return lowered.replace("-", "")


def campaign_id_variants(raw: str) -> list[str]:
    value = (raw or "").strip()
    if not value:
        return []

    variants: list[str] = []

    def add(candidate: str):
        candidate = (candidate or "").strip()
        if candidate and candidate not in variants:
            variants.append(candidate)

    add(value)
    norm = normalize_campaign_id(value)
    add(norm)

    if norm and len(norm) == 32 and _CAMPAIGN_HEX32_RE.match(norm):
        try:
            add(str(uuid.UUID(norm)))
        except Exception:
            pass
    else:
        try:
            add(str(uuid.UUID(value)))
        except Exception:
            pass

    return variants

from datetime import datetime, time
from django.utils import timezone


def _master_db_alias() -> str:
    from django.conf import settings
    alias = getattr(settings, "MASTER_DB_ALIAS", None)
    if alias:
        return alias
    for cand in ("master", "master_db", "MASTER"):
        if cand in getattr(settings, "DATABASES", {}):
            return cand
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


def ensure_portal_campaign(brand_campaign_id: str):
    from campaign_management.models import Campaign
    from campaign_management.master_models import MasterCampaign

    variants = campaign_id_variants(brand_campaign_id)
    if not variants:
        return None

    campaign = Campaign.objects.filter(brand_campaign_id__in=variants).first()
    if campaign:
        return campaign

    master_campaign = None
    alias = _master_db_alias()
    for candidate in variants:
        try:
            master_campaign = MasterCampaign.objects.using(alias).select_related("brand").filter(id=candidate).first()
        except Exception:
            master_campaign = None
        if master_campaign:
            break

    if not master_campaign:
        return None

    normalized_bcid = normalize_campaign_id(str(getattr(master_campaign, "id", "") or brand_campaign_id))
    campaign = Campaign.objects.filter(brand_campaign_id=normalized_bcid).first()
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
