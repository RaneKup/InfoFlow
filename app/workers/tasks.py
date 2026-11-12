from __future__ import annotations

from .celery_app import celery_app
from ..services.pipeline import process_item

@celery_app.task(name="infoflow.process_item")
def process_item_task(item_id: int) -> str:
    process_item(item_id)
    return f"item:{item_id}:processed"
