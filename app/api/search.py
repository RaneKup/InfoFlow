from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import get_current_user
from ..models import Item, User
from ..schemas import (
    ItemListItem,
    ItemType,
    SearchMode,
    SearchResponse,
    SearchResultOut,
)
from ..services.search import search_items

router = APIRouter(prefix="/search", tags=["Поиск"])

@router.get("", response_model=SearchResponse, summary="Поиск: hybrid / keyword / semantic")
def search(
    q: str = Query(..., min_length=1, max_length=500, description="Поисковый запрос"),
    mode: SearchMode = Query("hybrid"),
    limit: int = Query(20, ge=1, le=50),
    item_type: ItemType | None = Query(None, alias="type"),
    tag: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SearchResponse:
    started = time.perf_counter()
    hits = search_items(
        db,
        user.id,
        q,
        mode=mode,
        limit=limit,
        item_type=item_type,
        tag=tag,
    )

    items_by_id: dict[int, Item] = {}
    if hits:
        items = db.scalars(
            select(Item)
            .where(Item.user_id == user.id, Item.id.in_([hit.item_id for hit in hits]))
            .options(selectinload(Item.tags))
        ).all()
        items_by_id = {item.id: item for item in items}

    results: list[SearchResultOut] = []
    for hit in hits:
        item = items_by_id.get(hit.item_id)
        if item is None:
            continue
        base = ItemListItem.model_validate(item).model_dump()
        results.append(
            SearchResultOut(
                **base,
                score=hit.score,
                snippet=hit.snippet,
                match=hit.match,
            )
        )

    took_ms = int((time.perf_counter() - started) * 1000)
    return SearchResponse(
        query=q,
        mode=mode,
        total=len(results),
        took_ms=took_ms,
        results=results,
    )
