from __future__ import annotations

import csv
import json
import re
import uuid
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from django.db import connections
from django.utils import timezone


TARGET_CAMPAIGN_ID = "83ce7fc7c965433ab2b9717394abe3c1"
SYSTEM_NAME = "inclinic"
UUID_NAMESPACE = uuid.UUID("8a2f1b96-bf9c-47e3-a2c6-3c4eb266a2e2")


FIELD_REP_CONFLICT_TRANSACTION_EXCLUSION_CAMPAIGN_IDS = {
    TARGET_CAMPAIGN_ID,
}


LEGACY_DOCTOR_REP_ALIASES = [
    ("1568", "Madanraj A", "45", "49"),
    ("329", "Satyanarayana V V", "58", "24"),
    ("4614", "Rakhi Singh", "64", "91"),
    ("3997", "Arvind Kumar", "86", "85"),
    ("285", "Tarak Maity", "179", "21"),
    ("1451", "Dipankar Kalita", "175", "46"),
    ("2731", "Nipan Deka", "174", "71"),
    ("2564", "Manjunath S Nashi", "114", "66"),
    ("5763", "Baswaraj Shivling Biradar", "115", "116"),
    ("1276", "Rajib Nag", "118", "43"),
    ("1170", "Purnajit Ghosh", "128", "41"),
    ("1318", "Ravi Kumar Singh", "129", "44"),
    ("2282", "Rakesh Chandran A R", "138", "60"),
    ("145", "Sunil Pola", "140", "17"),
    ("4955", "Chandra Mohan Reddy P", "94", "97"),
    ("2949", "Vinay K", "93", "76"),
    ("151", "Suresh Kumar K C", "145", "18"),
    ("12013", "Bharath H B", "92", "152"),
    ("2335", "Vinod Kumar Singh", "146", "63"),
    ("3917", "Mohd Amir", "147", "83"),
    ("12851", "Devakinandan", "148", "155"),
    ("346", "Deepak Kumar Mallik", "160", "26"),
    ("1799", "Jiten Kumar Sahoo", "161", "52"),
    ("4628", "Ranjit Sharma", "170", "92"),
    ("5642", "Rishav Jain", "172", "110"),
]


def stable_uuid(*parts: Any) -> str:
    text = ":".join(str(p or "") for p in parts)
    return uuid.uuid5(UUID_NAMESPACE, text).hex


def normalize_campaign_id(value: Any) -> str:
    return re.sub(r"[^0-9a-fA-F]+", "", str(value or "")).lower()


def normalize_phone(value: Any) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    if len(digits) == 12 and digits.startswith("91"):
        return digits[-10:]
    if len(digits) > 10:
        return digits[-10:]
    return digits


DUPLICATE_ASM_DOCTOR_OVERRIDES = {
    "7086179396": {
        "expected_brand_supplied_field_rep_id": "1451",
        "preferred_doctor_viewer_doctor_id": "619",
        "doctor_names": "SUMEET KR BAKALI / SUMIT KR BAKALI",
    },
    "8355911135": {
        "expected_brand_supplied_field_rep_id": "7516",
        "preferred_doctor_viewer_doctor_id": "2400",
        "doctor_names": "Dr Imran Ali Rizvi / Imran Ali Rizvi",
    },
    "9474985364": {
        "expected_brand_supplied_field_rep_id": "337",
        "preferred_doctor_viewer_doctor_id": "200",
        "doctor_names": "DR S K SHAHABUDDIN / Dr Sk Sahabuddin",
    },
    "9840095669": {
        "expected_brand_supplied_field_rep_id": "2323",
        "preferred_doctor_viewer_doctor_id": "941",
        "doctor_names": "DR L K PREAM KUMAR / DR.L.K. PREMKUMAR",
    },
}


WRONG_DOCTOR_NUMBER_EXCLUSIONS = [
    {
        "brand_supplied_field_rep_id": "10340",
        "field_rep_name": "Sangayya Mugandamath",
        "doctor_name": "Dr.SHOAIB NAGATHAN",
        "doctor_number_raw_digits": "99862652552",
    },
    {
        "brand_supplied_field_rep_id": "10340",
        "field_rep_name": "Sangayya Mugandamath",
        "doctor_name": "Dr.J Prakash",
        "doctor_number_raw_digits": "964512884",
    },
    {
        "brand_supplied_field_rep_id": "4861",
        "field_rep_name": "Arvind Kumar Yadav",
        "doctor_name": "Dr.L.J.Yadav",
        "doctor_number_raw_digits": "94153769938",
    },
    {
        "brand_supplied_field_rep_id": "4158",
        "field_rep_name": "Ashok Kumar M",
        "doctor_name": "DR. MD MUKEED AHMEED",
        "doctor_number_raw_digits": "990203335",
    },
    {
        "brand_supplied_field_rep_id": "5277",
        "field_rep_name": "Arvind Choudhary",
        "doctor_name": "Akhilendra Parihar",
        "doctor_number_raw_digits": "787943657",
    },
    {
        "brand_supplied_field_rep_id": "5053",
        "field_rep_name": "Santosh Mishra",
        "doctor_name": "Abhijeet Manjundar",
        "doctor_number_raw_digits": "993612429",
    },
    {
        "brand_supplied_field_rep_id": "5053",
        "field_rep_name": "Santosh Mishra",
        "doctor_name": "H.p singh",
        "doctor_number_raw_digits": "94155544282",
    },
    {
        "brand_supplied_field_rep_id": "9535",
        "field_rep_name": "Chandra Bhushan Pandey",
        "doctor_name": "K.c Ramnani",
        "doctor_number_raw_digits": "989827620",
    },
    {
        "brand_supplied_field_rep_id": "285",
        "field_rep_name": "Tarak Maity",
        "doctor_name": "Dr. Sanjana Ghosh",
        "doctor_number_raw_digits": "98631365",
    },
]


WRONG_DOCTOR_NUMBER_EXCLUSIONS_BY_RAW_DIGITS = {
    row["doctor_number_raw_digits"]: row for row in WRONG_DOCTOR_NUMBER_EXCLUSIONS
}


def normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\b(dr|doctor|mr|mrs|ms|miss|sr)\.?\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def to_json(value: Any) -> str:
    def default(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return str(obj)

    return json.dumps(value, default=default, ensure_ascii=True, sort_keys=True)


def source_database(alias: str) -> str:
    return connections[alias].settings_dict.get("NAME") or alias


def table_exists(alias: str, table: str) -> bool:
    conn = connections[alias]
    try:
        with conn.cursor() as cursor:
            return table in conn.introspection.table_names(cursor)
    except Exception:
        return False


def fetch_rows(alias: str, table: str) -> list[dict[str, Any]]:
    if not table_exists(alias, table):
        return []
    conn = connections[alias]
    qn = conn.ops.quote_name
    with conn.cursor() as cursor:
        cursor.execute(f"SELECT * FROM {qn(table)}")
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def load_source_csv(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []

    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    active_rows = [
        {key: (None if value == "" else value) for key, value in row.items()}
        for row in rows
        if str(row.get("_is_deleted", "")).strip().lower() not in {"1", "true", "t", "yes", "y"}
    ]
    return latest_by_pk(active_rows)


def latest_by_pk(rows: Iterable[dict[str, Any]], pk: str = "id") -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = clean_text(row.get(pk))
        if not key:
            continue
        old = best.get(key)
        old_ts = clean_text(old.get("_ingested_at")) if old else ""
        new_ts = clean_text(row.get("_ingested_at"))
        if old is None or new_ts >= old_ts:
            best[key] = row
    return list(best.values())


def common_fields(
    *,
    alias: str,
    table: str,
    row: dict[str, Any],
    batch_id: str,
    verification_status: str,
    verification_basis: str,
    source_system: str = SYSTEM_NAME,
    pk_column: str = "id",
) -> dict[str, Any]:
    return {
        "source_system": source_system,
        "source_database": source_database(alias),
        "source_table": table,
        "source_pk_column": pk_column,
        "source_pk_value": clean_text(row.get(pk_column)),
        "source_created_at": row.get("created_at") or row.get("date_created") or row.get("share_timestamp"),
        "source_updated_at": row.get("updated_at"),
        "migration_batch_id": batch_id,
        "migrated_at": timezone.now(),
        "verification_status": verification_status,
        "verification_basis": verification_basis,
        "is_current": True,
        "valid_from": row.get("created_at") or row.get("date_joined") or row.get("share_timestamp"),
        "valid_to": None,
        "raw_payload_json": to_json(row),
    }


def update_by_pk(model, pk_value: str, defaults: dict[str, Any]):
    pk_name = model._meta.pk.name
    obj, created = model.objects.update_or_create(
        **{pk_name: pk_value},
        defaults=defaults,
    )
    return obj, created


def parse_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    if text in {"0", "false", "f", "no", "n", ""}:
        return False
    return None


def parse_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def parse_mismatch_csv(path: str | Path) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    parsed: list[dict[str, str]] = []
    exceptions: list[dict[str, Any]] = []
    path = Path(path)
    if not path.exists():
        return parsed, [
            {
                "source_pk_value": str(path),
                "entity_type": "assigned_doctor",
                "issue_code": "MISMATCH_FILE_NOT_FOUND",
                "issue_details": {"path": str(path)},
                "raw_payload": {},
            }
        ]

    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row_number, row in enumerate(reader, start=2):
            brand_id = clean_text(row.get("ID"))
            rep_label = clean_text(row.get("mail"))
            lines = [clean_text(line) for line in clean_text(row.get("doctor")).splitlines()]
            lines = [line for line in lines if line]
            i = 0
            while i < len(lines):
                doctor_name = lines[i]
                phone = lines[i + 1] if i + 1 < len(lines) else ""
                if not normalize_phone(phone):
                    exceptions.append(
                        {
                            "source_pk_value": f"{row_number}:{brand_id}:{doctor_name}",
                            "entity_type": "assigned_doctor",
                            "issue_code": "MISMATCH_DOCTOR_PHONE_MISSING",
                            "issue_details": {
                                "row_number": row_number,
                                "brand_supplied_field_rep_id": brand_id,
                                "field_rep_label": rep_label,
                                "doctor_name": doctor_name,
                                "phone_candidate": phone,
                            },
                            "raw_payload": row,
                        }
                    )
                    i += 1
                    continue
                parsed.append(
                    {
                        "row_number": str(row_number),
                        "brand_supplied_field_rep_id": brand_id,
                        "field_rep_label": rep_label,
                        "doctor_name_raw": doctor_name,
                        "doctor_phone_raw": phone,
                        "doctor_name_normalized": normalize_name(doctor_name),
                        "doctor_phone_normalized": normalize_phone(phone),
                    }
                )
                i += 2
    return parsed, exceptions


def group_by(rows: Iterable[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        out[clean_text(row.get(key))].append(row)
    return out


def first_by(rows: Iterable[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = clean_text(row.get(key))
        if value and value not in out:
            out[value] = row
    return out
