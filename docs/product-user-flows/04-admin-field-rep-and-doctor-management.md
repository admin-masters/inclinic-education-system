# Admin Field Rep and Doctor Management

## 1. Title

Admin Field Rep and Doctor Management

## 2. Document Purpose

Document how staff users maintain master field reps and the doctor lists attached to each rep.

## 3. Primary User

Staff admins and training leads who support rep onboarding and doctor list maintenance.

## 4. Entry Point

Authenticated portal login followed by `/admin_dashboard/fieldreps/` or `/admin_dashboard/fieldreps/?campaign=<brand_campaign_id>`.

## 5. Workflow Summary

- The field-rep list is sourced from the master database and can be filtered by brand campaign.
- Each field rep can be opened into a doctor-management screen backed by the portal doctor table.
- The screen is designed for campaign-scoped administration rather than open-ended browsing.
- Doctor data maintained here becomes reusable context in the field-rep sharing screens.
## 6. Step-By-Step Instructions

### Step 1. Open the field-rep list for a campaign

- What the user does: Navigate to the field-rep list and optionally keep the campaign filter in the URL.
- What the user sees: A table of master field reps with unique ID, field ID, Gmail ID, phone number, campaign mapping, and action buttons.
- Why the step matters: Campaign filtering reduces noise and keeps training focused on the reps that actually matter for a launch.
- Expected result: The admin can see exactly which reps are assigned to the selected campaign.
- Common issues / trainer notes: The list mixes master-table data with a display-friendly campaign mapping string to make the assignment state easy to explain.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/admin-field-rep-and-doctor-management/fieldrep-list.png`
  Screenshot caption: Field-rep administration list filtered to the active campaign.
  What the screenshot should show: Campaign-filtered rep inventory and the doctor management action.

### Step 2. Review or create a field-rep record

- What the user does: Open the add or edit field-rep form, confirm the contact details, and keep the campaign context intact.
- What the user sees: A standard field-rep form that writes back to the master data tables and preserves the campaign filter in the redirect.
- Why the step matters: Rep identity and campaign assignment need to be correct before any field-rep login or sharing flow works.
- Expected result: The rep is active, reachable, and assigned to the right campaign.
- Common issues / trainer notes: In the current implementation, the campaign-aware add button may point to an external field-rep site instead of the local Django form; document whichever environment your training run actually uses.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/admin-field-rep-and-doctor-management/fieldrep-form.png`
  Screenshot caption: Field-rep form used for create or update operations.
  What the screenshot should show: The contact and identifier fields that define the rep record.

### Step 3. Maintain the doctor list for a selected rep

- What the user does: Use the View Doctors action to add, edit, or remove doctors associated with the rep.
- What the user sees: A rep-specific doctor list and a compact add-doctor form on the same page.
- Why the step matters: Doctors created here become reusable share targets in the field-rep experience.
- Expected result: The rep leaves with a clean doctor list that can support fast WhatsApp sharing.
- Common issues / trainer notes: This screen writes to the portal doctor table even though the rep itself lives in the master database.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/admin-field-rep-and-doctor-management/fieldrep-doctors.png`
  Screenshot caption: Doctor maintenance screen for a selected field rep.
  What the screenshot should show: The add-doctor form and existing doctor list tied to the rep.

### Step 4. Validate the rep-to-doctor handoff

- What the user does: Confirm that the rep's identifiers match the field-rep sharing login and that the doctor list looks ready for distribution.
- What the user sees: The rep record and doctor list aligned around a single campaign and rep identity.
- Why the step matters: If the rep cannot log in or the doctor list is wrong, the downstream sharing demo will be frustrating and misleading.
- Expected result: The rep administration workflow is complete and ready to hand off to the field-rep training segment.
- Common issues / trainer notes: This is a good pause point to remind the audience that rep creation is master-data-driven while doctor maintenance is portal-data-driven.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/admin-field-rep-and-doctor-management/fieldrep-doctors.png`
  Screenshot caption: Rep-specific doctor list prepared for the sharing workflow.
  What the screenshot should show: The final state the field rep will rely on during outreach.

## 7. Success Criteria

- Admins can explain where rep data lives versus where doctor data lives.
- Campaign-filtered rep management is demonstrated clearly.
- Doctor lists are ready before the field-rep share workflow begins.

## 8. Related Documents

- `docs/product-user-flows/07-field-rep-sharing-and-doctor-bulk-upload.md`
- `backend/admin_dashboard/views.py`
- `backend/campaign_management/master_models.py`

## 9. Status

Validated against the seeded staff-admin screens on 2026-04-11.
