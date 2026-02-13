# reporting_etl/models.py
from django.db import models
from django.utils import timezone

class EtlState(models.Model):
    """
    Stores timestamp of last ETL run for each model.
    """
    model_name   = models.CharField(max_length=100, unique=True)
    last_synced  = models.DateTimeField(default=timezone.make_aware(timezone.datetime.min))

    class Meta:
        app_label = 'reporting_etl'

    def __str__(self):
        return f"{self.model_name} @ {self.last_synced:%Y-%m-%d %H:%M}"