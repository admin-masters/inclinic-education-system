# Publisher Campaign Onboarding and Update

## 1. Title

Publisher Campaign Onboarding and Update

## 2. Document Purpose

Show how a publisher or partner system opens the portal with a signed campaign link and maintains the editable portal-side campaign fields.

## 3. Primary User

Publisher users, partner-system operators, and trainers supporting SSO onboarding.

## 4. Entry Point

Signed publisher route: `/campaigns/publisher-landing-page/?campaign-id=<uuid>&jwt=<token>`.

## 5. Workflow Summary

- A signed JWT establishes the publisher session without a standard Django login.
- The landing page stores the campaign ID in session and offers the add/edit campaign paths.
- The campaign update page merges read-only master data with locally editable PE fields.
- Successful saves keep the user on the campaign update route so the campaign can be refined iteratively.
## 6. Step-By-Step Instructions

### Step 1. Open the signed publisher landing page

- What the user does: Launch the partner-provided URL that contains the `campaign-id` and publisher JWT.
- What the user sees: A minimal publisher landing page confirming the campaign ID and offering the add-details or select-another-campaign actions.
- Why the step matters: The signed link is what authorizes a publisher without giving them a normal portal user account.
- Expected result: The publisher session is established and the campaign ID is stored in the session.
- Common issues / trainer notes: If the JWT is missing or invalid, the route returns `unauthorised access` instead of falling back to a portal login screen.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/publisher-campaign-onboarding-and-update/publisher-landing.png`
  Screenshot caption: Publisher landing page after a valid signed link is opened.
  What the screenshot should show: Campaign ID confirmation and the branch into the add-details workflow.

### Step 2. Open the campaign update form

- What the user does: Choose the add-details or edit path for the current campaign.
- What the user sees: A campaign form that keeps master-system fields read-only and exposes portal-specific fields such as campaign name, dates, logos, background image, printing requirement, and status.
- Why the step matters: This is the sanctioned place where the PE system adds campaign-specific presentation and timing details without mutating the master record.
- Expected result: The publisher understands which information is reference-only and which is editable locally.
- Common issues / trainer notes: The form includes direct outbound buttons for field-rep management in the external field-rep site, which is a separate integration touchpoint from the local Django routes.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/publisher-campaign-onboarding-and-update/publisher-campaign-update.png`
  Screenshot caption: Publisher-facing campaign update screen showing read-only master fields and editable portal fields.
  What the screenshot should show: The split between immutable master metadata and editable PE-side fields.

### Step 3. Populate the editable campaign fields

- What the user does: Review the campaign dates, description, logos, field-rep login background image, printing settings, and status, then save the changes.
- What the user sees: The standard Django multipart form experience with the campaign values preserved on return.
- Why the step matters: These fields drive the field-rep visual experience, campaign timing, and what downstream users see in the portal.
- Expected result: The portal campaign record is ready for collateral setup and field-rep access.
- Common issues / trainer notes: Because the route saves back to the same campaign update URL, it is normal to treat this page as a working draft screen rather than a one-time wizard.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/publisher-campaign-onboarding-and-update/publisher-campaign-update.png`
  Screenshot caption: Campaign update form used to maintain the PE-side metadata for the selected campaign.
  What the screenshot should show: The editable form controls and save action.

### Step 4. Hand off to downstream campaign operations

- What the user does: After saving, hand the campaign over to the operator or internal team responsible for collaterals and field reps.
- What the user sees: The refreshed campaign update page, which now represents the latest local state for that campaign.
- Why the step matters: Publisher onboarding is the start of the lifecycle, not the end. The downstream team still needs campaign context to assign reps and publish assets.
- Expected result: The campaign is ready for staff-level operations and field-rep activation.
- Common issues / trainer notes: If the publisher enters a campaign that does not yet exist locally, the portal automatically routes them into the create/update path rather than failing.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/publisher-campaign-onboarding-and-update/publisher-campaign-update.png`
  Screenshot caption: Saved campaign update screen that becomes the handoff state for the operations team.
  What the screenshot should show: The persistent campaign record after publisher edits are stored.

## 7. Success Criteria

- The publisher can enter with a signed link and reach the campaign update screen.
- The distinction between master-owned and portal-owned data is clear.
- The saved campaign is ready to be used by the operational team.

## 8. Related Documents

- `docs/product-user-flows/03-internal-campaign-operations-from-the-manage-data-panel.md`
- `backend/campaign_management/views.py`
- `backend/campaign_management/publisher_auth.py`

## 9. Status

Validated against the signed publisher demo route on 2026-04-11.
