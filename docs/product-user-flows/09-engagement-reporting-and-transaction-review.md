# Engagement Reporting and Transaction Review

## 1. Title

Engagement Reporting and Transaction Review

## 2. Document Purpose

Show how campaign stakeholders review the doctor engagement outcomes created by sharing and doctor consumption.

## 3. Primary User

Campaign analysts, operations leads, and trainers closing the loop after a doctor demo.

## 4. Entry Point

`/reports/collateral-transactions/<brand_campaign_id>/`.

## 5. Workflow Summary

- The transaction dashboard aggregates the latest state per doctor, collateral, and field rep for the selected campaign.
- The collateral filter narrows the view when stakeholders want to discuss one asset at a time.
- Summary counters surface clicked doctors, downloaded PDFs, viewed-last-page counts, and video watch buckets.
- The doctor table is the operational follow-up surface for identifying which doctors engaged and how far they got.
## 6. Step-By-Step Instructions

### Step 1. Open the campaign transaction dashboard

- What the user does: Navigate directly to the report URL for the campaign.
- What the user sees: A branded reporting page with a campaign selector, collateral filter, summary section, and doctor table.
- Why the step matters: This is the clearest operational view of whether the campaign is generating meaningful doctor interaction.
- Expected result: Stakeholders can immediately orient to the campaign and available collateral.
- Common issues / trainer notes: The dashboard is latest-state oriented, which is useful for follow-up but different from a raw event log.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/engagement-reporting-and-transaction-review/report-dashboard.png`
  Screenshot caption: Campaign transaction dashboard with summary metrics and doctor rows.
  What the screenshot should show: The top summary section and the campaign/collateral filters.

### Step 2. Filter to a specific collateral when needed

- What the user does: Choose a collateral from the drop-down and refresh the page context.
- What the user sees: The same dashboard narrowed to a single collateral's doctor outcomes.
- Why the step matters: Filtering keeps the conversation concrete when the campaign has more than one asset.
- Expected result: The summary metrics and doctor rows now reflect the selected collateral only.
- Common issues / trainer notes: This is a strong way to compare flagship collateral against supporting leaflets during a training review.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/engagement-reporting-and-transaction-review/report-filtered.png`
  Screenshot caption: Transaction dashboard filtered to a specific collateral.
  What the screenshot should show: The same report with the collateral scope narrowed for discussion.

### Step 3. Read doctor-level engagement status

- What the user does: Scroll into the doctor rows and inspect who clicked, viewed, downloaded, or reached later video buckets.
- What the user sees: A doctor table that combines rep identity, doctor number, collateral title, and engagement state.
- Why the step matters: This is the bridge from aggregate counts to real operational follow-up.
- Expected result: The team can identify which doctors need another touchpoint or a different content approach.
- Common issues / trainer notes: Use the report right after the doctor-viewer demo so the audience recognizes how those actions appear operationally.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/engagement-reporting-and-transaction-review/report-dashboard.png`
  Screenshot caption: Doctor-level table used for campaign follow-up discussions.
  What the screenshot should show: The detailed rows that support rep and campaign follow-up.

### Step 4. Export and reuse the report output

- What the user does: Use the CSV download option and hand the resulting data to downstream reporting or follow-up teams.
- What the user sees: A report page designed for operational review and export, not just on-screen viewing.
- Why the step matters: Campaign reporting often continues outside the portal in spreadsheets or BI workflows.
- Expected result: The transaction view can feed a follow-up or analytics process without manual rewriting.
- Common issues / trainer notes: Even if the deck demo does not actually export a CSV live, call out the button so users know the path exists.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/engagement-reporting-and-transaction-review/report-dashboard.png`
  Screenshot caption: Report page showing the export-oriented controls.
  What the screenshot should show: The controls that let stakeholders take the data beyond the portal screen.

## 7. Success Criteria

- Stakeholders can connect doctor actions back to what they saw in the field-rep and doctor decks.
- The audience understands the difference between top-line counts and doctor-level rows.
- The export path is documented clearly enough for follow-up teams.

## 8. Related Documents

- `docs/product-user-flows/08-doctor-verification-and-collateral-consumption.md`
- `backend/sharing_management/views_transactions_page.py`
- `backend/sharing_management/services/transactions.py`

## 9. Status

Validated against the seeded transaction dashboard on 2026-04-11.
