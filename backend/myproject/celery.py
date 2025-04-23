import os, django
from celery import Celery


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

app = Celery('myproject')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# run every 6 h
from celery.schedules import crontab
app.conf.beat_schedule = {
    'etl-every-6h': {
        'task': 'reporting_etl.tasks.scheduled_etl',
        'schedule': crontab(minute=0, hour='*/6'),
    },
}