#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import uuid
from datetime import timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
RUNTIME_DIR = REPO_ROOT / "tmp" / "docs" / "demo_runtime"
SEED_DIR = RUNTIME_DIR / "seed_files"
MANIFEST_PATH = RUNTIME_DIR / "demo_manifest.json"


def reset_runtime() -> None:
    if RUNTIME_DIR.exists():
        shutil.rmtree(RUNTIME_DIR)
    SEED_DIR.mkdir(parents=True, exist_ok=True)


def bootstrap_django() -> None:
    sys.path.insert(0, str(BACKEND_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings_docs")

    import django

    django.setup()


def run_migrations() -> None:
    from django.core.management import call_command

    call_command("migrate", interactive=False, verbosity=0, database="default")
    call_command("migrate", interactive=False, verbosity=0, database="reporting")


def ensure_master_schema() -> None:
    master_db = RUNTIME_DIR / "master.sqlite3"
    con = sqlite3.connect(master_db)
    cur = con.cursor()

    cur.executescript(
        """
        PRAGMA foreign_keys = OFF;

        CREATE TABLE IF NOT EXISTS campaign_brand (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            company_name TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS campaign_campaign (
            id TEXT PRIMARY KEY,
            brand_id TEXT,
            name TEXT NOT NULL DEFAULT '',
            contact_person_name TEXT NOT NULL DEFAULT '',
            contact_person_phone TEXT NOT NULL DEFAULT '',
            contact_person_email TEXT NOT NULL DEFAULT '',
            num_doctors_supported INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS auth_user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            password TEXT NOT NULL,
            last_login TEXT NULL,
            is_superuser INTEGER NOT NULL DEFAULT 0,
            username TEXT NOT NULL UNIQUE,
            first_name TEXT NOT NULL DEFAULT '',
            last_name TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            is_staff INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            date_joined TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS campaign_fieldrep (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            brand_id TEXT NOT NULL,
            full_name TEXT NOT NULL DEFAULT '',
            phone_number TEXT NOT NULL DEFAULT '',
            brand_supplied_field_rep_id TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            password_hash TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS campaign_campaignfieldrep (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id TEXT NOT NULL,
            field_rep_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(campaign_id, field_rep_id)
        );
        """
    )

    con.commit()
    con.close()


def ensure_portal_schema_extensions() -> None:
    default_db = RUNTIME_DIR / "default.sqlite3"
    con = sqlite3.connect(default_db)
    cur = con.cursor()
    cur.executescript(
        """
        ALTER TABLE sharing_management_sharelog ADD COLUMN field_rep_email TEXT NOT NULL DEFAULT '';
        ALTER TABLE sharing_management_sharelog ADD COLUMN brand_campaign_id VARCHAR(32) NOT NULL DEFAULT '';

        ALTER TABLE sharing_management_securityquestion ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE sharing_management_securityquestion ADD COLUMN created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE sharing_management_securityquestion ADD COLUMN updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP;

        DROP TABLE IF EXISTS sharing_management_collateraltransaction;
        CREATE TABLE sharing_management_collateraltransaction (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            field_rep_id INTEGER NOT NULL,
            field_rep_email TEXT NOT NULL DEFAULT '',
            doctor_number VARCHAR(64) NOT NULL,
            doctor_name VARCHAR(255) NOT NULL DEFAULT '',
            collateral_id INTEGER NOT NULL,
            brand_campaign_id VARCHAR(32) NOT NULL DEFAULT '',
            share_channel VARCHAR(32) NOT NULL DEFAULT '',
            sent_at TEXT NULL,
            has_viewed INTEGER NOT NULL DEFAULT 0,
            first_viewed_at TEXT NULL,
            last_viewed_at TEXT NULL,
            pdf_last_page INTEGER NOT NULL DEFAULT 0,
            pdf_total_pages INTEGER NOT NULL DEFAULT 0,
            pdf_completed INTEGER NOT NULL DEFAULT 0,
            downloaded_pdf INTEGER NOT NULL DEFAULT 0,
            video_watch_percentage INTEGER NOT NULL DEFAULT 0,
            video_completed INTEGER NOT NULL DEFAULT 0,
            dv_engagement_id INTEGER NULL,
            sm_engagement_id VARCHAR(64) NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sharing_management_fieldrepsecurityprofile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            master_field_rep_id INTEGER NOT NULL UNIQUE,
            email TEXT NOT NULL DEFAULT '',
            security_question_id INTEGER NULL,
            security_answer_hash TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    con.commit()
    con.close()


def build_seed_assets() -> dict[str, Path]:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.load_default()

    def banner(path: Path, title: str, subtitle: str, size: tuple[int, int], colors: tuple[str, str]) -> None:
        img = Image.new("RGB", size, colors[0])
        draw = ImageDraw.Draw(img)

        stripe_height = max(size[1] // 5, 80)
        draw.rectangle([(0, size[1] - stripe_height), (size[0], size[1])], fill=colors[1])
        draw.rounded_rectangle(
            [(60, 60), (size[0] - 60, size[1] - 60)],
            radius=28,
            outline="white",
            width=5,
        )
        draw.text((100, 100), title, fill="white", font=font)
        draw.text((100, 140), subtitle, fill="white", font=font)
        draw.text((100, size[1] - stripe_height + 18), "InClinic demo asset", fill="white", font=font)
        img.save(path)

    def multipage_pdf(path: Path, pages: list[tuple[str, str]]) -> None:
        rendered = []
        for idx, (title, body) in enumerate(pages, start=1):
            img = Image.new("RGB", (1240, 1754), "white")
            draw = ImageDraw.Draw(img)
            draw.rectangle([(60, 60), (1180, 250)], fill="#0f4c81")
            draw.text((100, 110), title, fill="white", font=font)
            draw.text((100, 160), f"Page {idx}", fill="white", font=font)
            draw.rectangle([(100, 320), (1140, 1450)], outline="#0f4c81", width=4)
            draw.multiline_text((130, 380), body, fill="#1f2937", font=font, spacing=8)
            draw.text((130, 1510), "Demo collateral generated for documentation capture.", fill="#6b7280", font=font)
            rendered.append(img.convert("RGB"))

        rendered[0].save(path, save_all=True, append_images=rendered[1:])

    assets = {
        "brand_logo": SEED_DIR / "brand-logo.png",
        "company_logo": SEED_DIR / "company-logo.png",
        "login_background": SEED_DIR / "login-background.png",
        "banner_primary": SEED_DIR / "banner-primary.png",
        "banner_secondary": SEED_DIR / "banner-secondary.png",
        "main_pdf": SEED_DIR / "cardio-guide.pdf",
        "archive_pdf": SEED_DIR / "archive-guide.pdf",
    }

    banner(assets["brand_logo"], "CardioCare", "Brand mark", (600, 320), ("#0f4c81", "#38bdf8"))
    banner(assets["company_logo"], "Inditech Health", "Company mark", (600, 320), ("#166534", "#22c55e"))
    banner(assets["login_background"], "Field Rep Access", "Campaign-ready sign-in", (1600, 900), ("#1d4ed8", "#0ea5e9"))
    banner(assets["banner_primary"], "Doctor Education Kit", "CardioCare 2026", (1600, 900), ("#7c2d12", "#f97316"))
    banner(assets["banner_secondary"], "Evidence Snapshot", "Quarterly outcomes", (1600, 500), ("#1e3a8a", "#60a5fa"))

    multipage_pdf(
        assets["main_pdf"],
        [
            ("CardioCare Launch Guide", "Clinical positioning\nUsage summary\nRep talking points\nDoctor support workflow"),
            ("Patient Journey", "1. Share the guide\n2. Verify access\n3. Track scroll depth\n4. Review engagement"),
            ("Evidence Sheet", "Study A: improved adherence\nStudy B: better recall\nTrainer tip: call out the orange banner"),
            ("Closing Page", "Archive materials remain accessible from the viewer.\nUse the report dashboard for follow-up."),
        ],
    )
    multipage_pdf(
        assets["archive_pdf"],
        [
            ("CardioCare Archive", "Legacy materials stay available as archives.\nUse this to show the doctor archive panel."),
            ("Previous Quarter", "Retention summary\nHigh-level reminder script"),
        ],
    )

    return assets


def seed_demo_data() -> dict[str, object]:
    from django.contrib.auth.hashers import make_password
    from django.core.files import File
    from django.utils import timezone

    from campaign_management.models import Campaign
    from collateral_management.models import CampaignCollateral, Collateral, CollateralMessage
    from doctor_viewer.models import Doctor
    from sharing_management.models import FieldRepSecurityProfile, SecurityQuestion, ShareLog
    from sharing_management.services.transactions import (
        mark_downloaded_pdf,
        mark_pdf_progress,
        mark_video_event,
        mark_viewed,
        upsert_from_sharelog,
    )
    from shortlink_management.models import ShortLink
    from user_management.models import User
    import jwt
    from django.conf import settings
    from django.db import connection, connections

    now = timezone.now()
    assets = build_seed_assets()

    primary_campaign_uuid = uuid.UUID("11111111-1111-1111-1111-111111111111")
    secondary_campaign_uuid = uuid.UUID("22222222-2222-2222-2222-222222222222")

    master_rows = {
        "brands": [
            ("brand-cardio", "CardioCare", "Helios Therapeutics"),
            ("brand-neuro", "NeuroEase", "Helios Therapeutics"),
        ],
        "campaigns": [
            (
                primary_campaign_uuid.hex,
                "brand-cardio",
                "CardioCare Launch 2026",
                "Dr. Meera Iyer",
                "+91 98765 43210",
                "meera.iyer@example.com",
                240,
            ),
            (
                secondary_campaign_uuid.hex,
                "brand-neuro",
                "NeuroEase Awareness Sprint",
                "Dr. Sanjay Rao",
                "+91 99887 76655",
                "sanjay.rao@example.com",
                120,
            ),
        ],
    }

    master = connections["master"]
    with master.cursor() as cursor:
        cursor.execute("DELETE FROM campaign_campaignfieldrep")
        cursor.execute("DELETE FROM campaign_fieldrep")
        cursor.execute("DELETE FROM auth_user")
        cursor.execute("DELETE FROM campaign_campaign")
        cursor.execute("DELETE FROM campaign_brand")

        cursor.executemany(
            "INSERT INTO campaign_brand (id, name, company_name) VALUES (%s, %s, %s)",
            master_rows["brands"],
        )
        cursor.executemany(
            """
            INSERT INTO campaign_campaign
            (id, brand_id, name, contact_person_name, contact_person_phone, contact_person_email, num_doctors_supported)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            master_rows["campaigns"],
        )

        cursor.executemany(
            """
            INSERT INTO auth_user
            (password, last_login, is_superuser, username, first_name, last_name, email, is_staff, is_active, date_joined)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    make_password("FieldRep123!"),
                    None,
                    0,
                    "rep.docs",
                    "Asha",
                    "Patel",
                    "rep.docs@example.com",
                    0,
                    1,
                    now.isoformat(),
                ),
                (
                    make_password("FieldRep123!"),
                    None,
                    0,
                    "rep.neuro",
                    "Rohit",
                    "Shah",
                    "rep.neuro@example.com",
                    0,
                    1,
                    now.isoformat(),
                ),
            ],
        )

        users = cursor.execute("SELECT id, email FROM auth_user ORDER BY id").fetchall()
        rep_map = {email: user_id for user_id, email in users}

        cursor.executemany(
            """
            INSERT INTO campaign_fieldrep
            (user_id, brand_id, full_name, phone_number, brand_supplied_field_rep_id, is_active, password_hash, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    rep_map["rep.docs@example.com"],
                    "brand-cardio",
                    "Asha Patel",
                    "+91 98765 00001",
                    "FR-1001",
                    1,
                    make_password("FieldRep123!"),
                    now.isoformat(),
                    now.isoformat(),
                ),
                (
                    rep_map["rep.neuro@example.com"],
                    "brand-neuro",
                    "Rohit Shah",
                    "+91 98765 00002",
                    "FR-2001",
                    1,
                    make_password("FieldRep123!"),
                    now.isoformat(),
                    now.isoformat(),
                ),
            ],
        )

        reps = cursor.execute("SELECT id, brand_supplied_field_rep_id FROM campaign_fieldrep ORDER BY id").fetchall()
        rep_ids = {field_id: rep_id for rep_id, field_id in reps}

        cursor.executemany(
            """
            INSERT INTO campaign_campaignfieldrep (campaign_id, field_rep_id, created_at)
            VALUES (%s, %s, %s)
            """,
            [
                (primary_campaign_uuid.hex, rep_ids["FR-1001"], now.isoformat()),
                (secondary_campaign_uuid.hex, rep_ids["FR-2001"], now.isoformat()),
            ],
        )
        master.commit()

    admin_user, _ = User.objects.update_or_create(
        username="docs_admin",
        defaults={
            "email": "admin.docs@example.com",
            "first_name": "Admin",
            "last_name": "Trainer",
            "role": "admin",
            "is_staff": True,
            "is_superuser": True,
            "active": True,
            "is_active": True,
        },
    )
    admin_user.set_password("AdminDocs123!")
    admin_user.save()

    operator_user, _ = User.objects.update_or_create(
        username="docs_operator",
        defaults={
            "email": "rep.docs@example.com",
            "first_name": "Asha",
            "last_name": "Patel",
            "role": "field_rep",
            "field_id": "FR-1001",
            "phone_number": "+919876500001",
            "is_staff": True,
            "active": True,
            "is_active": True,
        },
    )
    operator_user.set_password("FieldRep123!")
    operator_user.save()

    Campaign.objects.all().delete()

    primary_campaign = Campaign.objects.create(
        name="CardioCare Launch 2026",
        brand_name="CardioCare",
        brand_campaign_id=primary_campaign_uuid,
        start_date=now - timedelta(days=10),
        end_date=now + timedelta(days=60),
        description="Primary documentation demo campaign.",
        company_name="Helios Therapeutics",
        incharge_name="Dr. Meera Iyer",
        incharge_contact="+91 98765 43210",
        incharge_designation="Medical Director",
        num_doctors=240,
        items_per_clinic_per_year=12,
        printing_required=True,
        status="Active",
        created_by=admin_user,
    )

    secondary_campaign = Campaign.objects.create(
        name="NeuroEase Awareness Sprint",
        brand_name="NeuroEase",
        brand_campaign_id=secondary_campaign_uuid,
        start_date=now - timedelta(days=5),
        end_date=now + timedelta(days=30),
        description="Secondary campaign to make dashboard lists look realistic.",
        company_name="Helios Therapeutics",
        incharge_name="Dr. Sanjay Rao",
        incharge_contact="+91 99887 76655",
        incharge_designation="Brand Lead",
        num_doctors=120,
        items_per_clinic_per_year=8,
        status="Draft",
        created_by=admin_user,
    )

    with assets["brand_logo"].open("rb") as fh:
        primary_campaign.brand_logo.save("docs/brand-logo.png", File(fh), save=False)
    with assets["company_logo"].open("rb") as fh:
        primary_campaign.company_logo.save("docs/company-logo.png", File(fh), save=False)
    with assets["login_background"].open("rb") as fh:
        primary_campaign.fieldrep_login_background_image.save("docs/login-background.png", File(fh), save=False)
    primary_campaign.save()

    CollateralMessage.objects.all().delete()
    CampaignCollateral.objects.all().delete()
    Collateral.objects.all().delete()
    ShortLink.objects.all().delete()
    ShareLog.objects.all().delete()
    Doctor.objects.all().delete()

    archive_collateral = Collateral.objects.create(
        campaign=primary_campaign,
        created_by=admin_user,
        purpose="Doctor education short",
        title="CardioCare Archive Overview",
        type="pdf",
        content_id="CC-ARCH-01",
        description="Legacy archive material shown in the doctor viewer archive list.",
        doctor_name="Meera Iyer",
        upload_date=now - timedelta(days=40),
    )
    with assets["archive_pdf"].open("rb") as fh:
        archive_collateral.file.save("docs/archive-guide.pdf", File(fh), save=False)
    archive_collateral.save()

    main_collateral = Collateral.objects.create(
        campaign=primary_campaign,
        created_by=admin_user,
        purpose="Doctor education long",
        title="CardioCare Doctor Education Kit",
        type="pdf_video",
        content_id="CC-DEK-2026",
        vimeo_url="76979871",
        description="Flagship collateral used across the demo share and doctor journeys.",
        doctor_name="Meera Iyer",
        webinar_title="CardioCare Evidence Webinar",
        webinar_description="Recorded webinar that explains the latest study highlights and talking points.",
        webinar_url="https://diap.example.com/webinar/cardio-care-2026",
        webinar_date=(now + timedelta(days=14)).date(),
        upload_date=now - timedelta(days=2),
    )
    with assets["main_pdf"].open("rb") as fh:
        main_collateral.file.save("docs/cardio-guide.pdf", File(fh), save=False)
    with assets["banner_primary"].open("rb") as fh:
        main_collateral.banner_1.save("docs/banner-primary.png", File(fh), save=False)
    with assets["banner_secondary"].open("rb") as fh:
        main_collateral.banner_2.save("docs/banner-secondary.png", File(fh), save=False)
    main_collateral.save()

    supplemental_collateral = Collateral.objects.create(
        campaign=primary_campaign,
        created_by=admin_user,
        purpose="Patient education compliance",
        title="CardioCare Starter Leaflet",
        type="pdf",
        content_id="CC-LEAF-01",
        description="Secondary collateral used to populate collateral lists and reports.",
        upload_date=now - timedelta(days=1),
    )
    with assets["archive_pdf"].open("rb") as fh:
        supplemental_collateral.file.save("docs/starter-leaflet.pdf", File(fh), save=False)
    supplemental_collateral.save()

    for collateral, start_offset, end_offset in [
        (archive_collateral, -90, -10),
        (main_collateral, -7, 45),
        (supplemental_collateral, -2, 30),
    ]:
        CampaignCollateral.objects.create(
            campaign=primary_campaign,
            collateral=collateral,
            start_date=now + timedelta(days=start_offset),
            end_date=now + timedelta(days=end_offset),
        )

    CollateralMessage.objects.create(
        campaign=primary_campaign,
        collateral=main_collateral,
        message="Hello Doctor, please review the latest CardioCare material here: $collateralLinks",
        is_active=True,
    )
    CollateralMessage.objects.create(
        campaign=primary_campaign,
        collateral=supplemental_collateral,
        message="Please keep this starter leaflet handy for your next clinic discussion: $collateralLinks",
        is_active=True,
    )

    doctor_one = Doctor.objects.create(rep=operator_user, name="Dr. Priya Raman", phone="9876543210", source="manual")
    doctor_two = Doctor.objects.create(rep=operator_user, name="Dr. Kunal Shah", phone="9988776655", source="manual")
    doctor_three = Doctor.objects.create(rep=operator_user, name="Dr. Aditi Nair", phone="9123456780", source="manual")
    doctor_four = Doctor.objects.create(rep=operator_user, name="Dr. Neha Kapoor", phone="9012345678", source="manual")

    shortlink_archive = ShortLink.objects.create(
        short_code="cardio-archive-demo",
        resource_type="collateral",
        resource_id=archive_collateral.id,
        created_by=admin_user,
        is_active=True,
    )
    shortlink_main = ShortLink.objects.create(
        short_code="cardio-main-demo",
        resource_type="collateral",
        resource_id=main_collateral.id,
        created_by=admin_user,
        is_active=True,
    )
    shortlink_supplemental = ShortLink.objects.create(
        short_code="cardio-leaflet-demo",
        resource_type="collateral",
        resource_id=supplemental_collateral.id,
        created_by=admin_user,
        is_active=True,
    )

    question = SecurityQuestion.objects.create(question_txt="What is your favorite city?", is_active=True)
    SecurityQuestion.objects.create(question_txt="What was your first school?", is_active=True)
    FieldRepSecurityProfile.objects.update_or_create(
        master_field_rep_id=rep_ids["FR-1001"],
        defaults={
            "email": "rep.docs@example.com",
            "security_question": question,
            "security_answer_hash": make_password("Mumbai"),
        },
    )

    share_one = ShareLog.objects.create(
        short_link=shortlink_main,
        collateral=main_collateral,
        field_rep_id=rep_ids["FR-1001"],
        field_rep_email="rep.docs@example.com",
        doctor_identifier="+919876543210",
        share_channel="WhatsApp",
        message_text="Hello Doctor, please review the latest CardioCare material here: $collateralLinks",
        brand_campaign_id=str(primary_campaign.brand_campaign_id),
        share_timestamp=now - timedelta(hours=8),
    )
    share_two = ShareLog.objects.create(
        short_link=shortlink_main,
        collateral=main_collateral,
        field_rep_id=rep_ids["FR-1001"],
        field_rep_email="rep.docs@example.com",
        doctor_identifier="+919988776655",
        share_channel="WhatsApp",
        message_text="Hello Doctor, please review the latest CardioCare material here: $collateralLinks",
        brand_campaign_id=str(primary_campaign.brand_campaign_id),
        share_timestamp=now - timedelta(hours=3),
    )
    share_three = ShareLog.objects.create(
        short_link=shortlink_main,
        collateral=main_collateral,
        field_rep_id=rep_ids["FR-1001"],
        field_rep_email="rep.docs@example.com",
        doctor_identifier="+919123456780",
        share_channel="WhatsApp",
        message_text="Hello Doctor, please review the latest CardioCare material here: $collateralLinks",
        brand_campaign_id=str(primary_campaign.brand_campaign_id),
        share_timestamp=now - timedelta(days=8),
    )
    share_four = ShareLog.objects.create(
        short_link=shortlink_archive,
        collateral=archive_collateral,
        field_rep_id=rep_ids["FR-1001"],
        field_rep_email="rep.docs@example.com",
        doctor_identifier="+919912345678",
        share_channel="Email",
        message_text="Archive material for your reference: $collateralLinks",
        brand_campaign_id=str(primary_campaign.brand_campaign_id),
        share_timestamp=now - timedelta(days=2),
    )

    for share_log, doctor_name in [
        (share_one, doctor_one.name),
        (share_two, doctor_two.name),
        (share_three, doctor_three.name),
        (share_four, "Dr. Kavita Rao"),
    ]:
        upsert_from_sharelog(
            share_log,
            brand_campaign_id=str(primary_campaign.brand_campaign_id),
            doctor_name=doctor_name,
            field_rep_unique_id="FR-1001",
            sent_at=share_log.share_timestamp,
        )

    mark_viewed(share_one)
    mark_pdf_progress(share_one, last_page=4, completed=True, total_pages=4)
    mark_downloaded_pdf(share_one)
    mark_video_event(share_one, percentage=100)

    publisher_token = jwt.encode(
        {
            "sub": "publisher-demo-user",
            "username": "publisher.docs",
            "roles": ["publisher"],
            "iss": settings.PUBLISHER_JWT_ISSUER,
            "aud": settings.PUBLISHER_JWT_AUDIENCE,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=4)).timestamp()),
        },
        settings.PUBLISHER_JWT_SECRET,
        algorithm=settings.PUBLISHER_JWT_ALGORITHMS[0],
    )

    return {
        "base_url": settings.SITE_URL,
        "credentials": {
            "admin": {"username": "docs_admin", "password": "AdminDocs123!"},
            "operator": {"username": "docs_operator", "password": "FieldRep123!"},
            "field_rep_public": {
                "field_id": "FR-1001",
                "email": "rep.docs@example.com",
                "password": "FieldRep123!",
            },
        },
        "campaign": {
            "primary_uuid": str(primary_campaign.brand_campaign_id),
            "secondary_uuid": str(secondary_campaign.brand_campaign_id),
            "primary_pk": primary_campaign.pk,
        },
        "master_ids": {
            "primary_rep_id": rep_ids["FR-1001"],
            "secondary_rep_id": rep_ids["FR-2001"],
        },
        "doctor_flow": {
            "doctor_name": doctor_one.name,
            "doctor_phone_last10": doctor_one.phone,
            "doctor_phone_e164": "+919876543210",
            "short_code": shortlink_main.short_code,
            "short_link_id": shortlink_main.id,
            "share_log_id": share_one.id,
        },
        "collateral_ids": {
            "main": main_collateral.id,
            "supplemental": supplemental_collateral.id,
            "archive": archive_collateral.id,
        },
        "fieldrep_doctors": {
            "opened": {"name": doctor_one.name, "phone_last10": doctor_one.phone},
            "sent": {"name": doctor_two.name, "phone_last10": doctor_two.phone},
            "reminder": {"name": doctor_three.name, "phone_last10": doctor_three.phone},
            "not_sent": {"name": doctor_four.name, "phone_last10": doctor_four.phone},
        },
        "pages": {
            "admin_login": "/admin/login/",
            "manage_data": "/campaigns/manage-data/",
            "campaign_update": f"/campaigns/campaign/{primary_campaign.brand_campaign_id}/edit/",
            "publisher_landing": f"/campaigns/publisher-landing-page/?campaign-id={primary_campaign.brand_campaign_id}&jwt={publisher_token}",
            "fieldrep_list": f"/admin_dashboard/fieldreps/?campaign={primary_campaign.brand_campaign_id}",
            "fieldrep_doctors": f"/admin_dashboard/fieldreps/{rep_ids['FR-1001']}/doctors/",
            "collateral_dashboard": f"/share/dashboard/?campaign={primary_campaign.brand_campaign_id}",
            "add_collateral": f"/collaterals/add/{primary_campaign.brand_campaign_id}/",
            "collateral_messages": "/collaterals/collateral-messages/",
            "fieldrep_register": f"/share/fieldrep-register/?campaign={primary_campaign.brand_campaign_id}",
            "fieldrep_create_password": f"/share/fieldrep-create-password/?campaign={primary_campaign.brand_campaign_id}&email=rep.docs%40example.com",
            "fieldrep_login": f"/share/fieldrep-login/?campaign={primary_campaign.brand_campaign_id}",
            "fieldrep_gmail_login": f"/share/fieldrep-gmail-login/?campaign={primary_campaign.brand_campaign_id}",
            "fieldrep_share": f"/share/fieldrep-share-collateral/{primary_campaign.brand_campaign_id}/",
            "fieldrep_gmail_share": f"/share/fieldrep-gmail-share-collateral/?brand_campaign_id={primary_campaign.brand_campaign_id}",
            "doctor_bulk_upload": f"/share/dashboard/doctors/bulk-upload/?campaign={primary_campaign.brand_campaign_id}",
            "doctor_verify": f"/view/collateral/verify/?short_link_id={shortlink_main.id}",
            "doctor_public_shortlink": f"/shortlinks/go/{shortlink_main.short_code}/?share_id={share_one.id}",
            "report_dashboard": f"/reports/collateral-transactions/{primary_campaign.brand_campaign_id}/",
        },
    }


def main() -> None:
    reset_runtime()
    bootstrap_django()
    run_migrations()
    ensure_master_schema()
    ensure_portal_schema_extensions()
    manifest = seed_demo_data()
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
