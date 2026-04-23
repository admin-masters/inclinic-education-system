# Field Rep Sharing and Doctor Bulk Upload

## 1. Title

Field Rep Sharing and Doctor Bulk Upload

## 2. Document Purpose

Document the day-to-day field-rep workflow for choosing doctors, filtering the doctor work queue, sending collateral through WhatsApp, following up with reminders, and bulk-uploading doctor rosters.

## 3. Primary User

Field reps and trainers running campaign distribution sessions.

## 4. Entry Point

Campaign-scoped Gmail share route: `/share/fieldrep-gmail-share-collateral/?brand_campaign_id=<brand_campaign_id>` plus `/share/dashboard/doctors/bulk-upload/?campaign=<brand_campaign_id>`.

## 5. Workflow Summary

- The Gmail share page is the campaign-aware workbench for choosing a doctor, choosing collateral, and launching the WhatsApp handoff.
- The left-side manual form is still a live path for entering a doctor name and WhatsApp number directly, choosing a collateral from the dropdown, and sending with the `Submit` button.
- Doctors can be typed manually on the left-side form or reused from the rep's assigned doctor list on the right, where each row doubles as a quick-send shortcut.
- The right-side doctor statuses are collateral-specific and progress from `Send Message` to `Sent`, then to `Send Reminder` after six days without engagement, and finally to `Opened` once the doctor views the collateral.
- Each quick-send action creates or reuses a short link, upserts the doctor record if needed, writes a ShareLog entry, and opens the WhatsApp deep link for that doctor and collateral.
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

### Step 2. Prepare a manual share from the left-side form

- What the user does: Enter the doctor name, type the doctor's WhatsApp number, choose the collateral from the dropdown, and review the rep ID before clicking `Submit`.
- What the user sees: The full left-side share form with the campaign ID, read-only Field Rep ID, doctor inputs, collateral selector, and the primary `Submit` button.
- Why the step matters: This is the explicit manual-share path when the doctor is not yet in the right-side roster or when the trainer wants to demonstrate the form fields one by one.
- Expected result: The rep is ready to send the selected collateral using the left-hand form without relying on a preloaded doctor row.
- Common issues / trainer notes: Emphasize that the collateral dropdown drives the entire page state. The same selected collateral also determines the right-side doctor statuses and the hidden values in the quick-send forms.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/field-rep-sharing-and-doctor-bulk-upload/fieldrep-send-form.png`
  Screenshot caption: Left-side manual share form showing doctor inputs, collateral dropdown, and the Submit button.
  What the screenshot should show: The explicit manual-send path that pairs a typed doctor with a selected collateral.

### Step 3. Review the doctor queue and filter the worklist

- What the user does: Use the right-side search box, status filter, and the shared collateral selector to find the doctor who needs action for the currently selected collateral.
- What the user sees: A searchable doctor roster with row-level quick-send buttons labeled `Send Message`, `Sent`, `Send Reminder`, or `Opened` depending on the latest share and engagement state.
- Why the step matters: The right panel is the rep's live work queue. It shows who still needs a first send, who was contacted recently, who is ready for a reminder, and who already opened the collateral.
- Expected result: The rep can isolate the correct doctor and understand whether the next action is an initial send, a reminder, or no action at all.
- Common issues / trainer notes: Changing the collateral dropdown refreshes the page so the doctor-row statuses are recalculated for that asset. The right-side filter is a queue-management aid, not a separate data source.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/field-rep-sharing-and-doctor-bulk-upload/fieldrep-doctor-status.png`
  Screenshot caption: Assigned doctor list with search, status filtering, and the live send-state buttons.
  What the screenshot should show: A mixed queue that shows `Send Message`, `Sent`, `Send Reminder`, and `Opened` for the currently selected collateral.

### Step 4. Send the first collateral message with the Submit flow

- What the user does: Complete the left-side doctor form and click `Submit` to send the currently selected collateral to a manually entered doctor.
- What the user sees: A submit action that resolves the doctor phone number, creates or updates the doctor record, creates or reuses the short link and ShareLog entry, and redirects into a WhatsApp deep link for the chosen doctor.
- Why the step matters: This is the primary field-rep outcome: the doctor receives a trackable message that carries the right campaign, collateral, and rep context.
- Expected result: The rep launches WhatsApp with the configured collateral message and the right short link for the selected doctor.
- Common issues / trainer notes: This is the clearest slide for explaining the dropdown-based collateral choice and the `Submit` button. The manual form is also how the system can upsert a brand-new doctor into the rep's list.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/field-rep-sharing-and-doctor-bulk-upload/fieldrep-send-form.png`
  Screenshot caption: Manual share form immediately before the rep submits the first collateral message.
  What the screenshot should show: The doctor details and collateral selection used by the Submit-based share flow.

### Step 5. Use the right-side quick-send buttons and follow-up states

- What the user does: Click a doctor-row `Send Message` button for a first send, then revisit the same queue later to use the `Sent` and `Send Reminder` buttons as follow-up shortcuts.
- What the user sees: A right-side work queue where first-send and follow-up actions reuse the currently selected collateral and launch the same WhatsApp handoff logic as the left form.
- Why the step matters: This is the fastest day-to-day sharing path once the rep's doctor roster is already loaded.
- Expected result: The rep can send, resend, or remind from the doctor list without retyping the doctor details.
- Common issues / trainer notes: The quick-send buttons on the right use the same POST flow as the left form. In the current UI only `Opened` is disabled; `Sent` is still actionable as a resend shortcut, while `Send Reminder` appears once the six-day threshold is reached.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/field-rep-sharing-and-doctor-bulk-upload/fieldrep-send-message.png`
  Screenshot caption: Doctor queue filtered to the first-send state with an active Send Message button.
  What the screenshot should show: The row-level action that launches the quick-send version of the share flow.

### Step 6. Interpret reminder and opened states

- What the user does: Return to the same doctor list after a share and use the row labels to decide whether a doctor needs a resend, a reminder, or no action.
- What the user sees: A reminder-due queue where older unopened shares show `Send Reminder`, recently shared doctors can still show `Sent`, and engaged doctors show a disabled `Opened` button.
- Why the step matters: This is how reps decide whether to resend, remind, or move on without opening a separate report.
- Expected result: The rep can identify reminder-ready doctors quickly and avoid recontacting doctors who already opened the collateral.
- Common issues / trainer notes: Explain the age rule explicitly: the template changes from `Sent` to `Send Reminder` once the latest share is older than six days and there is still no doctor engagement for that collateral.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/field-rep-sharing-and-doctor-bulk-upload/fieldrep-send-reminder.png`
  Screenshot caption: Reminder-due doctor view showing the follow-up state after the first share ages without engagement.
  What the screenshot should show: The `Send Reminder` action and the surrounding `Sent` and `Opened` status cues.

### Step 7. Bulk-upload doctors when onboarding a campaign

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

- The rep can explain how the left-side collateral selector and Submit flow work together on the share page.
- The rep can explain how the doctor search and status filter change the right-side work queue.
- The audience understands the row-button lifecycle from `Send Message` to `Sent`, `Send Reminder`, and `Opened`.
- The audience understands why the doctor's exact WhatsApp number matters.
- The bulk-upload option is positioned as a preparation tool, not a separate reporting workflow.

## 8. Related Documents

- `docs/product-user-flows/08-doctor-verification-and-collateral-consumption.md`
- `backend/sharing_management/views.py`
- `backend/sharing_management/templates/sharing_management/fieldrep_gmail_share_collateral.html`

## 9. Status

Validated against the Gmail/manual share flow and doctor bulk-upload page on 2026-04-23.
