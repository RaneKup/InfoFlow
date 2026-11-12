from __future__ import annotations

import uvicorn

from app.config import get_settings

settings = get_settings()
uvicorn.run(
    "app.main:app",
    host="127.0.0.1",
    port=8000,
    reload=settings.debug,
)
