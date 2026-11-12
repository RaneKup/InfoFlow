from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Item, Tag, User
from ..schemas import (
    ItemCreate,
    ItemListItem,
    ItemListOut,
    ItemOut,
    ItemType,
    ItemUpdate,
)
from ..services.pipeline import (
    create_item,
    delete_item,
    mark_pending,
    update_all_tags,
    update_manual_tags,
)
from ..services.tags import normalize_tag
from ..services.tasks import enqueue_processing

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/items", tags=["Записи"])

def _get_owned_item(db: Session, item_id: int, user: User) -> Item:
    item = db.scalar(
        select(Item)
        .where(Item.id == item_id, Item.user_id == user.id)
        .options(selectinload(Item.tags), selectinload(Item.chunks))
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")
    return item

def _parse_form_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [normalize_tag(part) for part in raw.replace(";", ",").split(",") if normalize_tag(part)]

@router.post(
    "",
    response_model=ItemOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Сохранить ссылку или заметку",
)
def create_new_item(
    payload: ItemCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Item:
    item = create_item(
        db,
        user,
        item_type=payload.type,
        title=payload.title,
        url=payload.url.strip() if payload.url else None,
        text=payload.text,
        manual_tags=payload.tags,
    )
    enqueue_processing(item.id, background_tasks)
    return item

@router.get("", response_model=ItemListOut, summary="Список записей")
def list_items(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    item_type: ItemType | None = Query(None, alias="type"),
    status_filter: str | None = Query(None, alias="status"),
    tag: str | None = Query(None),
    q: str | None = Query(None, max_length=300),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ItemListOut:
    filters = [Item.user_id == user.id]
    if item_type:
        filters.append(Item.type == item_type)
    if status_filter:
        filters.append(Item.status == status_filter)
    if tag:
        filters.append(Item.tags.any(Tag.name == normalize_tag(tag)))
    if q and q.strip():
        like = f"%{q.strip()}%"
        filters.append(
            or_(
                Item.title.ilike(like),
                Item.summary.ilike(like),
                Item.content_text.ilike(like),
            )
        )

    total = db.scalar(select(func.count(Item.id)).where(*filters)) or 0
    items = list(
        db.scalars(
            select(Item)
            .where(*filters)
            .options(selectinload(Item.tags))
            .order_by(Item.created_at.desc(), Item.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return ItemListOut(
        items=[ItemListItem.model_validate(item) for item in items],
        total=int(total),
        limit=limit,
        offset=offset,
    )

@router.post(
    "/upload",
    response_model=ItemOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Загрузить файл (PDF, TXT, MD…)",
)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    tags: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Item:
    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    original_name = Path(file.filename or "file").name
    suffix = Path(original_name).suffix[:16]
    target = Path(settings.upload_dir) / f"{uuid4().hex}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    try:
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Файл больше {settings.max_upload_mb} МБ",
                    )
                output.write(chunk)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    except OSError as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Не удалось сохранить файл") from exc
    finally:
        await file.close()

    if total == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Файл пустой")

    try:
        item = create_item(
            db,
            user,
            item_type="file",
            title=title,
            file_path=str(target),
            file_name=original_name,
            file_size=total,
            mime_type=file.content_type,
            manual_tags=_parse_form_tags(tags),
        )
    except Exception:
        target.unlink(missing_ok=True)
        raise
    enqueue_processing(item.id, background_tasks)
    return item

@router.get("/{item_id}", response_model=ItemOut, summary="Запись целиком")
def get_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Item:
    return _get_owned_item(db, item_id, user)

@router.patch("/{item_id}", response_model=ItemOut, summary="Изменить заголовок, резюме, теги")
def update_item(
    item_id: int,
    payload: ItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Item:
    item = _get_owned_item(db, item_id, user)
    if payload.title is not None:
        item.title = payload.title.strip()[:512] or "Без названия"
    if payload.summary is not None:
        item.summary = payload.summary.strip()[:4000]
    if payload.tags is not None:
        if payload.replace_tags:
            update_all_tags(db, item, payload.tags)
        else:
            update_manual_tags(db, item, payload.tags)
    else:
        db.commit()
        db.refresh(item)
    return item

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить запись")
def remove_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    item = _get_owned_item(db, item_id, user)
    delete_item(db, item)

@router.post(
    "/{item_id}/reprocess",
    response_model=ItemOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Перезапустить AI-обработку",
)
def reprocess_item(
    item_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Item:
    item = _get_owned_item(db, item_id, user)
    mark_pending(db, item)
    enqueue_processing(item.id, background_tasks)
    return item

@router.get("/{item_id}/download", summary="Скачать исходный файл")
def download_file(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    item = _get_owned_item(db, item_id, user)
    if not item.file_path:
        raise HTTPException(status_code=404, detail="У записи нет файла")
    path = Path(item.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден на диске")
    return FileResponse(
        path,
        media_type=item.mime_type or "application/octet-stream",
        filename=item.file_name or path.name,
    )
