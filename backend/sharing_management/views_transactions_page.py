from __future__ import annotations

from django.db.models import OuterRef, Subquery, F
from django.shortcuts import render

from collateral_management.models import CampaignCollateral as CMCampaignCollateral
from sharing_management.models import CollateralTransaction
from user_management.models import User


def collateral_transactions_dashboard(request, brand_campaign_id: str):
    brand_campaign_id = (str(brand_campaign_id) or "").strip()

    # --- Schema drift safety: inspect model field names at runtime ---
    model_field_names = {f.name for f in CollateralTransaction._meta.get_fields()}

    # Base queryset for this campaign
    qs = CollateralTransaction.objects.filter(brand_campaign_id=brand_campaign_id)

    # Collateral dropdown list (from campaign calendar table)
    collaterals_qs = (
        CMCampaignCollateral.objects
        .filter(campaign__brand_campaign_id=brand_campaign_id)
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
            brand_campaign_id=brand_campaign_id,
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
    # Your model/table (per error page) uses "downloaded_pdf"
    downloaded_field = "downloaded_pdf" if "downloaded_pdf" in model_field_names else None
    downloaded_pdf_doctors = (
        base_rows.filter(**{downloaded_field: True}).values("doctor_number").distinct().count()
        if downloaded_field else 0
    )

    # Viewed last page
    # Prefer pdf_completed if present; else derive from pdf_last_page >= pdf_total_pages
    if "pdf_completed" in model_field_names:
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
    # If field_rep_id happens to match portal User.id, show User.field_id; otherwise fallback.
    rep_ids = []
    for r in rows:
        rid = getattr(r, "field_rep_id", None)
        if isinstance(rid, int):
            rep_ids.append(rid)

    rep_map = {}
    if rep_ids:
        rep_map = {
            u.id: (u.field_id or str(u.id))
            for u in User.objects.filter(id__in=set(rep_ids)).only("id", "field_id")
        }

    for r in rows:
        rid = getattr(r, "field_rep_id", None)

        rep_display = ""
        if isinstance(rid, int) and rid in rep_map:
            rep_display = rep_map[rid]
        else:
            # Prefer email if available; else show master id
            rep_email = getattr(r, "field_rep_email", "") if "field_rep_email" in model_field_names else ""
            rep_display = rep_email or (str(rid) if rid is not None else "")

        r.transaction_id_display = f"{rep_display}-{r.doctor_number}-{r.collateral_id}"
        r.collateral_title = collateral_title_by_id.get(r.collateral_id, "—")

        # Provide template-friendly aliases (won't crash template even if old names were used)
        r.has_downloaded_pdf = bool(getattr(r, downloaded_field, False)) if downloaded_field else False
        if "pdf_completed" in model_field_names:
            r.has_viewed_last_page = bool(getattr(r, "pdf_completed", False))
        elif "pdf_last_page" in model_field_names and "pdf_total_pages" in model_field_names:
            try:
                r.has_viewed_last_page = bool(r.pdf_total_pages and (r.pdf_last_page >= r.pdf_total_pages))
            except Exception:
                r.has_viewed_last_page = False
        else:
            r.has_viewed_last_page = False

    context = {
        "brand_campaign_id": brand_campaign_id,
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
