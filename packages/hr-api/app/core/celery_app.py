from __future__ import annotations
from celery import Celery
from app.core.config import settings

celery = Celery(
    "foundry_people",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
