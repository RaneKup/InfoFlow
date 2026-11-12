from __future__ import annotations

import re

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from ..models import Item, Tag, item_tags

_TAG_CLEAN_RE = re.compile(r"\s+")

def normalize_tag(name: str) -> str:
    tag = (name or "").strip().lower().replace("ё", "е")
    tag = tag.lstrip("#").strip(" .,;:!?«»\"'()[]{}—-")
    tag = _TAG_CLEAN_RE.sub(" ", tag)
    return tag[:64]

def get_or_create_tag(
    db: Session,
    user_id: int,
    name: str,
    *,
    is_auto_generated: bool = False,
) -> Tag | None:
    normalized = normalize_tag(name)
    if not normalized:
        return None
    tag = db.scalar(select(Tag).where(Tag.user_id == user_id, Tag.name == normalized))
    if tag is not None:
        return tag
    tag = Tag(user_id=user_id, name=normalized, is_auto_generated=is_auto_generated)
    db.add(tag)
    db.flush()
    return tag

def apply_auto_tags(db: Session, item: Item, names: list[str], limit: int = 5) -> None:
    auto_tags = [tag for tag in item.tags if tag.is_auto_generated]
    for tag in auto_tags:
        if tag in item.tags:
            item.tags.remove(tag)

    seen: set[str] = set()
    added = 0
    for name in names:
        normalized = normalize_tag(name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tag = get_or_create_tag(db, item.user_id, normalized, is_auto_generated=True)
        if tag is None:
            continue
        if tag not in item.tags:
            item.tags.append(tag)
        added += 1
        if added >= limit:
            break

def set_manual_tags(db: Session, item: Item, names: list[str]) -> None:
    for tag in [tag for tag in item.tags if not tag.is_auto_generated]:
        item.tags.remove(tag)

    seen: set[str] = set()
    for name in names:
        normalized = normalize_tag(name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tag = get_or_create_tag(db, item.user_id, normalized, is_auto_generated=False)
        if tag is not None:

            tag.is_auto_generated = False
            if tag not in item.tags:
                item.tags.append(tag)

def set_all_tags(db: Session, item: Item, names: list[str]) -> None:
    for tag in list(item.tags):
        item.tags.remove(tag)

    seen: set[str] = set()
    for name in names:
        normalized = normalize_tag(name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tag = get_or_create_tag(db, item.user_id, normalized, is_auto_generated=False)
        if tag is not None:
            tag.is_auto_generated = False
            if tag not in item.tags:
                item.tags.append(tag)

def cleanup_orphan_tags(db: Session, user_id: int) -> int:
    linked = exists().where(item_tags.c.tag_id == Tag.id)
    orphan_tags = db.scalars(select(Tag).where(Tag.user_id == user_id, ~linked)).all()
    for tag in orphan_tags:
        db.delete(tag)
    return len(orphan_tags)
