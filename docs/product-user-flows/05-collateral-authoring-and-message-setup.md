# Collateral Authoring and Message Setup

## 1. Title

Collateral Authoring and Message Setup

## 2. Document Purpose

Show how campaign assets, collateral schedules, and WhatsApp messages are configured before field reps start sharing.

## 3. Primary User

Campaign operators and training leads preparing the collateral side of a launch.

## 4. Entry Point

Campaign-scoped collateral panel: `/share/dashboard/?campaign=<brand_campaign_id>` plus `/collaterals/add/<brand_campaign_id>/` and `/collaterals/collateral-messages/`.

## 5. Workflow Summary

- The collateral dashboard is the campaign-scoped control panel for asset inventory, calendar edits, and rep-facing shortcuts.
- Add Collateral combines campaign selection, asset upload, banner configuration, webinar metadata, and a default WhatsApp message path.
- Collateral Messages Management stores custom message text per campaign-collateral pair.
- Calendar windows determine when a collateral is considered available in the share screens.
## 6. Step-By-Step Instructions

### Step 1. Open the campaign collateral dashboard

- What the user does: Navigate to the campaign's collateral panel from the campaign inventory or directly through the filtered route.
- What the user sees: A campaign-scoped dashboard with buttons for Add Collaterals, Edit Calendar, Doctor Bulk Upload, and the field-rep entry links.
- Why the step matters: This dashboard is the operator's launch pad for collateral and rep-facing setup.
- Expected result: The operator sees the current collateral inventory and the next setup actions in one place.
- Common issues / trainer notes: This route is campaign-aware and surfaces the same brand campaign ID used elsewhere in the product.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/collateral-authoring-and-message-setup/collateral-dashboard.png`
  Screenshot caption: Campaign collateral dashboard with collateral inventory and setup shortcuts.
  What the screenshot should show: The operator-facing control panel for campaign assets.

### Step 2. Create or update a collateral asset

- What the user does: Open the Add Collateral form, upload the PDF and banners, choose the type, and add descriptive or webinar metadata.
- What the user sees: A large multipart form for purpose, content title, content ID, collateral type, PDF or Vimeo input, banners, doctor display name, and webinar details.
- Why the step matters: This screen defines what the doctor ultimately sees after verification.
- Expected result: The campaign has a polished collateral record that can be linked and shared.
- Common issues / trainer notes: The form automatically creates a message row when a collateral is saved, which is why the message-management screen is part of the same training segment.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/collateral-authoring-and-message-setup/add-collateral-form.png`
  Screenshot caption: Collateral input form used to create campaign-ready doctor content.
  What the screenshot should show: The PDF upload, metadata, and banner sections of the form.

### Step 3. Review or customize the WhatsApp message

- What the user does: Open the Collateral Messages Management page and inspect the message linked to the collateral and campaign pair.
- What the user sees: A searchable message list with campaign ID, collateral, message preview, status, and actions.
- Why the step matters: The share experience depends on good rep-facing message text that includes the `$collateralLinks` placeholder.
- Expected result: The active message is appropriate for the campaign and collateral being launched.
- Common issues / trainer notes: Use this step to remind trainees that the message text is not global; it is scoped to a specific campaign and collateral.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/collateral-authoring-and-message-setup/collateral-messages.png`
  Screenshot caption: Message-management page showing the campaign-to-collateral WhatsApp text setup.
  What the screenshot should show: The message preview list and campaign/collateral filtering controls.

### Step 4. Adjust the collateral calendar window

- What the user does: Open the Edit Calendar screen and confirm the start and end dates for the campaign-collateral mapping.
- What the user sees: A calendar-edit screen that controls whether a collateral is active in the share flow on the current date.
- Why the step matters: Availability windows are one of the key reasons a collateral might not appear for a field rep even when the asset exists.
- Expected result: Only the intended collateral is active during the campaign window.
- Common issues / trainer notes: This is one of the first places to inspect if a field rep says a collateral is missing from the share page.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/collateral-authoring-and-message-setup/edit-calendar.png`
  Screenshot caption: Calendar management screen used to control collateral availability windows.
  What the screenshot should show: The date controls that determine whether a collateral appears in the share flow.

## 7. Success Criteria

- Operators can create or review a collateral tied to the campaign.
- Message text and collateral availability windows are understood as part of the launch workflow.
- The field-rep-facing collateral inventory is ready before rep training starts.

## 8. Related Documents

- `docs/product-user-flows/07-field-rep-sharing-and-doctor-bulk-upload.md`
- `backend/collateral_management/views.py`
- `backend/collateral_management/views_collateral_message.py`

## 9. Status

Validated against the seeded collateral dashboard and forms on 2026-04-11.
