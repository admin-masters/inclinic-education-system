from django.db import migrations, models


def add_reminder_message_if_missing(apps, schema_editor):
    CollateralMessage = apps.get_model("collateral_management", "CollateralMessage")
    table_name = CollateralMessage._meta.db_table
    column_name = "reminder_message"

    with schema_editor.connection.cursor() as cursor:
        existing_columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)
        }

    if column_name in existing_columns:
        return

    field = models.TextField(
        blank=True,
        default="",
        help_text="Optional reminder-specific WhatsApp message. Use $collateralLinks as placeholder for the actual link.",
    )
    field.set_attributes_from_name(column_name)
    schema_editor.add_field(CollateralMessage, field)


class Migration(migrations.Migration):

    dependencies = [
        ("collateral_management", "0006_collateralmessage"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    add_reminder_message_if_missing,
                    reverse_code=migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="collateralmessage",
                    name="reminder_message",
                    field=models.TextField(
                        blank=True,
                        default="",
                        help_text="Optional reminder-specific WhatsApp message. Use $collateralLinks as placeholder for the actual link.",
                    ),
                ),
            ],
        ),
    ]
