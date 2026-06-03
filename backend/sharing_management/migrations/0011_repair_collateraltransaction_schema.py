from django.db import migrations


TABLE_NAME = "sharing_management_collateraltransaction"


COLUMN_DEFINITIONS = {
    "transaction_id": "varchar(128) NOT NULL DEFAULT ''",
    "brand_campaign_id": "varchar(64) NOT NULL DEFAULT ''",
    "field_rep_id": "varchar(64) NOT NULL DEFAULT ''",
    "field_rep_unique_id": "varchar(64) NULL",
    "doctor_name": "varchar(255) NULL",
    "doctor_number": "varchar(15) NOT NULL DEFAULT ''",
    "doctor_unique_id": "varchar(64) NULL",
    "collateral_id": "bigint NOT NULL DEFAULT 0",
    "transaction_date": "date NULL",
    "has_viewed": "bool NOT NULL DEFAULT 0",
    "has_downloaded_pdf": "bool NOT NULL DEFAULT 0",
    "has_viewed_last_page": "bool NOT NULL DEFAULT 0",
    "video_view_lt_50": "bool NOT NULL DEFAULT 0",
    "video_view_gt_50": "bool NOT NULL DEFAULT 0",
    "video_view_100": "bool NOT NULL DEFAULT 0",
    "total_video_events": "integer NOT NULL DEFAULT 0",
    "last_video_percentage": "smallint NOT NULL DEFAULT 0",
    "last_page_scrolled": "integer NOT NULL DEFAULT 0",
    "doctor_viewer_engagement_id": "bigint NULL",
    "share_management_engagement_id": "bigint NULL",
    "video_tracking_last_event_id": "bigint NULL",
    "created_at": "datetime(6) NULL",
    "updated_at": "datetime(6) NULL",
    "sent_at": "datetime(6) NULL",
    "viewed_at": "datetime(6) NULL",
    "downloaded_pdf_at": "datetime(6) NULL",
    "viewed_last_page_at": "datetime(6) NULL",
    "video_lt_50_at": "datetime(6) NULL",
    "video_gt_50_at": "datetime(6) NULL",
    "video_100_at": "datetime(6) NULL",
    "last_video_event_at": "datetime(6) NULL",
}


def _existing_columns(connection, table_name):
    with connection.cursor() as cursor:
        table_names = connection.introspection.table_names(cursor)
        if table_name not in table_names:
            return None
        return {
            column.name
            for column in connection.introspection.get_table_description(cursor, table_name)
        }


def _execute_if_columns_exist(schema_editor, columns, sql):
    existing = _existing_columns(schema_editor.connection, TABLE_NAME)
    if existing and columns.issubset(existing):
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(sql)


def repair_collateraltransaction_schema(apps, schema_editor):
    connection = schema_editor.connection
    columns = _existing_columns(connection, TABLE_NAME)
    if columns is None:
        return

    qn = schema_editor.quote_name
    table = qn(TABLE_NAME)

    with connection.cursor() as cursor:
        for column_name, definition in COLUMN_DEFINITIONS.items():
            if column_name in columns:
                continue
            cursor.execute(
                f"ALTER TABLE {table} ADD COLUMN {qn(column_name)} {definition}"
            )
            columns.add(column_name)

    vendor = connection.vendor

    if {"transaction_date", "sent_at", "created_at"}.issubset(columns):
        today_expr = "CURRENT_DATE()" if vendor == "mysql" else "DATE('now')"
        _execute_if_columns_exist(
            schema_editor,
            {"transaction_date", "sent_at", "created_at"},
            (
                f"UPDATE {table} "
                f"SET {qn('transaction_date')} = COALESCE("
                f"DATE({qn('sent_at')}), DATE({qn('created_at')}), {today_expr}"
                f") WHERE {qn('transaction_date')} IS NULL"
            ),
        )

    if "downloaded_pdf" in columns and "has_downloaded_pdf" in columns:
        _execute_if_columns_exist(
            schema_editor,
            {"downloaded_pdf", "has_downloaded_pdf"},
            (
                f"UPDATE {table} SET {qn('has_downloaded_pdf')} = 1 "
                f"WHERE COALESCE({qn('downloaded_pdf')}, 0) <> 0"
            ),
        )

    if "pdf_completed" in columns and "has_viewed_last_page" in columns:
        _execute_if_columns_exist(
            schema_editor,
            {"pdf_completed", "has_viewed_last_page"},
            (
                f"UPDATE {table} SET {qn('has_viewed_last_page')} = 1 "
                f"WHERE COALESCE({qn('pdf_completed')}, 0) <> 0"
            ),
        )

    if "pdf_last_page" in columns and "last_page_scrolled" in columns:
        _execute_if_columns_exist(
            schema_editor,
            {"pdf_last_page", "last_page_scrolled"},
            (
                f"UPDATE {table} "
                f"SET {qn('last_page_scrolled')} = COALESCE({qn('pdf_last_page')}, 0) "
                f"WHERE COALESCE({qn('last_page_scrolled')}, 0) < COALESCE({qn('pdf_last_page')}, 0)"
            ),
        )

    if "video_watch_percentage" in columns and "last_video_percentage" in columns:
        _execute_if_columns_exist(
            schema_editor,
            {"video_watch_percentage", "last_video_percentage"},
            (
                f"UPDATE {table} "
                f"SET {qn('last_video_percentage')} = COALESCE({qn('video_watch_percentage')}, 0) "
                f"WHERE COALESCE({qn('last_video_percentage')}, 0) < COALESCE({qn('video_watch_percentage')}, 0)"
            ),
        )

    if "last_video_percentage" in columns:
        _execute_if_columns_exist(
            schema_editor,
            {"last_video_percentage", "video_view_lt_50", "video_view_gt_50", "video_view_100"},
            (
                f"UPDATE {table} SET "
                f"{qn('video_view_lt_50')} = CASE WHEN {qn('last_video_percentage')} > 0 "
                f"AND {qn('last_video_percentage')} < 50 THEN 1 ELSE {qn('video_view_lt_50')} END, "
                f"{qn('video_view_gt_50')} = CASE WHEN {qn('last_video_percentage')} >= 50 "
                f"AND {qn('last_video_percentage')} < 100 THEN 1 ELSE {qn('video_view_gt_50')} END, "
                f"{qn('video_view_100')} = CASE WHEN {qn('last_video_percentage')} >= 100 "
                f"THEN 1 ELSE {qn('video_view_100')} END"
            ),
        )

    if "video_completed" in columns and "video_view_100" in columns:
        _execute_if_columns_exist(
            schema_editor,
            {"video_completed", "video_view_100"},
            (
                f"UPDATE {table} SET {qn('video_view_100')} = 1 "
                f"WHERE COALESCE({qn('video_completed')}, 0) <> 0"
            ),
        )

    if "total_video_events" in columns and "last_video_percentage" in columns:
        _execute_if_columns_exist(
            schema_editor,
            {"total_video_events", "last_video_percentage"},
            (
                f"UPDATE {table} SET {qn('total_video_events')} = 1 "
                f"WHERE COALESCE({qn('total_video_events')}, 0) = 0 "
                f"AND COALESCE({qn('last_video_percentage')}, 0) > 0"
            ),
        )

    if {"viewed_at", "first_viewed_at", "last_viewed_at"}.issubset(columns):
        _execute_if_columns_exist(
            schema_editor,
            {"viewed_at", "first_viewed_at", "last_viewed_at"},
            (
                f"UPDATE {table} "
                f"SET {qn('viewed_at')} = COALESCE({qn('first_viewed_at')}, {qn('last_viewed_at')}) "
                f"WHERE {qn('viewed_at')} IS NULL "
                f"AND ({qn('first_viewed_at')} IS NOT NULL OR {qn('last_viewed_at')} IS NOT NULL)"
            ),
        )

    if {"downloaded_pdf_at", "last_viewed_at", "viewed_at", "updated_at", "has_downloaded_pdf"}.issubset(columns):
        _execute_if_columns_exist(
            schema_editor,
            {"downloaded_pdf_at", "last_viewed_at", "viewed_at", "updated_at", "has_downloaded_pdf"},
            (
                f"UPDATE {table} SET {qn('downloaded_pdf_at')} = "
                f"COALESCE({qn('last_viewed_at')}, {qn('viewed_at')}, {qn('updated_at')}) "
                f"WHERE {qn('downloaded_pdf_at')} IS NULL "
                f"AND COALESCE({qn('has_downloaded_pdf')}, 0) <> 0"
            ),
        )

    if {"viewed_last_page_at", "last_viewed_at", "has_viewed_last_page"}.issubset(columns):
        _execute_if_columns_exist(
            schema_editor,
            {"viewed_last_page_at", "last_viewed_at", "has_viewed_last_page"},
            (
                f"UPDATE {table} SET {qn('viewed_last_page_at')} = {qn('last_viewed_at')} "
                f"WHERE {qn('viewed_last_page_at')} IS NULL "
                f"AND COALESCE({qn('has_viewed_last_page')}, 0) <> 0 "
                f"AND {qn('last_viewed_at')} IS NOT NULL"
            ),
        )

    if {"last_video_event_at", "last_viewed_at", "viewed_at", "updated_at", "last_video_percentage"}.issubset(columns):
        _execute_if_columns_exist(
            schema_editor,
            {"last_video_event_at", "last_viewed_at", "viewed_at", "updated_at", "last_video_percentage"},
            (
                f"UPDATE {table} SET {qn('last_video_event_at')} = "
                f"COALESCE({qn('last_viewed_at')}, {qn('viewed_at')}, {qn('updated_at')}) "
                f"WHERE {qn('last_video_event_at')} IS NULL "
                f"AND COALESCE({qn('last_video_percentage')}, 0) > 0"
            ),
        )

    if {"transaction_date", "sent_at", "created_at"}.issubset(columns):
        today_expr = "CURRENT_DATE()" if vendor == "mysql" else "DATE('now')"
        _execute_if_columns_exist(
            schema_editor,
            {"transaction_date", "sent_at", "created_at"},
            (
                f"UPDATE {table} "
                f"SET {qn('transaction_date')} = COALESCE("
                f"DATE({qn('transaction_date')}), DATE({qn('sent_at')}), DATE({qn('created_at')}), {today_expr}"
                f") WHERE {qn('transaction_date')} IS NOT NULL"
            ),
        )

    if {"transaction_id", "field_rep_unique_id", "field_rep_id", "doctor_number", "collateral_id"}.issubset(columns):
        if vendor == "mysql":
            timestamp_expr = (
                f"DATE_FORMAT(COALESCE({qn('sent_at')}, {qn('created_at')}, NOW()), "
                f"'%Y%m%d%H%i%s')"
            )
            concat_expr = (
                f"LEFT(CONCAT("
                f"COALESCE(NULLIF({qn('field_rep_unique_id')}, ''), NULLIF({qn('field_rep_id')}, ''), 'unknown'), "
                f"'-', COALESCE(NULLIF({qn('doctor_number')}, ''), 'unknown'), "
                f"'-', COALESCE(CAST({qn('collateral_id')} AS CHAR), 'unknown'), "
                f"'-', {timestamp_expr}"
                f"), 128)"
            )
        else:
            timestamp_expr = (
                f"strftime('%Y%m%d%H%M%S', COALESCE({qn('sent_at')}, {qn('created_at')}, 'now'))"
            )
            concat_expr = (
                f"substr("
                f"COALESCE(NULLIF({qn('field_rep_unique_id')}, ''), NULLIF({qn('field_rep_id')}, ''), 'unknown') "
                f"|| '-' || COALESCE(NULLIF({qn('doctor_number')}, ''), 'unknown') "
                f"|| '-' || COALESCE(CAST({qn('collateral_id')} AS TEXT), 'unknown') "
                f"|| '-' || {timestamp_expr}, 1, 128)"
            )

        _execute_if_columns_exist(
            schema_editor,
            {
                "transaction_id",
                "field_rep_unique_id",
                "field_rep_id",
                "doctor_number",
                "collateral_id",
                "sent_at",
                "created_at",
            },
            (
                f"UPDATE {table} SET {qn('transaction_id')} = {concat_expr} "
                f"WHERE {qn('transaction_id')} IS NULL OR {qn('transaction_id')} = ''"
            ),
        )


class Migration(migrations.Migration):

    dependencies = [
        ("sharing_management", "0010_collateraltransaction"),
    ]

    operations = [
        migrations.RunPython(repair_collateraltransaction_schema, migrations.RunPython.noop),
    ]
