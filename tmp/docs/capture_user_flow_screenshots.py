#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright.sync_api import Page, sync_playwright

from workflow_pack_data import select_workflows

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "tmp" / "docs" / "demo_runtime" / "demo_manifest.json"
ASSET_ROOT = REPO_ROOT / "docs" / "product-user-flows" / "assets"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def asset_path(slug: str, filename: str) -> Path:
    path = ASSET_ROOT / slug / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def login_via_admin(page: Page, base_url: str, username: str, password: str) -> None:
    page.goto(f"{base_url}/admin/login/", wait_until="networkidle")
    page.fill("input[name='username']", username)
    page.fill("input[name='password']", password)
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")


def duplicate(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def capture(page: Page, path: Path, full_page: bool = False) -> None:
    page.screenshot(path=str(path), full_page=full_page)


def capture_locator(locator, path: Path) -> None:
    locator.screenshot(path=str(path))


def with_query_params(path: str, **params: str) -> str:
    parts = urlsplit(path)
    current = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in params.items():
        if value is None:
            continue
        current[key] = value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(current), parts.fragment))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture workflow screenshots for the training pack.")
    parser.add_argument(
        "selectors",
        nargs="*",
        help="Optional workflow orders or slugs to capture. Defaults to all workflows.",
    )
    parser.add_argument(
        "--workflows",
        dest="workflow_csv",
        help="Comma-separated workflow orders or slugs to capture.",
    )
    return parser.parse_args()


def fieldrep_share_url(manifest: dict, collateral_id: int | str | None = None) -> str:
    path = manifest["pages"]["fieldrep_gmail_share"]
    if collateral_id is not None:
        path = with_query_params(path, collateral=str(collateral_id))
    return f"{manifest['base_url']}{path}"


def login_fieldrep_public(page: Page, manifest: dict) -> None:
    base_url = manifest["base_url"]
    pages = manifest["pages"]
    creds = manifest["credentials"]["field_rep_public"]

    page.goto(f"{base_url}{pages['fieldrep_gmail_login']}", wait_until="networkidle")
    page.fill("input[name='field_id']", creds["field_id"])
    page.fill("input[name='gmail_id']", creds["email"])
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(400)


def expect_share_redirect(page: Page, click_action, expected_phone_digits: str) -> None:
    with page.expect_response(
        lambda response: response.request.method == "POST" and "fieldrep-gmail-share-collateral" in response.url
    ) as response_info:
        click_action()

    response = response_info.value
    location = response.header_value("location") or ""
    assert response.status in {302, 303}, f"Expected redirect status from share action, got {response.status}"
    assert location.startswith("https://wa.me/"), f"Expected WhatsApp redirect, got {location}"
    assert expected_phone_digits in location, f"Expected phone digits {expected_phone_digits} in redirect {location}"


def row_button(page: Page, doctor_name: str):
    return page.locator(".doctor-row", has_text=doctor_name).locator("button")


def smoke_test_fieldrep_share_actions(page: Page, manifest: dict, share_url: str) -> None:
    page.route("https://wa.me/**", lambda route: route.fulfill(status=200, body="WhatsApp stub for docs capture"))

    page.goto(share_url, wait_until="networkidle")
    page.wait_for_timeout(200)
    page.fill("input[name='doctor_name']", "Dr. Manual Share Demo")
    page.fill("input[name='doctor_whatsapp']", "9090909090")
    expect_share_redirect(
        page,
        lambda: page.locator(".col-12.col-lg-4 form button[type='submit']").click(),
        "919090909090",
    )

    doctors = manifest["fieldrep_doctors"]

    page.goto(share_url, wait_until="networkidle")
    page.wait_for_timeout(200)
    expect_share_redirect(
        page,
        lambda: row_button(page, doctors["not_sent"]["name"]).click(),
        f"91{doctors['not_sent']['phone_last10']}",
    )

    page.goto(share_url, wait_until="networkidle")
    page.wait_for_timeout(200)
    expect_share_redirect(
        page,
        lambda: row_button(page, doctors["sent"]["name"]).click(),
        f"91{doctors['sent']['phone_last10']}",
    )

    page.goto(share_url, wait_until="networkidle")
    page.wait_for_timeout(200)
    expect_share_redirect(
        page,
        lambda: row_button(page, doctors["reminder"]["name"]).click(),
        f"91{doctors['reminder']['phone_last10']}",
    )

    page.goto(share_url, wait_until="networkidle")
    opened_button = row_button(page, doctors["opened"]["name"])
    assert opened_button.is_disabled(), "Expected the opened doctor action to be disabled"


def capture_public_home(page: Page, base_url: str) -> None:
    page.goto(base_url, wait_until="networkidle")
    capture(page, asset_path("platform-overview-and-role-map", "platform-home.png"))


def capture_publisher_flow(page: Page, manifest: dict) -> None:
    base_url = manifest["base_url"]
    pages = manifest["pages"]

    page.goto(f"{base_url}{pages['publisher_landing']}", wait_until="networkidle")
    capture(page, asset_path("publisher-campaign-onboarding-and-update", "publisher-landing.png"))

    page.goto(f"{base_url}{pages['campaign_update']}", wait_until="networkidle")
    capture(page, asset_path("publisher-campaign-onboarding-and-update", "publisher-campaign-update.png"))


def capture_admin_ops(page: Page, manifest: dict, selected_orders: set[int]) -> None:
    base_url = manifest["base_url"]
    pages = manifest["pages"]
    campaign_uuid = manifest["campaign"]["primary_uuid"]

    if 1 in selected_orders or 3 in selected_orders:
        page.goto(f"{base_url}{pages['manage_data']}", wait_until="networkidle")
        manage_data = asset_path("internal-campaign-operations-from-the-manage-data-panel", "manage-data-panel.png")
        capture(page, manage_data)
        duplicate(manage_data, asset_path("platform-overview-and-role-map", "platform-manage-data.png"))

    if 3 in selected_orders:
        page.goto(f"{base_url}/campaigns/campaign/{campaign_uuid}/", wait_until="networkidle")
        capture(page, asset_path("internal-campaign-operations-from-the-manage-data-panel", "campaign-detail.png"))

    if 4 in selected_orders:
        page.goto(f"{base_url}{pages['fieldrep_list']}", wait_until="networkidle")
        capture(page, asset_path("admin-field-rep-and-doctor-management", "fieldrep-list.png"))

        page.goto(f"{base_url}/admin_dashboard/fieldreps/add/?campaign={campaign_uuid}", wait_until="networkidle")
        capture(page, asset_path("admin-field-rep-and-doctor-management", "fieldrep-form.png"))

        page.goto(f"{base_url}{pages['fieldrep_doctors']}", wait_until="networkidle")
        capture(page, asset_path("admin-field-rep-and-doctor-management", "fieldrep-doctors.png"))

    if 1 in selected_orders or 9 in selected_orders:
        page.goto(f"{base_url}{pages['report_dashboard']}", wait_until="networkidle")
        report_dash = asset_path("engagement-reporting-and-transaction-review", "report-dashboard.png")
        capture(page, report_dash)
        duplicate(report_dash, asset_path("platform-overview-and-role-map", "platform-reporting-loop.png"))

    if 9 in selected_orders:
        option = page.locator("#collateralFilter option").nth(1)
        value = option.get_attribute("value")
        if value:
            page.goto(f"{base_url}{pages['report_dashboard']}?collateral_id={value}", wait_until="networkidle")
            capture(page, asset_path("engagement-reporting-and-transaction-review", "report-filtered.png"))


def capture_operator_ops(page: Page, manifest: dict, selected_orders: set[int]) -> None:
    base_url = manifest["base_url"]
    pages = manifest["pages"]
    campaign_uuid = manifest["campaign"]["primary_uuid"]

    if 5 in selected_orders:
        page.goto(f"{base_url}{pages['collateral_dashboard']}", wait_until="networkidle")
        capture(page, asset_path("collateral-authoring-and-message-setup", "collateral-dashboard.png"))

        page.goto(f"{base_url}{pages['add_collateral']}", wait_until="networkidle")
        capture(page, asset_path("collateral-authoring-and-message-setup", "add-collateral-form.png"))

        page.goto(f"{base_url}{pages['collateral_messages']}", wait_until="networkidle")
        capture(page, asset_path("collateral-authoring-and-message-setup", "collateral-messages.png"))

        page.goto(f"{base_url}/share/edit-calendar/?brand={campaign_uuid}", wait_until="networkidle")
        capture(page, asset_path("collateral-authoring-and-message-setup", "edit-calendar.png"))

    if 7 in selected_orders:
        page.goto(f"{base_url}{pages['doctor_bulk_upload']}", wait_until="networkidle")
        capture(page, asset_path("field-rep-sharing-and-doctor-bulk-upload", "doctor-bulk-upload.png"))


def capture_fieldrep_public(page: Page, manifest: dict, selected_orders: set[int]) -> None:
    pages = manifest["pages"]
    creds = manifest["credentials"]["field_rep_public"]

    if 6 in selected_orders:
        base_url = manifest["base_url"]
        page.goto(f"{base_url}{pages['fieldrep_register']}", wait_until="networkidle")
        page.wait_for_timeout(250)
        capture(page, asset_path("field-rep-registration-and-login", "fieldrep-register.png"))

        create_password_path = with_query_params(
            pages["fieldrep_create_password"],
            field_id=creds["field_id"],
        )
        page.goto(f"{base_url}{create_password_path}", wait_until="networkidle")
        page.wait_for_timeout(250)
        capture(page, asset_path("field-rep-registration-and-login", "fieldrep-create-password.png"))

        page.goto(f"{base_url}{pages['fieldrep_login']}", wait_until="networkidle")
        page.wait_for_timeout(250)
        capture(page, asset_path("field-rep-registration-and-login", "fieldrep-login.png"))

        page.goto(f"{base_url}{pages['fieldrep_gmail_login']}", wait_until="networkidle")
        page.wait_for_timeout(250)
        capture(page, asset_path("field-rep-registration-and-login", "fieldrep-gmail-login.png"))

    if 1 in selected_orders or 7 in selected_orders:
        login_fieldrep_public(page, manifest)
        main_collateral_id = manifest["collateral_ids"]["main"]
        share_url = fieldrep_share_url(manifest, main_collateral_id)
        page.goto(share_url, wait_until="networkidle")
        page.wait_for_timeout(400)

        share_top = asset_path("field-rep-sharing-and-doctor-bulk-upload", "fieldrep-gmail-share.png")
        capture(page, share_top)
        if 1 in selected_orders:
            duplicate(share_top, asset_path("platform-overview-and-role-map", "platform-share-handoff.png"))

        doctor_panel = page.locator(".col-12.col-lg-8 .card.shadow")
        page.wait_for_timeout(300)
        capture_locator(doctor_panel, asset_path("field-rep-sharing-and-doctor-bulk-upload", "fieldrep-doctor-status.png"))

        page.select_option("#statusFilter", "not_sent")
        page.wait_for_timeout(250)
        capture_locator(doctor_panel, asset_path("field-rep-sharing-and-doctor-bulk-upload", "fieldrep-send-message.png"))

        page.select_option("#statusFilter", "reminder")
        page.wait_for_timeout(250)
        capture_locator(doctor_panel, asset_path("field-rep-sharing-and-doctor-bulk-upload", "fieldrep-send-reminder.png"))

        page.select_option("#statusFilter", "")
        page.wait_for_timeout(150)
        smoke_test_fieldrep_share_actions(page, manifest, share_url)


def capture_doctor_flow(page: Page, manifest: dict) -> None:
    base_url = manifest["base_url"]
    pages = manifest["pages"]
    doctor = manifest["doctor_flow"]

    page.goto(f"{base_url}{pages['doctor_verify']}", wait_until="networkidle")
    capture(page, asset_path("doctor-verification-and-collateral-consumption", "doctor-verify.png"))

    page.fill("input[name='whatsapp_number']", doctor["doctor_phone_last10"])
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    capture(page, asset_path("doctor-verification-and-collateral-consumption", "doctor-viewer.png"))
    archive_heading = page.locator("text=Archives")
    if archive_heading.count():
        archive_heading.scroll_into_view_if_needed()
    else:
        page.mouse.wheel(0, 1600)
    page.wait_for_timeout(400)
    capture(page, asset_path("doctor-verification-and-collateral-consumption", "doctor-viewer-archive.png"))


def main() -> None:
    args = parse_args()
    selectors = list(args.selectors)
    if args.workflow_csv:
        selectors.append(args.workflow_csv)
    selected_workflows = select_workflows(selectors)
    selected_orders = {workflow["order"] for workflow in selected_workflows}

    manifest = load_manifest()
    base_url = manifest["base_url"]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        if 1 in selected_orders or 2 in selected_orders:
            public_ctx = browser.new_context(viewport={"width": 1600, "height": 1100})
            public_page = public_ctx.new_page()
            if 1 in selected_orders:
                capture_public_home(public_page, base_url)
            if 2 in selected_orders:
                capture_publisher_flow(public_page, manifest)

        if selected_orders & {1, 3, 4, 9}:
            admin_ctx = browser.new_context(viewport={"width": 1600, "height": 1100})
            admin_page = admin_ctx.new_page()
            login_via_admin(
                admin_page,
                base_url,
                manifest["credentials"]["admin"]["username"],
                manifest["credentials"]["admin"]["password"],
            )
            capture_admin_ops(admin_page, manifest, selected_orders)

        if selected_orders & {5, 7}:
            operator_ctx = browser.new_context(viewport={"width": 1600, "height": 1100})
            operator_page = operator_ctx.new_page()
            login_via_admin(
                operator_page,
                base_url,
                manifest["credentials"]["operator"]["username"],
                manifest["credentials"]["operator"]["password"],
            )
            capture_operator_ops(operator_page, manifest, selected_orders)

        if selected_orders & {1, 6, 7}:
            fieldrep_ctx = browser.new_context(viewport={"width": 1600, "height": 1100})
            fieldrep_page = fieldrep_ctx.new_page()
            capture_fieldrep_public(fieldrep_page, manifest, selected_orders)

        if 8 in selected_orders:
            doctor_ctx = browser.new_context(viewport={"width": 1600, "height": 1100})
            doctor_page = doctor_ctx.new_page()
            capture_doctor_flow(doctor_page, manifest)

        browser.close()

    selected_orders_text = ", ".join(f"{workflow['order']:02d}" for workflow in selected_workflows)
    print(f"Captured user-flow screenshots into docs/product-user-flows/assets/ for workflows: {selected_orders_text}")


if __name__ == "__main__":
    sys.exit(main())
