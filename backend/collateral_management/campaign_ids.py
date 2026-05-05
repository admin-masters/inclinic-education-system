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
