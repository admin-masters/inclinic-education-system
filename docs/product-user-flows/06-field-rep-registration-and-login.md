# Field Rep Registration and Login

## 1. Title

Field Rep Registration and Login

## 2. Document Purpose

Explain the current public field-rep access screens, including the legacy compatibility redirects, the password login page, and the active Gmail/manual or SSO login path.

## 3. Primary User

Field reps and trainers preparing reps for their first campaign login.

## 4. Entry Point

Public routes under `/share/fieldrep-register/`, `/share/fieldrep-create-password/`, `/share/fieldrep-login/`, and `/share/fieldrep-gmail-login/`.

## 5. Workflow Summary

- The legacy registration and create-password routes no longer collect new credentials; they redirect into the Gmail/manual login screen with an informational banner.
- The product still supports both email/password login and Brand Specific Field ID plus Email ID login patterns.
- Signed SSO can also auto-complete the Gmail login flow by trusting the master Field Rep ID inside the URL or JWT payload.
- Campaign context can travel in the query string or session so a rep is taken directly into the correct campaign after login.
- The field-rep background can be campaign-specific when the campaign has a configured background image.
## 6. Step-By-Step Instructions

### Step 1. Open the legacy registration route and observe the redirect

- What the user does: Launch the campaign-scoped registration URL that older launch materials may still reference.
- What the user sees: The Gmail/manual login page with an info banner stating that Field Rep registration is no longer required.
- Why the step matters: This explains the current product behavior when older documentation or bookmarks still point to the registration route.
- Expected result: The rep lands on the active login surface instead of a self-service sign-up form.
- Common issues / trainer notes: Call this out explicitly during training so the audience understands that the route is compatibility-only and not a live onboarding wizard anymore.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/field-rep-registration-and-login/fieldrep-register.png`
  Screenshot caption: Legacy registration URL redirecting into the current Gmail/manual login page.
  What the screenshot should show: The informational banner and redirected login screen shown instead of the old registration form.

### Step 2. Open the legacy create-password route and confirm the new handoff

- What the user does: Launch the create-password URL, optionally carrying the rep email, Field ID, and campaign in the query string.
- What the user sees: The same Gmail/manual login page, usually with the email and Field ID prefilled and the same informational banner.
- Why the step matters: This shows how older password-setup links now preserve context while handing the rep into the supported login path.
- Expected result: The rep can continue with the current login flow without losing the campaign or identifier context.
- Common issues / trainer notes: Use this screen to explain that the product team simplified onboarding: reps are expected to log in, not create a new password from this route.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/field-rep-registration-and-login/fieldrep-create-password.png`
  Screenshot caption: Legacy create-password URL redirecting into the current login page with preserved identifiers.
  What the screenshot should show: The redirected Gmail/manual login form with prefilled rep context.

### Step 3. Review the direct email/password login screen

- What the user does: Open the field-rep login page tied to the active campaign.
- What the user sees: A focused login form that asks for email and password, preserves campaign context, and includes the same support chatbot used on the other public rep pages.
- Why the step matters: This is the most straightforward rep-login method for routine use.
- Expected result: The rep knows where to enter their standard credentials when the campaign requires the password flow.
- Common issues / trainer notes: If the audience asks which login path to use, clarify what the current campaign rollout recommends before moving into the next workflow deck.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/field-rep-registration-and-login/fieldrep-login.png`
  Screenshot caption: Email/password field-rep login page for the selected campaign.
  What the screenshot should show: The direct credential-entry option for field reps.

### Step 4. Use the active Gmail/manual or SSO login path

- What the user does: Open the Gmail login route and either enter the Brand Specific Field ID plus Email ID manually or arrive through a signed SSO link that provides those values automatically.
- What the user sees: A campaign-scoped login form labeled Brand Specific Field ID and Email ID, along with the campaign context and the floating support chatbot.
- Why the step matters: This is the primary live access route into the share experience and the path used by the seeded demo.
- Expected result: The rep reaches the campaign share page with the correct assignment and session context.
- Common issues / trainer notes: Manual login uses the brand-specific Field ID. Automatic SSO trusts the master Field Rep ID from the URL or JWT claims, then completes the same login path.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/field-rep-registration-and-login/fieldrep-gmail-login.png`
  Screenshot caption: Current Gmail/manual login page used for campaign-scoped rep access.
  What the screenshot should show: The Brand Specific Field ID and Email ID fields that lead directly into the share experience.

## 7. Success Criteria

- Trainees understand that registration and create-password routes are now compatibility redirects, not live onboarding forms.
- The difference between email/password, Gmail/manual login, and signed SSO is explained clearly.
- Campaign context in the URL is explained clearly.
- The group is ready to continue into the share workflow with the correct login path.

## 8. Related Documents

- `docs/product-user-flows/07-field-rep-sharing-and-doctor-bulk-upload.md`
- `backend/sharing_management/views.py`
- `backend/sharing_management/templates/sharing_management/fieldrep_gmail_login.html`

## 9. Status

Validated against the current public rep-access screens on 2026-04-23; legacy registration routes now documented as redirects into Gmail/manual login.
