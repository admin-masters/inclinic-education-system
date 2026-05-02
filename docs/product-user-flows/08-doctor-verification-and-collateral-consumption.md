# Doctor Verification and Collateral Consumption

## 1. Title

Doctor Verification and Collateral Consumption

## 2. Document Purpose

Show the doctor journey from WhatsApp short-link click through verification, viewer access, and archive/webinar exploration.

## 3. Primary User

Doctors, trainers demonstrating the doctor experience, and support teams validating the public flow.

## 4. Entry Point

Public short-link path `/shortlinks/go/<code>/` which redirects into `/view/collateral/verify/`.

## 5. Workflow Summary

- Short links resolve to a doctor verification screen rather than directly exposing the collateral.
- Verification is based on the last 10 digits of the WhatsApp number originally used in the share log.
- A successful verify step grants access, creates or reuses the doctor engagement context, and renders the PDF/video viewer.
- The viewer can show banners, embedded video, downloadable PDF content, archive links, webinar links, and the support chatbot.
- The PDF viewer now auto-loads with device-aware behavior: most devices use an in-page scroll box, while iOS devices switch to inline lazy rendering.
## 6. Step-By-Step Instructions

### Step 1. Open the short link and reach the verification page

- What the user does: Tap the short link from the WhatsApp message.
- What the user sees: A public Verify Access screen that asks for the WhatsApp number used during sharing and includes the floating support chatbot.
- Why the step matters: This prevents the collateral from behaving like an unguarded public file link.
- Expected result: The doctor is ready to prove they are the intended recipient.
- Common issues / trainer notes: Support teams should always ask for the exact shared number when helping a doctor who cannot unlock content.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/doctor-verification-and-collateral-consumption/doctor-verify.png`
  Screenshot caption: Public doctor verify page reached from the short link.
  What the screenshot should show: The number-entry step required before content is unlocked.

### Step 2. Verify with the same WhatsApp number used during sharing

- What the user does: Enter the matching 10-digit number and submit the form.
- What the user sees: A successful handoff into the doctor viewer instead of an access-denied message, with the unlocked collateral title and content area visible immediately.
- Why the step matters: The matching logic is what binds the public doctor experience back to a specific share log and grants download access for that short link.
- Expected result: The doctor gains access to the content and engagement tracking starts.
- Common issues / trainer notes: If verification fails, double-check number formatting and whether the rep used a different phone number during sharing.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/doctor-verification-and-collateral-consumption/doctor-viewer.png`
  Screenshot caption: Verified doctor viewer shown immediately after a successful unlock.
  What the screenshot should show: The content area that appears once verification succeeds.

### Step 3. Consume the PDF, banners, and video content

- What the user does: Scroll the PDF, watch the embedded video, or download the PDF copy.
- What the user sees: A branded viewer with banners, embedded Vimeo player, download button, and an auto-loading PDF area that adapts to the device type.
- Why the step matters: This is the content experience the field rep promised to the doctor and the source of the later engagement metrics.
- Expected result: Doctor engagement events can be captured and reflected in downstream reporting.
- Common issues / trainer notes: The PDF area is intentionally large and scrollable because the product treats scroll depth as a meaningful engagement signal. On iPhone and iPad, the viewer switches to inline lazy rendering rather than a nested scroll box.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/doctor-verification-and-collateral-consumption/doctor-viewer.png`
  Screenshot caption: Doctor viewer showing banners, PDF download, and the embedded collateral content.
  What the screenshot should show: The content-consumption experience after verification.

### Step 4. Use the archive and webinar options when present

- What the user does: Open older collateral from the archive cards or launch the webinar link.
- What the user sees: Additional campaign content options such as archive cards or a webinar panel below the primary collateral.
- Why the step matters: The product can extend beyond a single PDF or video and act as a campaign micro-journey for the doctor.
- Expected result: The doctor can discover related material without needing a separate share from the rep.
- Common issues / trainer notes: Archive and webinar blocks are collateral-dependent, so explain that they appear only when the asset was configured with those extras.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/doctor-verification-and-collateral-consumption/doctor-viewer-archive.png`
  Screenshot caption: Doctor viewer lower section showing optional follow-on content below the main collateral.
  What the screenshot should show: The webinar panel and any archive follow-ons available to the doctor after unlock.

## 7. Success Criteria

- The audience can explain why the doctor must use the same WhatsApp number.
- The doctor viewer's main content areas are easy to identify.
- Archive and webinar options are understood as optional extensions of the core flow.

## 8. Related Documents

- `docs/product-user-flows/07-field-rep-sharing-and-doctor-bulk-upload.md`
- `docs/product-user-flows/09-engagement-reporting-and-transaction-review.md`
- `backend/doctor_viewer/views.py`

## 9. Status

Validated against the seeded public doctor flow on 2026-04-23, including the current support widget and device-aware PDF viewer behavior.
