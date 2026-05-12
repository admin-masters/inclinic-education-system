from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("collateral_management", "0006_collateralmessage"),
    ]

    operations = [
        migrations.AddField(
            model_name="collateralmessage",
            name="reminder_message",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Optional reminder-specific WhatsApp message. Use $collateralLinks as placeholder for the actual link.",
            ),
        ),
    ]
