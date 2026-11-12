from __future__ import annotations

from fastapi import APIRouter

from . import auth, items, search, stats, system, tags

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(items.router)
api_router.include_router(search.router)
api_router.include_router(tags.router)
api_router.include_router(stats.router)
api_router.include_router(system.router)

__all__ = ["api_router"]
