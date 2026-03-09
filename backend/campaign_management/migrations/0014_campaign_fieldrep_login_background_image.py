from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("campaign_management", "0013_remove_campaignassignment_campaign_ma_campaig_c8c8cc_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="campaign",
            name="fieldrep_login_background_image",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="campaigns/fieldrep/backgrounds/",
            ),
        ),
    ]
