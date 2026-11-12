from __future__ import annotations

import importlib.util
import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..schemas import HealthOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Служебные"])

def health_payload(db: Session) -> HealthOut:
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:
        logger.warning("Database health-check failed: %s", exc)
        database = "error"

    embedding_provider = settings.embedding_provider
    if embedding_provider == "auto":
        embedding_provider = (
            "sentence-transformers"
            if importlib.util.find_spec("sentence_transformers") is not None
            else "hash"
        )
    vector_backend = settings.vector_backend
    if vector_backend == "auto":
        vector_backend = (
            "chroma" if importlib.util.find_spec("chromadb") is not None else "local"
        )

    return HealthOut(
        status="ok" if database == "ok" else "degraded",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        database=database,
        ai_provider=settings.effective_ai_provider,
        embedding_provider=embedding_provider,
        vector_backend=vector_backend,
    )

@router.get("/health", response_model=HealthOut, summary="Проверка работоспособности")
def health(db: Session = Depends(get_db)) -> HealthOut:
    return health_payload(db)
