from celery import shared_task
from django.core.management import call_command

@shared_task
def scheduled_etl():
    call_command('run_etl')