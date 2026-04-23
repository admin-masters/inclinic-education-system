# Field Rep Sharing and Doctor Bulk Upload

## 1. Title

Field Rep Sharing and Doctor Bulk Upload

## 2. Document Purpose

Document the day-to-day field-rep workflow for choosing doctors, selecting collateral, sharing through WhatsApp, and bulk-uploading doctor rosters.

## 3. Primary User

Field reps and trainers running campaign distribution sessions.

## 4. Entry Point

Campaign-scoped Gmail share route: `/share/fieldrep-gmail-share-collateral/?brand_campaign_id=<brand_campaign_id>` plus `/share/dashboard/doctors/bulk-upload/?campaign=<brand_campaign_id>`.

## 5. Workflow Summary

- The Gmail share page is the campaign-aware workbench for choosing a doctor, choosing collateral, and launching the WhatsApp handoff.
- Doctors can be typed manually on the left-side form or reused from the rep's assigned doctor list on the right.
- Each share creates or reuses a short link and records a ShareLog entry tied to the rep, doctor, collateral, and campaign.
- The public rep screens now include the support chatbot so reps and trainers can jump into help without leaving the workflow.
- Bulk upload helps a rep or operator stage a doctor roster before manual sharing starts.
## 6. Step-By-Step Instructions

### Step 1. Authenticate into the campaign share screen

- What the user does: Use the Gmail login route for the selected campaign and land on the rep share screen.
- What the user sees: A campaign-scoped page with the rep identity, available collateral, doctor-sharing controls, and the floating support chatbot.
- Why the step matters: This is the operational screen reps use most frequently during campaign outreach.
- Expected result: The rep can see only the active collateral that belongs to the current campaign window.
- Common issues / trainer notes: If the list is empty, check the campaign assignment and collateral calendar windows before debugging anything else. If login fails outright, confirm the rep is assigned to the campaign.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/field-rep-sharing-and-doctor-bulk-upload/fieldrep-gmail-share.png`
  Screenshot caption: Campaign share page after a successful Gmail/manual rep login.
  What the screenshot should show: The left-side share form, collateral picker, and help entry point at the top of the current screen.

### Step 2. Select or confirm the doctor context

- What the user does: Choose a doctor from the assigned doctor list or type a doctor name and WhatsApp number manually into the share form.
- What the user sees: Manual input controls on the left and a searchable doctor list on the right, including Sent, Reminder Due, and Opened-style status cues.
- Why the step matters: Doctor identification drives the later verification step, so the number needs to be accurate.
- Expected result: The rep is ready to pair the right doctor with the right collateral.
- Common issues / trainer notes: Emphasize that the same WhatsApp number will be required again by the doctor to unlock the content.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/field-rep-sharing-and-doctor-bulk-upload/fieldrep-doctor-status.png`
  Screenshot caption: Share page section showing the assigned doctor list and send-status controls.
  What the screenshot should show: The searchable doctor roster and status-aware action buttons available during sharing.

### Step 3. Choose collateral and launch the WhatsApp handoff

- What the user does: Select the collateral, submit the share form or doctor-row action, and allow the browser to open the WhatsApp deep link generated for that doctor and campaign.
- What the user sees: A campaign-specific share action that uses the stored message template and short link, then hands the session off to WhatsApp.
- Why the step matters: This is the main product outcome for the field rep: a doctor receives a trackable, campaign-linked message.
- Expected result: A ShareLog is created and the doctor receives a WhatsApp message containing the short link.
- Common issues / trainer notes: During live training, you can stop after the generated message step if opening WhatsApp is not appropriate for the session.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/field-rep-sharing-and-doctor-bulk-upload/fieldrep-gmail-share.png`
  Screenshot caption: Share screen immediately before launching the WhatsApp handoff.
  What the screenshot should show: The campaign-collateral selection and action button used to send the message.

### Step 4. Bulk-upload doctors when onboarding a campaign

- What the user does: Open the Doctor Bulk Upload page, download the sample CSV if needed, and upload a prepared doctor file for the campaign.
- What the user sees: A purpose-built bulk-upload form that explains the expected CSV columns and confirms successful ingestion.
- Why the step matters: Uploading a roster up front makes manual sharing dramatically faster once the campaign goes live.
- Expected result: The rep or operator can stage multiple doctors for the same campaign in one pass.
- Common issues / trainer notes: Use the bulk-upload step before the live sharing demo if you want the doctor list to look realistic without typing every doctor by hand.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/field-rep-sharing-and-doctor-bulk-upload/doctor-bulk-upload.png`
  Screenshot caption: Doctor bulk-upload screen with sample CSV guidance.
  What the screenshot should show: The upload field and the expected column list.

## 7. Success Criteria

- The rep can explain how doctors and collateral are selected on the share page.
- The audience understands why the doctor's exact WhatsApp number matters.
- The bulk-upload option is positioned as a preparation tool, not a separate reporting workflow.

## 8. Related Documents

- `docs/product-user-flows/08-doctor-verification-and-collateral-consumption.md`
- `backend/sharing_management/views.py`
- `backend/sharing_management/templates/sharing_management/fieldrep_gmail_share_collateral.html`

## 9. Status

Validated against the Gmail/manual share flow and doctor bulk-upload page on 2026-04-23.
