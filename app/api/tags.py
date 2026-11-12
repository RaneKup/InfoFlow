from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Tag, User, item_tags
from ..schemas import MessageOut, TagStat

router = APIRouter(prefix="/tags", tags=["Теги"])

@router.get("", response_model=list[TagStat], summary="Теги с количеством записей")
def list_tags(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TagStat]:
    rows = db.execute(
        select(
            Tag.id,
            Tag.name,
            Tag.is_auto_generated,
            func.count(item_tags.c.item_id).label("items_count"),
        )
        .join(item_tags, Tag.id == item_tags.c.tag_id)
        .where(Tag.user_id == user.id)
        .group_by(Tag.id, Tag.name, Tag.is_auto_generated)
        .order_by(func.count(item_tags.c.item_id).desc(), Tag.name.asc())
    ).all()
    return [
        TagStat(
            id=row.id,
            name=row.name,
            is_auto_generated=bool(row.is_auto_generated),
            items_count=int(row.items_count),
        )
        for row in rows
    ]

@router.delete("/{tag_id}", response_model=MessageOut, summary="Удалить тег у всех записей")
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MessageOut:
    tag = db.scalar(select(Tag).where(Tag.id == tag_id, Tag.user_id == user.id))
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тег не найден")
    db.execute(sql_delete(item_tags).where(item_tags.c.tag_id == tag.id))
    db.delete(tag)
    db.commit()
    return MessageOut(message="Тег удалён")
