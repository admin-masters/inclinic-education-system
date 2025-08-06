from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('doctor_viewer', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='doctorengagement',
            name='status',
            field=models.IntegerField(default=0, db_index=True),
        ),
    ]
