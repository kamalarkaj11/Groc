import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grocery_store.settings')

app = Celery('grocery_store')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()