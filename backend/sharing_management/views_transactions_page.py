from __future__ import annotations

import csv
from types import SimpleNamespace

from django.db.models import OuterRef, Subquery, F
from django.http import HttpResponse
from django.shortcuts import render

from campaign_management.campaign_ids import canonical_brand_campaign_id, tracking_campaign_id_variants
from collateral_management.models import CampaignCollateral as CMCampaignCollateral
from reporting_etl.inclinic_v2 import normalize_campaign_id, stable_uuid
from reporting_etl.models import InclinicCollateralTransactionV2
from reporting_etl.v2_switch import inclinic_v2_reads_enabled
from sharing_management.models import CollateralTransaction
from user_management.models import User


def collateral_transactions_dashboard(request, brand_campaign_id: str):
    brand_campaign_id = (str(brand_campaign_id) or "").strip()
    campaign_variants = tracking_campaign_id_variants(brand_campaign_id, sync_from_master=True)
    canonical_campaign_id = canonical_brand_campaign_id(brand_campaign_id, sync_from_master=True)

    v2_response = _collateral_transactions_dashboard_v2(
        request=request,
        brand_campaign_id=brand_campaign_id,
        campaign_variants=campaign_variants,
        canonical_campaign_id=canonical_campaign_id,
    )
    if v2_response is not None:
        return v2_response

    # --- Schema drift safety: inspect model field names at runtime ---
    model_field_names = {f.name for f in CollateralTransaction._meta.get_fields()}

    # Base queryset for this campaign
    qs = CollateralTransaction.objects.filter(brand_campaign_id__in=campaign_variants)

    # Collateral dropdown list (from campaign calendar table)
    collaterals_qs = (
        CMCampaignCollateral.objects
        .filter(campaign__brand_campaign_id__in=campaign_variants)
        .select_related("collateral")
        .order_by("-id")
    )

    seen = set()
    collaterals = []
    for cc in collaterals_qs:
        if not getattr(cc, "collateral_id", None) or cc.collateral_id in seen:
            continue
        if not getattr(cc, "collateral", None):
            continue
        seen.add(cc.collateral_id)
        collaterals.append({
            "id": cc.collateral_id,
            "title": getattr(cc.collateral, "title", str(cc.collateral)),
        })

    collateral_title_by_id = {c["id"]: c["title"] for c in collaterals}

    # Selected collateral filter
    selected_collateral_id = request.GET.get("collateral_id")
    try:
        selected_collateral_id_int = int(selected_collateral_id) if selected_collateral_id else None
    except (ValueError, TypeError):
        selected_collateral_id_int = None

    valid_ids = {c["id"] for c in collaterals}
    if selected_collateral_id_int and selected_collateral_id_int not in valid_ids:
        selected_collateral_id_int = None

    # --- Latest row per (doctor_number, collateral_id, field_rep_id) ---
    latest_updated = Subquery(
        CollateralTransaction.objects.filter(
            brand_campaign_id__in=campaign_variants,
            doctor_number=OuterRef("doctor_number"),
            collateral_id=OuterRef("collateral_id"),
            field_rep_id=OuterRef("field_rep_id"),
        )
        .order_by("-updated_at", "-id")
        .values("updated_at")[:1]
    )

    annotated = qs.annotate(last_updated=latest_updated)
    base_rows = annotated.filter(updated_at=F("last_updated"))

    if selected_collateral_id_int:
        base_rows = base_rows.filter(collateral_id=selected_collateral_id_int)

    rows = list(base_rows.order_by("-updated_at")[:1000])

    # --------------------------
    # Summary metrics (LATEST-only)
    # --------------------------
    total_unique_doctors = base_rows.values("doctor_number").distinct().count()

    # Clicked / viewed
    if "has_viewed" in model_field_names:
        clicked_doctors = base_rows.filter(has_viewed=True).values("doctor_number").distinct().count()
    elif "viewed_at" in model_field_names:
        clicked_doctors = base_rows.filter(viewed_at__isnull=False).values("doctor_number").distinct().count()
    elif "first_viewed_at" in model_field_names:
        clicked_doctors = base_rows.filter(first_viewed_at__isnull=False).values("doctor_number").distinct().count()
    else:
        clicked_doctors = 0

    # Downloaded PDF
    if "has_downloaded_pdf" in model_field_names:
        downloaded_field = "has_downloaded_pdf"
    elif "downloaded_pdf" in model_field_names:
        downloaded_field = "downloaded_pdf"
    else:
        downloaded_field = None
    downloaded_pdf_doctors = (
        base_rows.filter(**{downloaded_field: True}).values("doctor_number").distinct().count()
        if downloaded_field else 0
    )

    # Viewed last page
    # Prefer pdf_completed if present; else derive from pdf_last_page >= pdf_total_pages
    if "has_viewed_last_page" in model_field_names:
        viewed_last_page_doctors = base_rows.filter(has_viewed_last_page=True).values("doctor_number").distinct().count()
    elif "pdf_completed" in model_field_names:
        viewed_last_page_doctors = base_rows.filter(pdf_completed=True).values("doctor_number").distinct().count()
    elif "pdf_last_page" in model_field_names and "pdf_total_pages" in model_field_names:
        viewed_last_page_doctors = (
            base_rows.filter(pdf_total_pages__gt=0, pdf_last_page__gte=F("pdf_total_pages"))
            .values("doctor_number").distinct().count()
        )
    else:
        viewed_last_page_doctors = 0

    # Video buckets
    # Your model/table (per error page) uses video_watch_percentage + video_completed
    pct_field = None
    if "video_watch_percentage" in model_field_names:
        pct_field = "video_watch_percentage"
    elif "last_video_percentage" in model_field_names:
        pct_field = "last_video_percentage"

    if pct_field:
        video_lt_50_doctors = (
            base_rows.filter(**{f"{pct_field}__gt": 0, f"{pct_field}__lt": 50})
            .values("doctor_number").distinct().count()
        )
        video_gt_50_doctors = (
            base_rows.filter(**{f"{pct_field}__gte": 50, f"{pct_field}__lt": 100})
            .values("doctor_number").distinct().count()
        )
        if "video_completed" in model_field_names:
            video_100_doctors = base_rows.filter(video_completed=True).values("doctor_number").distinct().count()
        else:
            video_100_doctors = (
                base_rows.filter(**{f"{pct_field}__gte": 100}).values("doctor_number").distinct().count()
            )
    else:
        video_lt_50_doctors = 0
        video_gt_50_doctors = 0
        video_100_doctors = 0

    total_transactions = base_rows.count()

    # --------------------------
    # Row presentation helpers
    # --------------------------
    def _tx_datetime_part(row):
        dt = getattr(row, "sent_at", None) or getattr(row, "created_at", None) or getattr(row, "updated_at", None)
        if hasattr(dt, "strftime"):
            return dt.strftime("%Y%m%d%H%M%S")
        tx_date = getattr(row, "transaction_date", "")
        return str(tx_date).replace("-", "")

    # Prefer the brand-supplied field rep id stored with the transaction.
    # If old rows only have a portal User id, map it to User.field_id.
    rep_ids = []
    for r in rows:
        rid = getattr(r, "field_rep_id", None)
        rid_text = str(rid or "").strip()
        if rid_text.isdigit():
            rep_ids.append(int(rid_text))

    rep_map = {}
    if rep_ids:
        rep_map = {
            u.id: (u.field_id or str(u.id))
            for u in User.objects.filter(id__in=set(rep_ids)).only("id", "field_id")
        }

    for r in rows:
        rid = getattr(r, "field_rep_id", None)
        rid_text = str(rid or "").strip()
        rep_unique = (
            (getattr(r, "field_rep_unique_id", "") or "").strip()
            if "field_rep_unique_id" in model_field_names
            else ""
        )

        if rep_unique:
            rep_display = rep_unique
        elif rid_text.isdigit() and int(rid_text) in rep_map:
            rep_display = rep_map[int(rid_text)]
        else:
            rep_email = getattr(r, "field_rep_email", "") if "field_rep_email" in model_field_names else ""
            rep_display = rep_email or rid_text

        r.field_rep_display = rep_display
        stored_transaction_id = getattr(r, "transaction_id", "") if "transaction_id" in model_field_names else ""
        r.transaction_id_display = stored_transaction_id or f"{rep_display}-{r.doctor_number}-{r.collateral_id}-{_tx_datetime_part(r)}"
        r.collateral_title = collateral_title_by_id.get(r.collateral_id, "—")

        # Provide template-friendly aliases (won't crash template even if old names were used)
        r.has_downloaded_pdf = bool(getattr(r, downloaded_field, False)) if downloaded_field else False
        if "has_viewed_last_page" in model_field_names:
            r.has_viewed_last_page = bool(getattr(r, "has_viewed_last_page", False))
        elif "pdf_completed" in model_field_names:
            r.has_viewed_last_page = bool(getattr(r, "pdf_completed", False))
        elif "pdf_last_page" in model_field_names and "pdf_total_pages" in model_field_names:
            try:
                r.has_viewed_last_page = bool(r.pdf_total_pages and (r.pdf_last_page >= r.pdf_total_pages))
            except Exception:
                r.has_viewed_last_page = False
        else:
            r.has_viewed_last_page = False

    if request.GET.get("export"):
        filename = f"collateral-transactions-{brand_campaign_id}"
        if selected_collateral_id_int:
            filename += f"-collateral-{selected_collateral_id_int}"
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "transaction_id",
                "field_rep",
                "doctor_name",
                "doctor_number",
                "collateral_id",
                "collateral_title",
                "clicked",
                "pdf_downloaded",
                "viewed_last_page",
                "video_percentage",
                "video_events",
                "transaction_date",
                "updated_at",
            ]
        )

        for r in rows:
            writer.writerow(
                [
                    r.transaction_id_display,
                    r.field_rep_display,
                    r.doctor_name or "",
                    r.doctor_number,
                    r.collateral_id,
                    r.collateral_title,
                    1 if getattr(r, "has_viewed", False) else 0,
                    1 if getattr(r, "has_downloaded_pdf", False) else 0,
                    1 if getattr(r, "has_viewed_last_page", False) else 0,
                    getattr(r, "last_video_percentage", 0) if "last_video_percentage" in model_field_names else getattr(r, "video_watch_percentage", 0),
                    getattr(r, "total_video_events", 0),
                    getattr(r, "transaction_date", ""),
                    getattr(r, "updated_at", ""),
                ]
            )
        return response

    context = {
        "brand_campaign_id": canonical_campaign_id or brand_campaign_id,
        "collaterals": collaterals,
        "selected_collateral_id": selected_collateral_id_int,
        "summary_items": [
            ("Total Unique Doctors", total_unique_doctors),
            ("Clicked Doctors", clicked_doctors),
            ("PDF Downloaded Doctors", downloaded_pdf_doctors),
            ("Viewed Last Page Doctors", viewed_last_page_doctors),
            ("Video < 50% Doctors", video_lt_50_doctors),
            ("Video ≥ 50% Doctors", video_gt_50_doctors),
            ("Video 100% Doctors", video_100_doctors),
            ("Total Transactions", total_transactions),
        ],
        "rows": rows,
    }

    return render(request, "sharing_management/collateral_transactions_dashboard.html", context)


def _collateral_transactions_dashboard_v2(*, request, brand_campaign_id: str, campaign_variants: list[str], canonical_campaign_id: str):
    if not inclinic_v2_reads_enabled():
        return None

    campaign_uuid = stable_uuid("campaign", normalize_campaign_id(canonical_campaign_id or brand_campaign_id))
    base_qs = InclinicCollateralTransactionV2.objects.filter(
        campaign_uuid=campaign_uuid,
        is_current=True,
    )
    if not base_qs.exists():
        return None

    collaterals_qs = (
        CMCampaignCollateral.objects
        .filter(campaign__brand_campaign_id__in=campaign_variants)
        .select_related("collateral")
        .order_by("-id")
    )
    seen = set()
    collaterals = []
    for cc in collaterals_qs:
        if not getattr(cc, "collateral_id", None) or cc.collateral_id in seen:
            continue
        if not getattr(cc, "collateral", None):
            continue
        seen.add(cc.collateral_id)
        collaterals.append({
            "id": cc.collateral_id,
            "title": getattr(cc.collateral, "title", str(cc.collateral)),
        })
    collateral_title_by_id = {str(c["id"]): c["title"] for c in collaterals}

    selected_collateral_id = request.GET.get("collateral_id")
    try:
        selected_collateral_id_int = int(selected_collateral_id) if selected_collateral_id else None
    except (ValueError, TypeError):
        selected_collateral_id_int = None
    valid_ids = {c["id"] for c in collaterals}
    if selected_collateral_id_int and selected_collateral_id_int not in valid_ids:
        selected_collateral_id_int = None
    if selected_collateral_id_int:
        base_qs = base_qs.filter(old_collateral_id=str(selected_collateral_id_int))

    raw_rows = list(
        base_qs.order_by(
            "-old_updated_at",
            "-old_last_viewed_at",
            "-old_viewed_at",
            "-old_sent_at",
            "-old_id",
        )
    )
    latest = {}
    for tx in raw_rows:
        key = (
            tx.doctor_phone_normalized or tx.old_doctor_number or "",
            tx.old_collateral_id or "",
            tx.resolved_field_rep_uuid or tx.campaign_fieldrep_id or "",
        )
        if key not in latest:
            latest[key] = tx

    v2_rows = list(latest.values())
    rows = [_present_v2_transaction_row(tx, collateral_title_by_id) for tx in v2_rows[:1000]]

    total_unique_doctors = len({
        tx.doctor_phone_normalized or tx.old_doctor_number
        for tx in v2_rows
        if tx.doctor_phone_normalized or tx.old_doctor_number
    })
    clicked_doctors = len({
        tx.doctor_phone_normalized or tx.old_doctor_number
        for tx in v2_rows
        if tx.old_has_viewed or tx.old_viewed_at or tx.old_first_viewed_at
    })
    downloaded_pdf_doctors = len({
        tx.doctor_phone_normalized or tx.old_doctor_number
        for tx in v2_rows
        if tx.old_downloaded_pdf
    })
    viewed_last_page_doctors = len({
        tx.doctor_phone_normalized or tx.old_doctor_number
        for tx in v2_rows
        if tx.old_pdf_completed
    })
    video_lt_50_doctors = len({
        tx.doctor_phone_normalized or tx.old_doctor_number
        for tx in v2_rows
        if (tx.old_video_view_lt_50 or 0) > 0 and (tx.old_last_video_percentage or tx.old_video_watch_percentage or 0) < 50
    })
    video_gt_50_doctors = len({
        tx.doctor_phone_normalized or tx.old_doctor_number
        for tx in v2_rows
        if 50 <= (tx.old_last_video_percentage or tx.old_video_watch_percentage or 0) < 100
    })
    video_100_doctors = len({
        tx.doctor_phone_normalized or tx.old_doctor_number
        for tx in v2_rows
        if tx.old_video_completed or (tx.old_last_video_percentage or tx.old_video_watch_percentage or 0) >= 100
    })

    if request.GET.get("export"):
        filename = f"collateral-transactions-{brand_campaign_id}"
        if selected_collateral_id_int:
            filename += f"-collateral-{selected_collateral_id_int}"
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "transaction_id",
                "field_rep",
                "doctor_name",
                "doctor_number",
                "collateral_id",
                "collateral_title",
                "clicked",
                "pdf_downloaded",
                "viewed_last_page",
                "video_percentage",
                "video_events",
                "transaction_date",
                "updated_at",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.transaction_id_display,
                    r.field_rep_display,
                    r.doctor_name or "",
                    r.doctor_number,
                    r.collateral_id,
                    r.collateral_title,
                    1 if getattr(r, "has_viewed", False) else 0,
                    1 if getattr(r, "has_downloaded_pdf", False) else 0,
                    1 if getattr(r, "has_viewed_last_page", False) else 0,
                    getattr(r, "last_video_percentage", 0),
                    getattr(r, "total_video_events", 0),
                    getattr(r, "transaction_date", ""),
                    getattr(r, "updated_at", ""),
                ]
            )
        return response

    context = {
        "brand_campaign_id": canonical_campaign_id or brand_campaign_id,
        "collaterals": collaterals,
        "selected_collateral_id": selected_collateral_id_int,
        "summary_items": [
            ("Total Unique Doctors", total_unique_doctors),
            ("Clicked Doctors", clicked_doctors),
            ("PDF Downloaded Doctors", downloaded_pdf_doctors),
            ("Viewed Last Page Doctors", viewed_last_page_doctors),
            ("Video < 50% Doctors", video_lt_50_doctors),
            ("Video ≥ 50% Doctors", video_gt_50_doctors),
            ("Video 100% Doctors", video_100_doctors),
            ("Total Transactions", len(v2_rows)),
        ],
        "rows": rows,
        "data_source": "v2",
    }
    return render(request, "sharing_management/collateral_transactions_dashboard.html", context)


def _present_v2_transaction_row(tx: InclinicCollateralTransactionV2, collateral_title_by_id: dict[str, str]):
    doctor_number = tx.old_doctor_number or tx.doctor_phone_normalized or ""
    collateral_id = tx.old_collateral_id or ""
    rep_display = tx.brand_supplied_field_rep_id or tx.campaign_fieldrep_id or ""
    last_video_percentage = tx.old_last_video_percentage or tx.old_video_watch_percentage or 0
    transaction_id = tx.old_transaction_id or f"{rep_display}-{doctor_number}-{collateral_id}-{tx.old_id or tx.transaction_uuid}"
    return SimpleNamespace(
        transaction_id_display=transaction_id,
        field_rep_display=rep_display,
        doctor_name=tx.old_doctor_name or "",
        doctor_number=doctor_number,
        collateral_id=collateral_id,
        collateral_title=collateral_title_by_id.get(str(collateral_id), "—"),
        has_viewed=bool(tx.old_has_viewed or tx.old_viewed_at or tx.old_first_viewed_at),
        has_downloaded_pdf=bool(tx.old_downloaded_pdf),
        has_viewed_last_page=bool(tx.old_pdf_completed),
        last_video_percentage=last_video_percentage,
        video_watch_percentage=tx.old_video_watch_percentage or 0,
        total_video_events=1 if last_video_percentage else 0,
        transaction_date=tx.old_transaction_date or tx.source_created_at,
        updated_at=tx.old_updated_at or tx.source_updated_at,
    )
