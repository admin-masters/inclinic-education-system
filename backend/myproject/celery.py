import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

app = Celery('myproject')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Run every 6 hours
app.conf.beat_schedule = {
    'etl-every-6h': {
        'task': 'reporting_etl.tasks.scheduled_etl',
        'schedule': crontab(minute=0, hour='*/6'),
    },
}
