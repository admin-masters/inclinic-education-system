# Field Rep Login

## 1. Title

Field Rep Login

## 2. Document Purpose

Explain the live public Field Rep login screen and how campaign-scoped reps sign in with Email ID and Field Rep ID.

## 3. Primary User

Field reps and trainers preparing reps for their first campaign login.

## 4. Entry Point

Campaign-scoped Field Rep login route: `/share/fieldrep-gmail-login/?campaign=<brand_campaign_id>`.

## 5. Workflow Summary

- Field reps are registered through the campaign manager or staff-admin workflow before they ever reach the public login page.
- Public training now focuses on one live login pattern: Email ID plus Brand Specific Field ID.
- Campaign context can travel in the query string or session so a rep is taken directly into the correct campaign after login.
- Successful login takes the rep straight into the campaign share page used in workflow 07.
- The field-rep background can be campaign-specific when the campaign has a configured background image.
## 6. Step-By-Step Instructions

### Step 1. Open the campaign-scoped Field Rep login page

- What the user does: Launch the public Field Rep login URL for the selected campaign.
- What the user sees: A campaign-scoped login form labeled Brand Specific Field ID and Email ID, along with the campaign context and the floating support chatbot.
- Why the step matters: This is the live entry point field reps use after they have already been registered in the campaign manager workflow.
- Expected result: The rep reaches the correct login surface for the campaign they need to work on.
- Common issues / trainer notes: Set the expectation clearly: this page is for login only. Registration and rep setup happen earlier in the admin workflow covered in workflow 04.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/field-rep-registration-and-login/fieldrep-gmail-login.png`
  Screenshot caption: Current Field Rep login page used for campaign-scoped rep access.
  What the screenshot should show: The Email ID and Brand Specific Field ID fields that lead into the share experience.

### Step 2. Sign in with Email ID and Field Rep ID

- What the user does: Enter the Email ID and Brand Specific Field ID exactly as assigned for the campaign, then submit the form.
- What the user sees: The same login card until submission succeeds, after which the rep is redirected into the campaign share screen with the selected campaign already in context.
- Why the step matters: These two identifiers are the only public-login fields the rep needs for the live workflow.
- Expected result: The rep lands on the share page and is ready to start sending collateral.
- Common issues / trainer notes: If login fails, confirm that the rep record exists in the campaign manager dashboard and that the Email ID plus Field Rep ID pair belongs to the same campaign assignment.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/field-rep-registration-and-login/fieldrep-gmail-login.png`
  Screenshot caption: Field Rep login page showing the two identifiers required for campaign access.
  What the screenshot should show: The credential fields and submit action used before the rep is redirected into sharing.

## 7. Success Criteria

- Trainees understand that registration happens in the campaign manager or staff-admin workflow, not on the public rep page.
- The live public login uses only Email ID and Brand Specific Field ID.
- Campaign context in the URL is explained clearly.
- The group is ready to continue into the share workflow with the correct login path.

## 8. Related Documents

- `docs/product-user-flows/04-admin-field-rep-and-doctor-management.md`
- `docs/product-user-flows/07-field-rep-sharing-and-doctor-bulk-upload.md`
- `backend/sharing_management/views.py`
- `backend/sharing_management/templates/sharing_management/fieldrep_gmail_login.html`

## 9. Status

Validated against the current public Field Rep login screen on 2026-04-23; registration is documented in the admin workflow instead of the public rep deck.
