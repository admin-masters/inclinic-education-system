import uuid
from django.db import migrations, models

def fill_uids(apps, schema_editor):
    FRC = apps.get_model("admin_dashboard", "FieldRepCampaign")
    for row in FRC.objects.filter(uid__isnull=True):
        row.uid = uuid.uuid4()
        row.save(update_fields=["uid"])

class Migration(migrations.Migration):

    dependencies = [("admin_dashboard", "0001_initial")]

    operations = [
        # 1️⃣ add nullable / non-unique field first
        migrations.AddField(
            model_name="fieldrepcampaign",
            name="uid",
            field=models.UUIDField(null=True, editable=False),
        ),
        # 2️⃣ fill the column
        migrations.RunPython(fill_uids, migrations.RunPython.noop),
        # 3️⃣ now enforce NOT NULL + UNIQUE
        migrations.AlterField(
            model_name="fieldrepcampaign",
            name="uid",
            field=models.UUIDField(
                null=False,
                unique=True,
                editable=False,
                default=uuid.uuid4,
            ),
        ),
    ]
