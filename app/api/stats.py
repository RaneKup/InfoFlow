from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Item, Tag, User
from ..schemas import StatsOut

router = APIRouter(tags=["Статистика"])

@router.get("/stats", response_model=StatsOut, summary="Сводка по библиотеке")
def stats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StatsOut:
    total = db.scalar(select(func.count(Item.id)).where(Item.user_id == user.id)) or 0

    by_type_rows = db.execute(
        select(Item.type, func.count(Item.id))
        .where(Item.user_id == user.id)
        .group_by(Item.type)
    ).all()
    by_status_rows = db.execute(
        select(Item.status, func.count(Item.id))
        .where(Item.user_id == user.id)
        .group_by(Item.status)
    ).all()
    tags_count = (
        db.scalar(select(func.count(Tag.id)).where(Tag.user_id == user.id)) or 0
    )
    last_saved = db.scalar(
        select(func.max(Item.created_at)).where(Item.user_id == user.id)
    )

    return StatsOut(
        total_items=int(total),
        by_type={row[0]: int(row[1]) for row in by_type_rows},
        by_status={row[0]: int(row[1]) for row in by_status_rows},
        tags_count=int(tags_count),
        last_saved_at=last_saved,
    )
