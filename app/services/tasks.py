from __future__ import annotations

import logging

from fastapi import BackgroundTasks

from ..config import get_settings
from .pipeline import process_item

logger = logging.getLogger(__name__)

def enqueue_processing(item_id: int, background_tasks: BackgroundTasks | None = None) -> None:
    settings = get_settings()
    if settings.use_celery:
        try:
            from ..workers.tasks import process_item_task

            process_item_task.delay(item_id)
            logger.info("Задача обработки item=%s отправлена в Celery", item_id)
            return
        except Exception as exc:
            logger.warning(
                "Celery недоступен (%s). Обрабатываю запись в фоне процесса.", exc
            )
    if background_tasks is not None:
        background_tasks.add_task(process_item, item_id)
        return
    process_item(item_id)
