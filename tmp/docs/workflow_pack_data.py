from __future__ import annotations


GENERATED_ON = "2026-04-23"
SOURCE_MANUAL_DIR = "docs/product-user-flows"
ASSET_ROOT = "docs/product-user-flows/assets"
DECK_OUTPUT_DIR = "output/doc/user-flow-decks"

ROLE_MAP = [
    {
        "role": "Publisher / partner system",
        "goal": "Open a campaign in the portal and maintain the editable PE-side campaign fields.",
        "starts_at": "/campaigns/publisher-landing-page/?campaign-id=<uuid>&jwt=<token>",
        "hands_off_to": "Campaign operations users and field-rep setup.",
    },
    {
        "role": "Internal campaign operator",
        "goal": "Search campaign inventory, open campaign records, and branch into collateral or field-rep operations.",
        "starts_at": "/campaigns/manage-data/",
        "hands_off_to": "Collateral operations and field-rep administration.",
    },
    {
        "role": "Staff admin",
        "goal": "Maintain master field reps and the doctor lists attached to each rep.",
        "starts_at": "/admin_dashboard/fieldreps/",
        "hands_off_to": "Field reps who will actually share the content.",
    },
    {
        "role": "Field rep",
        "goal": "Authenticate, pick the right campaign collateral, and share it with doctors through WhatsApp.",
        "starts_at": "/share/fieldrep-gmail-login/ (legacy register/create-password routes redirect here)",
        "hands_off_to": "Doctors who receive the short link.",
    },
    {
        "role": "Doctor",
        "goal": "Verify access with the same WhatsApp number and consume the PDF/video collateral.",
        "starts_at": "/shortlinks/go/<code>/",
        "hands_off_to": "Reporting and follow-up users.",
    },
    {
        "role": "Reporting stakeholder",
        "goal": "Review transaction rollups and doctor-level engagement for a campaign.",
        "starts_at": "/reports/collateral-transactions/<brand_campaign_id>/",
        "hands_off_to": "Campaign optimization and rep follow-up.",
    },
]

WORKFLOW_GROUPS = [
    ("Platform Overview", [1]),
    ("Publisher and Campaign Operations", [2, 3, 5]),
    ("Admin Operations", [4]),
    ("Field Rep Journeys", [6, 7]),
    ("Doctor and Reporting", [8, 9]),
]

INVENTORY_DEPRECATED = [
    "Legacy field-rep self-registration and create-password routes still exist in the route map, but they now redirect to the Gmail/manual login page and are documented as compatibility entry points inside workflow 06.",
]

INVENTORY_MISSING = []

WORKFLOWS = [
    {
        "order": 1,
        "slug": "platform-overview-and-role-map",
        "title": "Platform Overview and Role Map",
        "deck_group": "Platform Overview",
        "inventory_status": "✅ up-to-date",
        "inventory_note": "Refreshed the cross-role handoff to match the current Gmail-first field-rep login and share experience.",
        "document_purpose": "Explain how campaign master data, portal operations, field-rep sharing, doctor verification, and reporting connect end to end.",
        "primary_user": "New team members, trainers, implementation partners, and AI agents orienting to the product.",
        "entry_point": "Role-dependent. The seeded demo uses `/campaigns/manage-data/`, `/campaigns/publisher-landing-page/`, `/share/fieldrep-gmail-login/`, and `/shortlinks/go/<code>/` as the main route families.",
        "workflow_summary": [
            "Campaign definitions originate in the master database and are surfaced in the portal through the Manage Data Panel and publisher landing pages.",
            "Editable campaign metadata, collateral assets, share logs, and transaction rollups live in the portal database.",
            "Field reps now reach the campaign share flow primarily through the Gmail/manual login or signed SSO entry point; legacy register and create-password URLs redirect into that path.",
            "Doctors unlock collateral with the same WhatsApp number used during sharing, then consume PDF/video content in a viewer that also surfaces archive and webinar follow-ons.",
            "Reporting screens summarize the latest engagement state per doctor, per collateral, per campaign.",
        ],
        "extra_markdown": """### Role Map

| Role | Core screens | Output to the next role |
| --- | --- | --- |
| Publisher / partner system | Publisher landing page, campaign update form | Brand-campaign context plus editable campaign metadata |
| Internal campaign operator | Manage Data Panel, campaign detail/update | Access to field-rep and collateral operations |
| Staff admin | Field rep list, doctor maintenance | Campaign-assigned reps and doctor rosters |
| Field rep | Gmail/manual login, share collateral page, doctor bulk upload | WhatsApp messages containing short links |
| Doctor | Verify access page, collateral viewer, support chatbot | Engagement records, archive opens, webinar opens |
| Reporting stakeholder | Collateral transactions dashboard | Operational follow-up and campaign insight |

### Role Flow Diagram

```mermaid
flowchart LR
    P["Publisher"] --> C["Campaign record in portal"]
    C --> O["Campaign operator"]
    O --> A["Staff admin"]
    A --> F["Field rep"]
    F --> D["Doctor"]
    D --> R["Reporting dashboard"]
    R --> O
```

### Where Each Workflow Starts

| Workflow | Typical starter |
| --- | --- |
| Publisher campaign onboarding | Signed publisher link with `campaign-id` and JWT |
| Campaign operations | Authenticated portal login -> Manage Data Panel |
| Field rep administration | Authenticated portal login -> Field Rep list |
| Collateral authoring | Campaign shortcut into the collateral dashboard |
| Field rep sharing | Campaign-scoped Gmail/manual login or signed SSO route |
| Doctor consumption | Public short link from WhatsApp |
| Reporting review | Campaign report URL with `brand_campaign_id` |

> Legacy note: `/share/fieldrep-register/` and `/share/fieldrep-create-password/` remain available only as compatibility redirects into the Gmail/manual login screen.
""",
        "steps": [
            {
                "number": 1,
                "title": "Identify the role-specific entry point",
                "user_does": "Start from the route that matches the role: publisher link, authenticated Manage Data Panel, field-rep login page, or public short link.",
                "user_sees": "A role-appropriate screen with the campaign context already embedded or selected.",
                "why_it_matters": "The system is intentionally route-driven. The entry point determines which database data is consulted and which actions are available next.",
                "expected_result": "The user lands on the correct role surface without manually stitching together URLs.",
                "trainer_notes": "Call out that the codebase has separate routes for publisher, staff, field-rep, and doctor experiences rather than a single unified shell.",
                "screenshot_file": "platform-home.png",
                "screenshot_caption": "Public home page used before an authenticated or signed route is chosen.",
                "screenshot_focus": "The simple unauthenticated landing page that redirects authenticated users into campaign operations.",
            },
            {
                "number": 2,
                "title": "Move campaign context from master data into portal operations",
                "user_does": "Open the Manage Data Panel or the publisher flow for a specific brand campaign.",
                "user_sees": "A campaign inventory or campaign form populated with master-owned context such as brand name, company name, and doctor count.",
                "why_it_matters": "This is the handoff from source-of-truth campaign definitions into the operational portal where the team can manage assets and distribution.",
                "expected_result": "The campaign is recognizable and ready for collateral, rep, and doctor operations.",
                "trainer_notes": "Master values are shown read-only in the campaign update flow; only PE-side fields are meant to be edited locally.",
                "screenshot_file": "platform-manage-data.png",
                "screenshot_caption": "Manage Data Panel with campaign shortcuts into field-rep and collateral operations.",
                "screenshot_focus": "The main operational hub that ties campaigns to downstream workflows.",
            },
            {
                "number": 3,
                "title": "Distribute collateral through campaign-assigned field reps",
                "user_does": "Assign or confirm field reps, then let a field rep authenticate into the Gmail/manual share flow or signed SSO entry point and send a doctor-facing WhatsApp message.",
                "user_sees": "Campaign-specific collateral options, doctor lists, send/reminder statuses, and the floating support chatbot on the field-rep pages.",
                "why_it_matters": "This is the commercial and educational delivery loop the platform is built to support.",
                "expected_result": "A doctor receives a short link tied back to the right collateral, campaign, and rep.",
                "trainer_notes": "The operator-facing campaign screens and the field-rep share screens live in different route families but reference the same campaign ID. Legacy register/create-password links now resolve into this same handoff.",
                "screenshot_file": "platform-share-handoff.png",
                "screenshot_caption": "Field-rep share page showing the current campaign form, doctor list, and support chatbot entry point.",
                "screenshot_focus": "The moment where campaign operations become doctor outreach in the current Gmail-first flow.",
            },
            {
                "number": 4,
                "title": "Close the loop with doctor verification and reporting",
                "user_does": "Follow the doctor from short-link click to verification, then open the transaction dashboard for the same campaign.",
                "user_sees": "The doctor unlock screen, the collateral viewer with PDF/archive/webinar content and support chatbot, and a reporting dashboard summarizing doctor-level outcomes.",
                "why_it_matters": "The product is not just a file host; it exists to connect campaign setup to verifiable doctor engagement.",
                "expected_result": "Doctor actions are visible again in reporting and can drive follow-up conversations.",
                "trainer_notes": "Point out that the transaction dashboard shows the latest state per doctor and collateral rather than every raw event row.",
                "screenshot_file": "platform-reporting-loop.png",
                "screenshot_caption": "Reporting dashboard that reflects the downstream result of shares and doctor engagement.",
                "screenshot_focus": "The closed feedback loop from campaign setup to doctor behavior.",
            },
        ],
        "success_criteria": [
            "A new user can explain which role owns which screen family.",
            "The relationship between master data, portal edits, sharing, verification, and reporting is clear.",
            "The team knows where to start each downstream workflow without guessing routes.",
        ],
        "related_documents": [
            "README.md",
            "docs/product-user-flows/02-publisher-campaign-onboarding-and-update.md",
            "docs/product-user-flows/07-field-rep-sharing-and-doctor-bulk-upload.md",
            "docs/product-user-flows/09-engagement-reporting-and-transaction-review.md",
        ],
        "status": f"Validated against the seeded docs demo and the current Django route map on {GENERATED_ON}.",
        "tips": [
            "Treat the campaign UUID as the product's cross-role handoff key.",
            "Use the platform overview deck first during training so later role decks make sense faster.",
        ],
    },
    {
        "order": 2,
        "slug": "publisher-campaign-onboarding-and-update",
        "title": "Publisher Campaign Onboarding and Update",
        "deck_group": "Publisher and Campaign Operations",
        "document_purpose": "Show how a publisher or partner system opens the portal with a signed campaign link and maintains the editable portal-side campaign fields.",
        "primary_user": "Publisher users, partner-system operators, and trainers supporting SSO onboarding.",
        "entry_point": "Signed publisher route: `/campaigns/publisher-landing-page/?campaign-id=<uuid>&jwt=<token>`.",
        "workflow_summary": [
            "A signed JWT establishes the publisher session without a standard Django login.",
            "The landing page stores the campaign ID in session and offers the add/edit campaign paths.",
            "The campaign update page merges read-only master data with locally editable PE fields.",
            "Successful saves keep the user on the campaign update route so the campaign can be refined iteratively.",
        ],
        "steps": [
            {
                "number": 1,
                "title": "Open the signed publisher landing page",
                "user_does": "Launch the partner-provided URL that contains the `campaign-id` and publisher JWT.",
                "user_sees": "A minimal publisher landing page confirming the campaign ID and offering the add-details or select-another-campaign actions.",
                "why_it_matters": "The signed link is what authorizes a publisher without giving them a normal portal user account.",
                "expected_result": "The publisher session is established and the campaign ID is stored in the session.",
                "trainer_notes": "If the JWT is missing or invalid, the route returns `unauthorised access` instead of falling back to a portal login screen.",
                "screenshot_file": "publisher-landing.png",
                "screenshot_caption": "Publisher landing page after a valid signed link is opened.",
                "screenshot_focus": "Campaign ID confirmation and the branch into the add-details workflow.",
            },
            {
                "number": 2,
                "title": "Open the campaign update form",
                "user_does": "Choose the add-details or edit path for the current campaign.",
                "user_sees": "A campaign form that keeps master-system fields read-only and exposes portal-specific fields such as campaign name, dates, logos, background image, printing requirement, and status.",
                "why_it_matters": "This is the sanctioned place where the PE system adds campaign-specific presentation and timing details without mutating the master record.",
                "expected_result": "The publisher understands which information is reference-only and which is editable locally.",
                "trainer_notes": "The form includes direct outbound buttons for field-rep management in the external field-rep site, which is a separate integration touchpoint from the local Django routes.",
                "screenshot_file": "publisher-campaign-update.png",
                "screenshot_caption": "Publisher-facing campaign update screen showing read-only master fields and editable portal fields.",
                "screenshot_focus": "The split between immutable master metadata and editable PE-side fields.",
            },
            {
                "number": 3,
                "title": "Populate the editable campaign fields",
                "user_does": "Review the campaign dates, description, logos, field-rep login background image, printing settings, and status, then save the changes.",
                "user_sees": "The standard Django multipart form experience with the campaign values preserved on return.",
                "why_it_matters": "These fields drive the field-rep visual experience, campaign timing, and what downstream users see in the portal.",
                "expected_result": "The portal campaign record is ready for collateral setup and field-rep access.",
                "trainer_notes": "Because the route saves back to the same campaign update URL, it is normal to treat this page as a working draft screen rather than a one-time wizard.",
                "screenshot_file": "publisher-campaign-update.png",
                "screenshot_caption": "Campaign update form used to maintain the PE-side metadata for the selected campaign.",
                "screenshot_focus": "The editable form controls and save action.",
            },
            {
                "number": 4,
                "title": "Hand off to downstream campaign operations",
                "user_does": "After saving, hand the campaign over to the operator or internal team responsible for collaterals and field reps.",
                "user_sees": "The refreshed campaign update page, which now represents the latest local state for that campaign.",
                "why_it_matters": "Publisher onboarding is the start of the lifecycle, not the end. The downstream team still needs campaign context to assign reps and publish assets.",
                "expected_result": "The campaign is ready for staff-level operations and field-rep activation.",
                "trainer_notes": "If the publisher enters a campaign that does not yet exist locally, the portal automatically routes them into the create/update path rather than failing.",
                "screenshot_file": "publisher-campaign-update.png",
                "screenshot_caption": "Saved campaign update screen that becomes the handoff state for the operations team.",
                "screenshot_focus": "The persistent campaign record after publisher edits are stored.",
            },
        ],
        "success_criteria": [
            "The publisher can enter with a signed link and reach the campaign update screen.",
            "The distinction between master-owned and portal-owned data is clear.",
            "The saved campaign is ready to be used by the operational team.",
        ],
        "related_documents": [
            "docs/product-user-flows/03-internal-campaign-operations-from-the-manage-data-panel.md",
            "backend/campaign_management/views.py",
            "backend/campaign_management/publisher_auth.py",
        ],
        "status": f"Validated against the signed publisher demo route on {GENERATED_ON}.",
        "tips": [
            "Keep a sample signed URL handy during training so participants can see the JWT-based bootstrap in action.",
            "Explain that the landing page is intentionally simple because its main job is session establishment and campaign selection.",
        ],
    },
    {
        "order": 3,
        "slug": "internal-campaign-operations-from-the-manage-data-panel",
        "title": "Internal Campaign Operations from the Manage Data Panel",
        "deck_group": "Publisher and Campaign Operations",
        "document_purpose": "Teach internal operators how to search campaign inventory, open individual campaigns, and branch into the linked operational tools.",
        "primary_user": "Internal campaign operators and trainers onboarding operational staff.",
        "entry_point": "Authenticated portal login followed by `/campaigns/manage-data/`.",
        "workflow_summary": [
            "The Manage Data Panel pulls campaign reference data from the master database and merges it with any local portal campaign rows.",
            "Operators can search by brand campaign ID, brand name, or company name.",
            "Every campaign row provides direct shortcuts into view, edit, collateral, and field-rep operations.",
            "This screen is the fastest route for orienting to a campaign before switching into a role-specific workflow.",
        ],
        "steps": [
            {
                "number": 1,
                "title": "Log in and open the Manage Data Panel",
                "user_does": "Sign in to the portal and navigate to the Manage Data Panel.",
                "user_sees": "A searchable campaign table with brand campaign IDs, brand names, company names, dates, and action buttons.",
                "why_it_matters": "This is the operational inventory of campaigns that can be maintained in the portal right now.",
                "expected_result": "The operator can quickly locate the campaign that needs work.",
                "trainer_notes": "The campaign list combines master data and local data; blank start or end dates usually mean the portal-side campaign row is not fully configured yet.",
                "screenshot_file": "manage-data-panel.png",
                "screenshot_caption": "Manage Data Panel with campaign inventory and action buttons.",
                "screenshot_focus": "The search field and per-row action shortcuts.",
            },
            {
                "number": 2,
                "title": "Filter and inspect a specific campaign",
                "user_does": "Use the live search field and open the selected campaign's view or edit route.",
                "user_sees": "A campaign-specific page where the operator can inspect current metadata and decide which downstream tool to use next.",
                "why_it_matters": "Operators rarely work on every campaign at once; the panel is meant to narrow attention to a single campaign quickly.",
                "expected_result": "The campaign row that matters is isolated and ready for action.",
                "trainer_notes": "In the current product, the view and edit buttons are usually enough to verify whether a portal campaign row already exists for a master campaign.",
                "screenshot_file": "campaign-detail.png",
                "screenshot_caption": "Campaign detail page reached from the Manage Data Panel.",
                "screenshot_focus": "The campaign-specific detail context after selecting a row.",
            },
            {
                "number": 3,
                "title": "Branch into the next operational tool",
                "user_does": "Choose the shortcut for collateral management or field-rep management from the same row.",
                "user_sees": "A new tab that opens the downstream route with the campaign already filtered.",
                "why_it_matters": "The Manage Data Panel is meant to hand campaign context forward instead of forcing users to re-enter campaign IDs elsewhere.",
                "expected_result": "The next workflow opens already focused on the same brand campaign.",
                "trainer_notes": "This is where trainers should explain the campaign UUID as the shared handoff key across the product.",
                "screenshot_file": "manage-data-panel.png",
                "screenshot_caption": "Campaign row with shortcut buttons for downstream operations.",
                "screenshot_focus": "The direct handoff from campaign inventory into field-rep and collateral routes.",
            },
            {
                "number": 4,
                "title": "Confirm downstream readiness",
                "user_does": "Check that the campaign has the expected dates, status, and accessible collateral or rep routes.",
                "user_sees": "A consistent campaign context across the linked screens.",
                "why_it_matters": "A small mismatch at this stage can ripple into the sharing and doctor experience later.",
                "expected_result": "The operator knows the campaign is ready for rep and collateral workflows.",
                "trainer_notes": "The codebase currently links some operator buttons into routes that are role-gated differently, so it is worth validating the user account used for training ahead of time.",
                "screenshot_file": "manage-data-panel.png",
                "screenshot_caption": "Campaign inventory used as the launching point for all downstream work.",
                "screenshot_focus": "Campaign readiness before switching to the next role deck.",
            },
        ],
        "success_criteria": [
            "Operators can locate a campaign quickly from the campaign inventory.",
            "The purpose of each row-level shortcut is understood.",
            "The campaign is verified before the trainer moves into collateral or field-rep decks.",
        ],
        "related_documents": [
            "docs/product-user-flows/04-admin-field-rep-and-doctor-management.md",
            "docs/product-user-flows/05-collateral-authoring-and-message-setup.md",
            "backend/campaign_management/views.py",
        ],
        "status": f"Validated against the seeded Manage Data Panel on {GENERATED_ON}.",
        "tips": [
            "Use this deck immediately after the publisher deck so the same campaign ID is still familiar.",
            "Call out the current role-gating nuance when you demonstrate the collateral shortcut.",
        ],
    },
    {
        "order": 4,
        "slug": "admin-field-rep-and-doctor-management",
        "title": "Admin Field Rep and Doctor Management",
        "deck_group": "Admin Operations",
        "document_purpose": "Document how staff users maintain master field reps and the doctor lists attached to each rep.",
        "primary_user": "Staff admins and training leads who support rep onboarding and doctor list maintenance.",
        "entry_point": "Authenticated portal login followed by `/admin_dashboard/fieldreps/` or `/admin_dashboard/fieldreps/?campaign=<brand_campaign_id>`.",
        "workflow_summary": [
            "The field-rep list is sourced from the master database and can be filtered by brand campaign.",
            "Each field rep can be opened into a doctor-management screen backed by the portal doctor table.",
            "The screen is designed for campaign-scoped administration rather than open-ended browsing.",
            "Doctor data maintained here becomes reusable context in the field-rep sharing screens.",
        ],
        "steps": [
            {
                "number": 1,
                "title": "Open the field-rep list for a campaign",
                "user_does": "Navigate to the field-rep list and optionally keep the campaign filter in the URL.",
                "user_sees": "A table of master field reps with unique ID, field ID, Gmail ID, phone number, campaign mapping, and action buttons.",
                "why_it_matters": "Campaign filtering reduces noise and keeps training focused on the reps that actually matter for a launch.",
                "expected_result": "The admin can see exactly which reps are assigned to the selected campaign.",
                "trainer_notes": "The list mixes master-table data with a display-friendly campaign mapping string to make the assignment state easy to explain.",
                "screenshot_file": "fieldrep-list.png",
                "screenshot_caption": "Field-rep administration list filtered to the active campaign.",
                "screenshot_focus": "Campaign-filtered rep inventory and the doctor management action.",
            },
            {
                "number": 2,
                "title": "Review or create a field-rep record",
                "user_does": "Open the add or edit field-rep form, confirm the contact details, and keep the campaign context intact.",
                "user_sees": "A standard field-rep form that writes back to the master data tables and preserves the campaign filter in the redirect.",
                "why_it_matters": "Rep identity and campaign assignment need to be correct before any field-rep login or sharing flow works.",
                "expected_result": "The rep is active, reachable, and assigned to the right campaign.",
                "trainer_notes": "In the current implementation, the campaign-aware add button may point to an external field-rep site instead of the local Django form; document whichever environment your training run actually uses.",
                "screenshot_file": "fieldrep-form.png",
                "screenshot_caption": "Field-rep form used for create or update operations.",
                "screenshot_focus": "The contact and identifier fields that define the rep record.",
            },
            {
                "number": 3,
                "title": "Maintain the doctor list for a selected rep",
                "user_does": "Use the View Doctors action to add, edit, or remove doctors associated with the rep.",
                "user_sees": "A rep-specific doctor list and a compact add-doctor form on the same page.",
                "why_it_matters": "Doctors created here become reusable share targets in the field-rep experience.",
                "expected_result": "The rep leaves with a clean doctor list that can support fast WhatsApp sharing.",
                "trainer_notes": "This screen writes to the portal doctor table even though the rep itself lives in the master database.",
                "screenshot_file": "fieldrep-doctors.png",
                "screenshot_caption": "Doctor maintenance screen for a selected field rep.",
                "screenshot_focus": "The add-doctor form and existing doctor list tied to the rep.",
            },
            {
                "number": 4,
                "title": "Validate the rep-to-doctor handoff",
                "user_does": "Confirm that the rep's identifiers match the field-rep sharing login and that the doctor list looks ready for distribution.",
                "user_sees": "The rep record and doctor list aligned around a single campaign and rep identity.",
                "why_it_matters": "If the rep cannot log in or the doctor list is wrong, the downstream sharing demo will be frustrating and misleading.",
                "expected_result": "The rep administration workflow is complete and ready to hand off to the field-rep training segment.",
                "trainer_notes": "This is a good pause point to remind the audience that rep creation is master-data-driven while doctor maintenance is portal-data-driven.",
                "screenshot_file": "fieldrep-doctors.png",
                "screenshot_caption": "Rep-specific doctor list prepared for the sharing workflow.",
                "screenshot_focus": "The final state the field rep will rely on during outreach.",
            },
        ],
        "success_criteria": [
            "Admins can explain where rep data lives versus where doctor data lives.",
            "Campaign-filtered rep management is demonstrated clearly.",
            "Doctor lists are ready before the field-rep share workflow begins.",
        ],
        "related_documents": [
            "docs/product-user-flows/07-field-rep-sharing-and-doctor-bulk-upload.md",
            "backend/admin_dashboard/views.py",
            "backend/campaign_management/master_models.py",
        ],
        "status": f"Validated against the seeded staff-admin screens on {GENERATED_ON}.",
        "tips": [
            "Demonstrate the campaign filter before the doctor drill-down so the audience sees why the list is short and targeted.",
            "Mention that doctor list maintenance here is the cleanest way to prepare a live sharing demo.",
        ],
    },
    {
        "order": 5,
        "slug": "collateral-authoring-and-message-setup",
        "title": "Collateral Authoring and Message Setup",
        "deck_group": "Publisher and Campaign Operations",
        "document_purpose": "Show how campaign assets, collateral schedules, and WhatsApp messages are configured before field reps start sharing.",
        "primary_user": "Campaign operators and training leads preparing the collateral side of a launch.",
        "entry_point": "Campaign-scoped collateral panel: `/share/dashboard/?campaign=<brand_campaign_id>` plus `/collaterals/add/<brand_campaign_id>/` and `/collaterals/collateral-messages/`.",
        "workflow_summary": [
            "The collateral dashboard is the campaign-scoped control panel for asset inventory, calendar edits, and rep-facing shortcuts.",
            "Add Collateral combines campaign selection, asset upload, banner configuration, webinar metadata, and a default WhatsApp message path.",
            "Collateral Messages Management stores custom message text per campaign-collateral pair.",
            "Calendar windows determine when a collateral is considered available in the share screens.",
        ],
        "steps": [
            {
                "number": 1,
                "title": "Open the campaign collateral dashboard",
                "user_does": "Navigate to the campaign's collateral panel from the campaign inventory or directly through the filtered route.",
                "user_sees": "A campaign-scoped dashboard with buttons for Add Collaterals, Edit Calendar, Doctor Bulk Upload, and the field-rep entry links.",
                "why_it_matters": "This dashboard is the operator's launch pad for collateral and rep-facing setup.",
                "expected_result": "The operator sees the current collateral inventory and the next setup actions in one place.",
                "trainer_notes": "This route is campaign-aware and surfaces the same brand campaign ID used elsewhere in the product.",
                "screenshot_file": "collateral-dashboard.png",
                "screenshot_caption": "Campaign collateral dashboard with collateral inventory and setup shortcuts.",
                "screenshot_focus": "The operator-facing control panel for campaign assets.",
            },
            {
                "number": 2,
                "title": "Create or update a collateral asset",
                "user_does": "Open the Add Collateral form, upload the PDF and banners, choose the type, and add descriptive or webinar metadata.",
                "user_sees": "A large multipart form for purpose, content title, content ID, collateral type, PDF or Vimeo input, banners, doctor display name, and webinar details.",
                "why_it_matters": "This screen defines what the doctor ultimately sees after verification.",
                "expected_result": "The campaign has a polished collateral record that can be linked and shared.",
                "trainer_notes": "The form automatically creates a message row when a collateral is saved, which is why the message-management screen is part of the same training segment.",
                "screenshot_file": "add-collateral-form.png",
                "screenshot_caption": "Collateral input form used to create campaign-ready doctor content.",
                "screenshot_focus": "The PDF upload, metadata, and banner sections of the form.",
            },
            {
                "number": 3,
                "title": "Review or customize the WhatsApp message",
                "user_does": "Open the Collateral Messages Management page and inspect the message linked to the collateral and campaign pair.",
                "user_sees": "A searchable message list with campaign ID, collateral, message preview, status, and actions.",
                "why_it_matters": "The share experience depends on good rep-facing message text that includes the `$collateralLinks` placeholder.",
                "expected_result": "The active message is appropriate for the campaign and collateral being launched.",
                "trainer_notes": "Use this step to remind trainees that the message text is not global; it is scoped to a specific campaign and collateral.",
                "screenshot_file": "collateral-messages.png",
                "screenshot_caption": "Message-management page showing the campaign-to-collateral WhatsApp text setup.",
                "screenshot_focus": "The message preview list and campaign/collateral filtering controls.",
            },
            {
                "number": 4,
                "title": "Adjust the collateral calendar window",
                "user_does": "Open the Edit Calendar screen and confirm the start and end dates for the campaign-collateral mapping.",
                "user_sees": "A calendar-edit screen that controls whether a collateral is active in the share flow on the current date.",
                "why_it_matters": "Availability windows are one of the key reasons a collateral might not appear for a field rep even when the asset exists.",
                "expected_result": "Only the intended collateral is active during the campaign window.",
                "trainer_notes": "This is one of the first places to inspect if a field rep says a collateral is missing from the share page.",
                "screenshot_file": "edit-calendar.png",
                "screenshot_caption": "Calendar management screen used to control collateral availability windows.",
                "screenshot_focus": "The date controls that determine whether a collateral appears in the share flow.",
            },
        ],
        "success_criteria": [
            "Operators can create or review a collateral tied to the campaign.",
            "Message text and collateral availability windows are understood as part of the launch workflow.",
            "The field-rep-facing collateral inventory is ready before rep training starts.",
        ],
        "related_documents": [
            "docs/product-user-flows/07-field-rep-sharing-and-doctor-bulk-upload.md",
            "backend/collateral_management/views.py",
            "backend/collateral_management/views_collateral_message.py",
        ],
        "status": f"Validated against the seeded collateral dashboard and forms on {GENERATED_ON}.",
        "tips": [
            "Demonstrate the message placeholder explicitly so trainees understand how the short link gets injected.",
            "If a share screen looks empty, revisit the calendar window before assuming the asset is missing.",
        ],
    },
    {
        "order": 6,
        "slug": "field-rep-registration-and-login",
        "title": "Field Rep Registration and Login",
        "deck_group": "Field Rep Journeys",
        "inventory_status": "✅ up-to-date",
        "inventory_note": "Updated to reflect that registration/create-password routes now redirect into Gmail/manual login; no live self-service signup remains.",
        "document_purpose": "Explain the current public field-rep access screens, including the legacy compatibility redirects, the password login page, and the active Gmail/manual or SSO login path.",
        "primary_user": "Field reps and trainers preparing reps for their first campaign login.",
        "entry_point": "Public routes under `/share/fieldrep-register/`, `/share/fieldrep-create-password/`, `/share/fieldrep-login/`, and `/share/fieldrep-gmail-login/`.",
        "workflow_summary": [
            "The legacy registration and create-password routes no longer collect new credentials; they redirect into the Gmail/manual login screen with an informational banner.",
            "The product still supports both email/password login and Brand Specific Field ID plus Email ID login patterns.",
            "Signed SSO can also auto-complete the Gmail login flow by trusting the master Field Rep ID inside the URL or JWT payload.",
            "Campaign context can travel in the query string or session so a rep is taken directly into the correct campaign after login.",
            "The field-rep background can be campaign-specific when the campaign has a configured background image.",
        ],
        "steps": [
            {
                "number": 1,
                "title": "Open the legacy registration route and observe the redirect",
                "user_does": "Launch the campaign-scoped registration URL that older launch materials may still reference.",
                "user_sees": "The Gmail/manual login page with an info banner stating that Field Rep registration is no longer required.",
                "why_it_matters": "This explains the current product behavior when older documentation or bookmarks still point to the registration route.",
                "expected_result": "The rep lands on the active login surface instead of a self-service sign-up form.",
                "trainer_notes": "Call this out explicitly during training so the audience understands that the route is compatibility-only and not a live onboarding wizard anymore.",
                "screenshot_file": "fieldrep-register.png",
                "screenshot_caption": "Legacy registration URL redirecting into the current Gmail/manual login page.",
                "screenshot_focus": "The informational banner and redirected login screen shown instead of the old registration form.",
            },
            {
                "number": 2,
                "title": "Open the legacy create-password route and confirm the new handoff",
                "user_does": "Launch the create-password URL, optionally carrying the rep email, Field ID, and campaign in the query string.",
                "user_sees": "The same Gmail/manual login page, usually with the email and Field ID prefilled and the same informational banner.",
                "why_it_matters": "This shows how older password-setup links now preserve context while handing the rep into the supported login path.",
                "expected_result": "The rep can continue with the current login flow without losing the campaign or identifier context.",
                "trainer_notes": "Use this screen to explain that the product team simplified onboarding: reps are expected to log in, not create a new password from this route.",
                "screenshot_file": "fieldrep-create-password.png",
                "screenshot_caption": "Legacy create-password URL redirecting into the current login page with preserved identifiers.",
                "screenshot_focus": "The redirected Gmail/manual login form with prefilled rep context.",
            },
            {
                "number": 3,
                "title": "Review the direct email/password login screen",
                "user_does": "Open the field-rep login page tied to the active campaign.",
                "user_sees": "A focused login form that asks for email and password, preserves campaign context, and includes the same support chatbot used on the other public rep pages.",
                "why_it_matters": "This is the most straightforward rep-login method for routine use.",
                "expected_result": "The rep knows where to enter their standard credentials when the campaign requires the password flow.",
                "trainer_notes": "If the audience asks which login path to use, clarify what the current campaign rollout recommends before moving into the next workflow deck.",
                "screenshot_file": "fieldrep-login.png",
                "screenshot_caption": "Email/password field-rep login page for the selected campaign.",
                "screenshot_focus": "The direct credential-entry option for field reps.",
            },
            {
                "number": 4,
                "title": "Use the active Gmail/manual or SSO login path",
                "user_does": "Open the Gmail login route and either enter the Brand Specific Field ID plus Email ID manually or arrive through a signed SSO link that provides those values automatically.",
                "user_sees": "A campaign-scoped login form labeled Brand Specific Field ID and Email ID, along with the campaign context and the floating support chatbot.",
                "why_it_matters": "This is the primary live access route into the share experience and the path used by the seeded demo.",
                "expected_result": "The rep reaches the campaign share page with the correct assignment and session context.",
                "trainer_notes": "Manual login uses the brand-specific Field ID. Automatic SSO trusts the master Field Rep ID from the URL or JWT claims, then completes the same login path.",
                "screenshot_file": "fieldrep-gmail-login.png",
                "screenshot_caption": "Current Gmail/manual login page used for campaign-scoped rep access.",
                "screenshot_focus": "The Brand Specific Field ID and Email ID fields that lead directly into the share experience.",
            },
        ],
        "success_criteria": [
            "Trainees understand that registration and create-password routes are now compatibility redirects, not live onboarding forms.",
            "The difference between email/password, Gmail/manual login, and signed SSO is explained clearly.",
            "Campaign context in the URL is explained clearly.",
            "The group is ready to continue into the share workflow with the correct login path.",
        ],
        "related_documents": [
            "docs/product-user-flows/07-field-rep-sharing-and-doctor-bulk-upload.md",
            "backend/sharing_management/views.py",
            "backend/sharing_management/templates/sharing_management/fieldrep_gmail_login.html",
        ],
        "status": f"Validated against the current public rep-access screens on {GENERATED_ON}; legacy registration routes now documented as redirects into Gmail/manual login.",
        "tips": [
            "Lead with the Gmail/manual screen because it reflects the current launch path most accurately.",
            "Keep the rep deck practical: explain the legacy redirects once, then spend the rest of the time on the live login and share flow.",
        ],
    },
    {
        "order": 7,
        "slug": "field-rep-sharing-and-doctor-bulk-upload",
        "title": "Field Rep Sharing and Doctor Bulk Upload",
        "deck_group": "Field Rep Journeys",
        "inventory_status": "✅ up-to-date",
        "inventory_note": "Refreshed the share journey to cover the live quick-send actions, doctor-row status lifecycle, reminder follow-up, and chatbot-enabled public rep pages.",
        "document_purpose": "Document the day-to-day field-rep workflow for choosing doctors, filtering the doctor work queue, sending collateral through WhatsApp, following up with reminders, and bulk-uploading doctor rosters.",
        "primary_user": "Field reps and trainers running campaign distribution sessions.",
        "entry_point": "Campaign-scoped Gmail share route: `/share/fieldrep-gmail-share-collateral/?brand_campaign_id=<brand_campaign_id>` plus `/share/dashboard/doctors/bulk-upload/?campaign=<brand_campaign_id>`.",
        "workflow_summary": [
            "The Gmail share page is the campaign-aware workbench for choosing a doctor, choosing collateral, and launching the WhatsApp handoff.",
            "Doctors can be typed manually on the left-side form or reused from the rep's assigned doctor list on the right, where each row doubles as a quick-send shortcut.",
            "The right-side doctor statuses are collateral-specific and progress from `Send Message` to `Sent`, then to `Send Reminder` after six days without engagement, and finally to `Opened` once the doctor views the collateral.",
            "Each quick-send action creates or reuses a short link, upserts the doctor record if needed, writes a ShareLog entry, and opens the WhatsApp deep link for that doctor and collateral.",
            "The public rep screens now include the support chatbot so reps and trainers can jump into help without leaving the workflow.",
            "Bulk upload helps a rep or operator stage a doctor roster before manual sharing starts.",
        ],
        "steps": [
            {
                "number": 1,
                "title": "Authenticate into the campaign share screen",
                "user_does": "Use the Gmail login route for the selected campaign and land on the rep share screen.",
                "user_sees": "A campaign-scoped page with the rep identity, available collateral, doctor-sharing controls, and the floating support chatbot.",
                "why_it_matters": "This is the operational screen reps use most frequently during campaign outreach.",
                "expected_result": "The rep can see only the active collateral that belongs to the current campaign window.",
                "trainer_notes": "If the list is empty, check the campaign assignment and collateral calendar windows before debugging anything else. If login fails outright, confirm the rep is assigned to the campaign.",
                "screenshot_file": "fieldrep-gmail-share.png",
                "screenshot_caption": "Campaign share page after a successful Gmail/manual rep login.",
                "screenshot_focus": "The left-side share form, collateral picker, and help entry point at the top of the current screen.",
            },
            {
                "number": 2,
                "title": "Review the doctor queue and filter the worklist",
                "user_does": "Use the right-side search box, status filter, and collateral selector to find the doctor who needs action for the currently selected collateral.",
                "user_sees": "A searchable doctor roster with row-level quick-send buttons labeled `Send Message`, `Sent`, `Send Reminder`, or `Opened` depending on the latest share and engagement state.",
                "why_it_matters": "The right panel is the rep's live work queue. It shows who still needs a first send, who was contacted recently, who is ready for a reminder, and who already opened the collateral.",
                "expected_result": "The rep can isolate the correct doctor and understand whether the next action is an initial send, a reminder, or no action at all.",
                "trainer_notes": "Call out that the statuses are recalculated for the collateral currently selected on the left. Changing the collateral dropdown updates the hidden doctor-row forms and refreshes the right-side status list.",
                "screenshot_file": "fieldrep-doctor-status.png",
                "screenshot_caption": "Assigned doctor list with search, status filtering, and the live send-state buttons.",
                "screenshot_focus": "A mixed queue that shows `Send Message`, `Sent`, `Send Reminder`, and `Opened` for the currently selected collateral.",
            },
            {
                "number": 3,
                "title": "Send the first collateral message",
                "user_does": "Either complete the left-side doctor form and click `Submit`, or click a doctor-row `Send Message` button to quick-send the currently selected collateral.",
                "user_sees": "A submit action that resolves the doctor phone number, creates or updates the doctor record, creates or reuses the short link and ShareLog entry, and redirects into a WhatsApp deep link for the chosen doctor.",
                "why_it_matters": "This is the primary field-rep outcome: the doctor receives a trackable message that carries the right campaign, collateral, and rep context.",
                "expected_result": "The rep launches WhatsApp with the configured collateral message and the right short link for the selected doctor.",
                "trainer_notes": "The quick-send buttons on the right use the same POST flow as the left form. Trainers can demonstrate either path, but the doctor-row `Send Message` button is the fastest option once the roster is already loaded.",
                "screenshot_file": "fieldrep-send-message.png",
                "screenshot_caption": "Quick-send view filtered to doctors who still need the first collateral message.",
                "screenshot_focus": "The active `Send Message` button that launches the first-share flow for the selected collateral.",
            },
            {
                "number": 4,
                "title": "Send reminders and interpret follow-up states",
                "user_does": "Return to the same doctor list after a share and use the row buttons to follow up. A recent share shows `Sent`, a share older than six days without engagement changes to `Send Reminder`, and an engaged doctor shows `Opened`.",
                "user_sees": "The same doctor queue, but with the follow-up state reflected directly on each doctor row. Clicking `Send Reminder` or `Sent` reuses the currently selected collateral and opens WhatsApp again; `Opened` is visible but disabled.",
                "why_it_matters": "This is how reps decide whether to resend, remind, or move on without leaving the share screen or opening a separate report.",
                "expected_result": "The rep can identify reminder-ready doctors quickly and relaunch the WhatsApp handoff for follow-up outreach when needed.",
                "trainer_notes": "In the current UI only `Opened` is disabled. `Sent` still posts the same share flow, so teach teams to use it deliberately as a resend shortcut while treating `Send Reminder` as the clearer follow-up state once the six-day threshold is reached.",
                "screenshot_file": "fieldrep-send-reminder.png",
                "screenshot_caption": "Reminder-due doctor view showing the follow-up button for a previously shared collateral.",
                "screenshot_focus": "The `Send Reminder` action available after the share ages past the six-day threshold without a doctor view.",
            },
            {
                "number": 5,
                "title": "Bulk-upload doctors when onboarding a campaign",
                "user_does": "Open the Doctor Bulk Upload page, download the sample CSV if needed, and upload a prepared doctor file for the campaign.",
                "user_sees": "A purpose-built bulk-upload form that explains the expected CSV columns and confirms successful ingestion.",
                "why_it_matters": "Uploading a roster up front makes manual sharing dramatically faster once the campaign goes live.",
                "expected_result": "The rep or operator can stage multiple doctors for the same campaign in one pass.",
                "trainer_notes": "Use the bulk-upload step before the live sharing demo if you want the doctor list to look realistic without typing every doctor by hand.",
                "screenshot_file": "doctor-bulk-upload.png",
                "screenshot_caption": "Doctor bulk-upload screen with sample CSV guidance.",
                "screenshot_focus": "The upload field and the expected column list.",
            },
        ],
        "success_criteria": [
            "The rep can explain how the collateral selector, doctor search, and status filter work together on the share page.",
            "The audience understands the row-button lifecycle from `Send Message` to `Sent`, `Send Reminder`, and `Opened`.",
            "The audience understands why the doctor's exact WhatsApp number matters.",
            "The bulk-upload option is positioned as a preparation tool, not a separate reporting workflow.",
        ],
        "related_documents": [
            "docs/product-user-flows/08-doctor-verification-and-collateral-consumption.md",
            "backend/sharing_management/views.py",
            "backend/sharing_management/templates/sharing_management/fieldrep_gmail_share_collateral.html",
        ],
        "status": f"Validated against the Gmail/manual share flow and doctor bulk-upload page on {GENERATED_ON}.",
        "tips": [
            "Use a real-looking doctor list before your demo so the share screen feels grounded.",
            "Remind trainees that changing the collateral dropdown recalculates the right-side statuses for that collateral and keeps the quick-send forms in sync.",
            "Only `Opened` is disabled in the current template; `Sent` and `Send Reminder` are both actionable quick-send buttons.",
            "Warn the audience that the product opens a WhatsApp deep link, which may leave the browser context during a live session.",
        ],
    },
    {
        "order": 8,
        "slug": "doctor-verification-and-collateral-consumption",
        "title": "Doctor Verification and Collateral Consumption",
        "deck_group": "Doctor and Reporting",
        "inventory_status": "✅ up-to-date",
        "inventory_note": "Refreshed the verify/view screenshots and guidance for the current PDF viewer, archive/webinar layout, and support chatbot.",
        "document_purpose": "Show the doctor journey from WhatsApp short-link click through verification, viewer access, and archive/webinar exploration.",
        "primary_user": "Doctors, trainers demonstrating the doctor experience, and support teams validating the public flow.",
        "entry_point": "Public short-link path `/shortlinks/go/<code>/` which redirects into `/view/collateral/verify/`.",
        "workflow_summary": [
            "Short links resolve to a doctor verification screen rather than directly exposing the collateral.",
            "Verification is based on the last 10 digits of the WhatsApp number originally used in the share log.",
            "A successful verify step grants access, creates or reuses the doctor engagement context, and renders the PDF/video viewer.",
            "The viewer can show banners, embedded video, downloadable PDF content, archive links, webinar links, and the support chatbot.",
            "The PDF viewer now auto-loads with device-aware behavior: most devices use an in-page scroll box, while iOS devices switch to inline lazy rendering.",
        ],
        "steps": [
            {
                "number": 1,
                "title": "Open the short link and reach the verification page",
                "user_does": "Tap the short link from the WhatsApp message.",
                "user_sees": "A public Verify Access screen that asks for the WhatsApp number used during sharing and includes the floating support chatbot.",
                "why_it_matters": "This prevents the collateral from behaving like an unguarded public file link.",
                "expected_result": "The doctor is ready to prove they are the intended recipient.",
                "trainer_notes": "Support teams should always ask for the exact shared number when helping a doctor who cannot unlock content.",
                "screenshot_file": "doctor-verify.png",
                "screenshot_caption": "Public doctor verify page reached from the short link.",
                "screenshot_focus": "The number-entry step required before content is unlocked.",
            },
            {
                "number": 2,
                "title": "Verify with the same WhatsApp number used during sharing",
                "user_does": "Enter the matching 10-digit number and submit the form.",
                "user_sees": "A successful handoff into the doctor viewer instead of an access-denied message, with the unlocked collateral title and content area visible immediately.",
                "why_it_matters": "The matching logic is what binds the public doctor experience back to a specific share log and grants download access for that short link.",
                "expected_result": "The doctor gains access to the content and engagement tracking starts.",
                "trainer_notes": "If verification fails, double-check number formatting and whether the rep used a different phone number during sharing.",
                "screenshot_file": "doctor-viewer.png",
                "screenshot_caption": "Verified doctor viewer shown immediately after a successful unlock.",
                "screenshot_focus": "The content area that appears once verification succeeds.",
            },
            {
                "number": 3,
                "title": "Consume the PDF, banners, and video content",
                "user_does": "Scroll the PDF, watch the embedded video, or download the PDF copy.",
                "user_sees": "A branded viewer with banners, embedded Vimeo player, download button, and an auto-loading PDF area that adapts to the device type.",
                "why_it_matters": "This is the content experience the field rep promised to the doctor and the source of the later engagement metrics.",
                "expected_result": "Doctor engagement events can be captured and reflected in downstream reporting.",
                "trainer_notes": "The PDF area is intentionally large and scrollable because the product treats scroll depth as a meaningful engagement signal. On iPhone and iPad, the viewer switches to inline lazy rendering rather than a nested scroll box.",
                "screenshot_file": "doctor-viewer.png",
                "screenshot_caption": "Doctor viewer showing banners, PDF download, and the embedded collateral content.",
                "screenshot_focus": "The content-consumption experience after verification.",
            },
            {
                "number": 4,
                "title": "Use the archive and webinar options when present",
                "user_does": "Open older collateral from the archive cards or launch the webinar link.",
                "user_sees": "Additional campaign content options such as archive cards or a webinar panel below the primary collateral.",
                "why_it_matters": "The product can extend beyond a single PDF or video and act as a campaign micro-journey for the doctor.",
                "expected_result": "The doctor can discover related material without needing a separate share from the rep.",
                "trainer_notes": "Archive and webinar blocks are collateral-dependent, so explain that they appear only when the asset was configured with those extras.",
                "screenshot_file": "doctor-viewer-archive.png",
                "screenshot_caption": "Doctor viewer lower section showing optional follow-on content below the main collateral.",
                "screenshot_focus": "The webinar panel and any archive follow-ons available to the doctor after unlock.",
            },
        ],
        "success_criteria": [
            "The audience can explain why the doctor must use the same WhatsApp number.",
            "The doctor viewer's main content areas are easy to identify.",
            "Archive and webinar options are understood as optional extensions of the core flow.",
        ],
        "related_documents": [
            "docs/product-user-flows/07-field-rep-sharing-and-doctor-bulk-upload.md",
            "docs/product-user-flows/09-engagement-reporting-and-transaction-review.md",
            "backend/doctor_viewer/views.py",
        ],
        "status": f"Validated against the seeded public doctor flow on {GENERATED_ON}, including the current support widget and device-aware PDF viewer behavior.",
        "tips": [
            "Use the exact phone number from the seeded ShareLog when demonstrating the unlock step.",
            "If you demonstrate on iPhone or iPad, explain that the PDF scrolls inline with lazy page rendering rather than inside a separate box.",
            "A successful doctor demo is the best setup for the reporting deck because it gives the audience a concrete event chain to remember.",
        ],
    },
    {
        "order": 9,
        "slug": "engagement-reporting-and-transaction-review",
        "title": "Engagement Reporting and Transaction Review",
        "deck_group": "Doctor and Reporting",
        "document_purpose": "Show how campaign stakeholders review the doctor engagement outcomes created by sharing and doctor consumption.",
        "primary_user": "Campaign analysts, operations leads, and trainers closing the loop after a doctor demo.",
        "entry_point": "`/reports/collateral-transactions/<brand_campaign_id>/`.",
        "workflow_summary": [
            "The transaction dashboard aggregates the latest state per doctor, collateral, and field rep for the selected campaign.",
            "The collateral filter narrows the view when stakeholders want to discuss one asset at a time.",
            "Summary counters surface clicked doctors, downloaded PDFs, viewed-last-page counts, and video watch buckets.",
            "The doctor table is the operational follow-up surface for identifying which doctors engaged and how far they got.",
        ],
        "steps": [
            {
                "number": 1,
                "title": "Open the campaign transaction dashboard",
                "user_does": "Navigate directly to the report URL for the campaign.",
                "user_sees": "A branded reporting page with a campaign selector, collateral filter, summary section, and doctor table.",
                "why_it_matters": "This is the clearest operational view of whether the campaign is generating meaningful doctor interaction.",
                "expected_result": "Stakeholders can immediately orient to the campaign and available collateral.",
                "trainer_notes": "The dashboard is latest-state oriented, which is useful for follow-up but different from a raw event log.",
                "screenshot_file": "report-dashboard.png",
                "screenshot_caption": "Campaign transaction dashboard with summary metrics and doctor rows.",
                "screenshot_focus": "The top summary section and the campaign/collateral filters.",
            },
            {
                "number": 2,
                "title": "Filter to a specific collateral when needed",
                "user_does": "Choose a collateral from the drop-down and refresh the page context.",
                "user_sees": "The same dashboard narrowed to a single collateral's doctor outcomes.",
                "why_it_matters": "Filtering keeps the conversation concrete when the campaign has more than one asset.",
                "expected_result": "The summary metrics and doctor rows now reflect the selected collateral only.",
                "trainer_notes": "This is a strong way to compare flagship collateral against supporting leaflets during a training review.",
                "screenshot_file": "report-filtered.png",
                "screenshot_caption": "Transaction dashboard filtered to a specific collateral.",
                "screenshot_focus": "The same report with the collateral scope narrowed for discussion.",
            },
            {
                "number": 3,
                "title": "Read doctor-level engagement status",
                "user_does": "Scroll into the doctor rows and inspect who clicked, viewed, downloaded, or reached later video buckets.",
                "user_sees": "A doctor table that combines rep identity, doctor number, collateral title, and engagement state.",
                "why_it_matters": "This is the bridge from aggregate counts to real operational follow-up.",
                "expected_result": "The team can identify which doctors need another touchpoint or a different content approach.",
                "trainer_notes": "Use the report right after the doctor-viewer demo so the audience recognizes how those actions appear operationally.",
                "screenshot_file": "report-dashboard.png",
                "screenshot_caption": "Doctor-level table used for campaign follow-up discussions.",
                "screenshot_focus": "The detailed rows that support rep and campaign follow-up.",
            },
            {
                "number": 4,
                "title": "Export and reuse the report output",
                "user_does": "Use the CSV download option and hand the resulting data to downstream reporting or follow-up teams.",
                "user_sees": "A report page designed for operational review and export, not just on-screen viewing.",
                "why_it_matters": "Campaign reporting often continues outside the portal in spreadsheets or BI workflows.",
                "expected_result": "The transaction view can feed a follow-up or analytics process without manual rewriting.",
                "trainer_notes": "Even if the deck demo does not actually export a CSV live, call out the button so users know the path exists.",
                "screenshot_file": "report-dashboard.png",
                "screenshot_caption": "Report page showing the export-oriented controls.",
                "screenshot_focus": "The controls that let stakeholders take the data beyond the portal screen.",
            },
        ],
        "success_criteria": [
            "Stakeholders can connect doctor actions back to what they saw in the field-rep and doctor decks.",
            "The audience understands the difference between top-line counts and doctor-level rows.",
            "The export path is documented clearly enough for follow-up teams.",
        ],
        "related_documents": [
            "docs/product-user-flows/08-doctor-verification-and-collateral-consumption.md",
            "backend/sharing_management/views_transactions_page.py",
            "backend/sharing_management/services/transactions.py",
        ],
        "status": f"Validated against the seeded transaction dashboard on {GENERATED_ON}.",
        "tips": [
            "Close the training pack with this deck so the audience sees the business value of the earlier workflows.",
            "If time is short, focus on one collateral and one doctor row instead of trying to read every metric live.",
        ],
    },
]


WORKFLOW_BY_ORDER = {workflow["order"]: workflow for workflow in WORKFLOWS}
WORKFLOW_BY_SLUG = {workflow["slug"]: workflow for workflow in WORKFLOWS}


def _normalize_workflow_token(token: str) -> str:
    token = (token or "").strip()
    token = token.replace(".pptx", "").replace(".md", "")
    return token


def select_workflows(selection=None) -> list[dict]:
    if not selection:
        return list(WORKFLOWS)

    raw_tokens = selection if isinstance(selection, (list, tuple, set)) else [selection]
    tokens: list[str] = []
    for raw in raw_tokens:
        if raw is None:
            continue
        parts = str(raw).split(",")
        tokens.extend(part.strip() for part in parts if part.strip())

    if not tokens:
        return list(WORKFLOWS)

    selected: list[dict] = []
    seen_orders: set[int] = set()

    for token in tokens:
        normalized = _normalize_workflow_token(token)
        if normalized in {"*", "all"}:
            return list(WORKFLOWS)

        workflow = None
        if normalized.isdigit():
            workflow = WORKFLOW_BY_ORDER.get(int(normalized))
        if workflow is None and "-" in normalized and normalized.split("-", 1)[0].isdigit():
            workflow = WORKFLOW_BY_ORDER.get(int(normalized.split("-", 1)[0]))
        if workflow is None:
            workflow = WORKFLOW_BY_SLUG.get(normalized)

        if workflow is None:
            raise ValueError(f"Unknown workflow selector: {token}")
        if workflow["order"] in seen_orders:
            continue
        selected.append(workflow)
        seen_orders.add(workflow["order"])

    return sorted(selected, key=lambda workflow: workflow["order"])
