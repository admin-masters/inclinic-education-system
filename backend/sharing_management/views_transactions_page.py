from django.contrib.auth.decorators import login_required
from django.db.models import Max, OuterRef, Subquery, F
from django.shortcuts import render
from user_management.models import User
from collateral_management.models import CampaignCollateral as CMCampaignCollateral, Collateral as CMCollateral

from sharing_management.models import CollateralTransaction


@login_required
def collateral_transactions_dashboard(request, brand_campaign_id: str):
    qs = CollateralTransaction.objects.filter(brand_campaign_id=str(brand_campaign_id))
    collaterals_qs = CMCampaignCollateral.objects.filter(
        campaign__brand_campaign_id=str(brand_campaign_id)
    ).select_related("collateral")
    collaterals = [{"id": cc.collateral_id, "title": cc.collateral.title} for cc in collaterals_qs]
    selected_collateral_id = request.GET.get("collateral_id")
    try:
        selected_collateral_id_int = int(selected_collateral_id) if selected_collateral_id else None
    except (ValueError, TypeError):
        selected_collateral_id_int = None
    valid_ids = {c["id"] for c in collaterals}
    if selected_collateral_id_int and selected_collateral_id_int not in valid_ids:
        selected_collateral_id_int = None

    # ---- Summary stats (unique doctors for brand) ----
    total_unique_doctors = qs.values("doctor_number").distinct().count()
    clicked_doctors = qs.filter(has_viewed=True).values("doctor_number").distinct().count()
    downloaded_pdf_doctors = qs.filter(has_downloaded_pdf=True).values("doctor_number").distinct().count()
    viewed_last_page_doctors = qs.filter(has_viewed_last_page=True).values("doctor_number").distinct().count()
    video_lt_50_doctors = qs.filter(video_view_lt_50=True).values("doctor_number").distinct().count()
    video_gt_50_doctors = qs.filter(video_view_gt_50=True).values("doctor_number").distinct().count()
    video_100_doctors = qs.filter(video_view_100=True).values("doctor_number").distinct().count()
    total_transactions = qs.count()

    # ---- Table: most recent row per (doctor_number, collateral_id) ----
    # show the latest state for each doctor+collateral in the brand
    latest_updated = Subquery(
        CollateralTransaction.objects.filter(
            brand_campaign_id=str(brand_campaign_id),
            doctor_number=OuterRef("doctor_number"),
            collateral_id=OuterRef("collateral_id"),
        ).order_by("-updated_at").values("updated_at")[:1]
    )
    annotated = qs.annotate(last_updated=latest_updated)
    base_rows = annotated.filter(updated_at=F("last_updated"))
    if selected_collateral_id_int:
        base_rows = base_rows.filter(collateral_id=selected_collateral_id_int)
    rows = base_rows.order_by("-updated_at")[:1000]

    # Build map for numeric user IDs → field_id
    rep_ids_numeric = []
    for r in rows:
        fid = getattr(r, "field_rep_id", "")
        if isinstance(fid, str) and fid.isdigit():
            rep_ids_numeric.append(int(fid))
    rep_map = {
        u.id: (u.field_id or str(u.id))
        for u in User.objects.filter(id__in=set(rep_ids_numeric)).only("id", "field_id")
    } if rep_ids_numeric else {}

    for r in rows:
        raw_rep = getattr(r, "field_rep_id", "")
        if isinstance(raw_rep, str) and raw_rep.isdigit():
            rep_display = rep_map.get(int(raw_rep), raw_rep)
        else:
            rep_display = raw_rep or ""
        r.transaction_id_display = f"{rep_display}-{r.doctor_number}-{r.collateral_id}"

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
