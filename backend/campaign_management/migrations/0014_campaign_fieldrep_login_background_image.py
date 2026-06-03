from django.db import migrations, models


def add_fieldrep_login_background_image_if_missing(apps, schema_editor):
    Campaign = apps.get_model("campaign_management", "Campaign")
    table_name = Campaign._meta.db_table
    column_name = "fieldrep_login_background_image"

    with schema_editor.connection.cursor() as cursor:
        existing_columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)
        }

    if column_name in existing_columns:
        return

    field = models.ImageField(
        blank=True,
        null=True,
        upload_to="campaigns/fieldrep/backgrounds/",
    )
    field.set_attributes_from_name(column_name)
    schema_editor.add_field(Campaign, field)


class Migration(migrations.Migration):

    dependencies = [
        ("campaign_management", "0013_remove_campaignassignment_campaign_ma_campaig_c8c8cc_idx"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    add_fieldrep_login_background_image_if_missing,
                    reverse_code=migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="campaign",
                    name="fieldrep_login_background_image",
                    field=models.ImageField(
                        blank=True,
                        null=True,
                        upload_to="campaigns/fieldrep/backgrounds/",
                    ),
                ),
            ],
        ),
    ]
