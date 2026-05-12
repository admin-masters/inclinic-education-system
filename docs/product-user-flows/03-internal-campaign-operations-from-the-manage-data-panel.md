# Internal Campaign Operations from the Manage Data Panel

## 1. Title

Internal Campaign Operations from the Manage Data Panel

## 2. Document Purpose

Teach internal operators how to search campaign inventory, open individual campaigns, and branch into the linked operational tools.

## 3. Primary User

Internal campaign operators and trainers onboarding operational staff.

## 4. Entry Point

Authenticated portal login followed by `/campaigns/manage-data/`.

## 5. Workflow Summary

- The Manage Data Panel pulls campaign reference data from the master database and merges it with any local portal campaign rows.
- Operators can search by brand campaign ID, brand name, or company name.
- Every campaign row provides direct shortcuts into view, edit, collateral, and field-rep operations.
- This screen is the fastest route for orienting to a campaign before switching into a role-specific workflow.
## 6. Step-By-Step Instructions

### Step 1. Log in and open the Manage Data Panel

- What the user does: Sign in to the portal and navigate to the Manage Data Panel.
- What the user sees: A searchable campaign table with brand campaign IDs, brand names, company names, dates, and row buttons labeled `View`, `Edit`, `Collateral`, and `Field Reps`.
- Why the step matters: This is the operational inventory of campaigns that can be maintained in the portal right now.
- Expected result: The operator can quickly locate the campaign that needs work.
- Common issues / trainer notes: The live-search field debounces and refreshes the URL query string automatically. Blank start or end dates usually mean the portal-side campaign row is not fully configured yet.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/internal-campaign-operations-from-the-manage-data-panel/manage-data-panel.png`
  Screenshot caption: Manage Data Panel with campaign inventory and action buttons.
  What the screenshot should show: The search field and per-row action shortcuts.

### Step 2. Filter and inspect a specific campaign

- What the user does: Use the live search field and open the selected campaign's view or edit route.
- What the user sees: A campaign detail or campaign update page where the operator can confirm the local description, dates, status, and other portal-side metadata for the selected brand campaign.
- Why the step matters: Operators rarely work on every campaign at once; the panel is meant to narrow attention to a single campaign quickly.
- Expected result: The campaign row that matters is isolated and ready for action.
- Common issues / trainer notes: Use `View` when you only need a quick read of the campaign, and `Edit` when you need to change the PE-side metadata or inspect the master read-only fields in more depth.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/internal-campaign-operations-from-the-manage-data-panel/campaign-detail.png`
  Screenshot caption: Campaign detail page reached from the Manage Data Panel.
  What the screenshot should show: The campaign-specific detail context after selecting a row.

### Step 3. Branch into the next operational tool

- What the user does: Choose the shortcut for collateral management or field-rep management from the same row.
- What the user sees: A new tab that opens either the collateral dashboard or the field-rep administration list with the same brand campaign ID already carried into the next screen.
- Why the step matters: The Manage Data Panel is meant to hand campaign context forward instead of forcing users to re-enter campaign IDs elsewhere.
- Expected result: The next workflow opens already focused on the same brand campaign.
- Common issues / trainer notes: This is where trainers should explain the brand campaign ID as the shared handoff key across the product. The `Collateral` button opens the rep-facing collateral dashboard, and `Field Reps` opens the staff rep list.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/internal-campaign-operations-from-the-manage-data-panel/manage-data-panel.png`
  Screenshot caption: Campaign row with shortcut buttons for downstream operations.
  What the screenshot should show: The direct handoff from campaign inventory into field-rep and collateral routes.

### Step 4. Confirm downstream readiness

- What the user does: Check that the campaign has the expected dates, status, and accessible collateral or rep routes.
- What the user sees: A consistent campaign context across the linked screens.
- Why the step matters: A small mismatch at this stage can ripple into the sharing and doctor experience later.
- Expected result: The operator knows the campaign is ready for rep and collateral workflows.
- Common issues / trainer notes: The codebase currently links some operator buttons into routes that are role-gated differently, so it is worth validating the user account used for training ahead of time.
- Screenshot placeholder:
  Suggested file path: `docs/product-user-flows/assets/internal-campaign-operations-from-the-manage-data-panel/manage-data-panel.png`
  Screenshot caption: Campaign inventory used as the launching point for all downstream work.
  What the screenshot should show: Campaign readiness before switching to the next role deck.

## 7. Success Criteria

- Operators can locate a campaign quickly from the campaign inventory.
- The purpose of each row-level shortcut is understood.
- The campaign is verified before the trainer moves into collateral or field-rep decks.

## 8. Related Documents

- `docs/product-user-flows/04-admin-field-rep-and-doctor-management.md`
- `docs/product-user-flows/05-collateral-authoring-and-message-setup.md`
- `backend/campaign_management/views.py`

## 9. Status

Validated against the seeded Manage Data Panel on 2026-04-23.
