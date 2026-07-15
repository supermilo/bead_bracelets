import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bracelet_builder.settings')

app = Celery('bracelet_builder')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
