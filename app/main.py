from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .api.router import api_router
from .api.system import health_payload
from .config import ensure_directories, get_settings
from .database import get_db, init_db
from .schemas import HealthOut

logging.basicConfig(
    level=logging.DEBUG if get_settings().debug else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()
STATIC_DIR = Path(__file__).resolve().parent / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_directories(settings)
    if settings.auto_create_tables:
        init_db()
        logger.info("Таблицы базы данных проверены/созданы")
    logger.info(
        "%s %s запущен | AI: %s | embeddings: %s | vector: %s",
        settings.app_name,
        settings.app_version,
        settings.effective_ai_provider,
        settings.embedding_provider,
        settings.vector_backend,
    )
    yield
    logger.info("%s остановлен", settings.app_name)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Единая база знаний: сохранение ссылок, заметок и файлов, "
        "автоматическое резюме и теги, гибридный поиск по смыслу и ключевым словам."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

cors_origins = settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/favicon.svg", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")

@app.get("/health", response_model=HealthOut, include_in_schema=False)
def root_health(db: Session = Depends(get_db)) -> HealthOut:
    return health_payload(db)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
