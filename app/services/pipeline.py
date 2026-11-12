from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_session_factory
from ..models import Item, ItemChunk, User
from .ai import Analysis, analyze_content
from .chunking import clean_text, estimate_tokens, make_title_from_text, split_text
from .embeddings import EmbeddingError, HashEmbedder, get_embedder
from .ingestion import extract_file_text, fetch_web_page
from .tags import apply_auto_tags, cleanup_orphan_tags, normalize_tag, set_all_tags, set_manual_tags
from .vector_store import VectorRecord, get_vector_store

logger = logging.getLogger(__name__)

def create_item(
    db: Session,
    user: User,
    *,
    item_type: str,
    title: str | None = None,
    url: str | None = None,
    text: str | None = None,
    file_path: str | None = None,
    file_name: str | None = None,
    file_size: int | None = None,
    mime_type: str | None = None,
    manual_tags: list[str] | None = None,
) -> Item:
    item = Item(
        user_id=user.id,
        type=item_type,
        title=(title or "").strip()[:512],
        original_url=url,
        content_text=clean_text(text or ""),
        summary="",
        status="pending",
        file_path=file_path,
        file_name=file_name,
        file_size=file_size,
        mime_type=mime_type,
    )
    db.add(item)
    db.flush()
    if manual_tags:
        set_manual_tags(db, item, manual_tags)
    db.commit()
    db.refresh(item)
    return item

def _prepare_content(item: Item) -> Analysis:
    settings = get_settings()
    text = item.content_text or ""
    title = (item.title or "").strip()

    if item.type == "link" and item.original_url and not text.strip():
        page = fetch_web_page(item.original_url)
        text = page.text
        title = title or page.title
        if page.final_url:
            item.original_url = page.final_url
    elif item.type == "file" and item.file_path and not text.strip():
        text = extract_file_text(item.file_path, item.mime_type, item.file_name)

    text = clean_text(text)[: settings.max_content_chars]
    if not text and not title:
        raise ValueError("Не удалось извлечь текст из материала")

    analysis = analyze_content(title=title, text=text, item_type=item.type)
    if not title:
        title = analysis.title or make_title_from_text(text)
    item.title = (title or "Без названия").strip()[:500]
    item.summary = (analysis.summary or "").strip()[:4000]
    item.content_text = text
    item.error_message = None

    logger.info(
        "AI-обработка item=%s: provider=%s, теги=%s",
        item.id,
        analysis.provider,
        analysis.tags,
    )
    return analysis

def _vectorize(db: Session, item: Item) -> None:
    settings = get_settings()
    source = item.content_text or f"{item.title}. {item.summary}"
    chunks = split_text(
        source,
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
        max_chunks=settings.max_chunks_per_item,
    )
    if not chunks:
        chunks = [(item.summary or item.title or "Без содержимого").strip()]

    store = get_vector_store()
    store.delete_by_item(item.user_id, item.id)

    for old_chunk in list(item.chunks):
        db.delete(old_chunk)
    db.flush()

    chunk_objects: list[ItemChunk] = []
    for index, content in enumerate(chunks):
        vector_id = f"item-{item.id}-chunk-{index}"
        chunk = ItemChunk(
            item_id=item.id,
            chunk_index=index,
            content=content,
            vector_id=vector_id,
            token_count=estimate_tokens(content),
        )
        db.add(chunk)
        chunk_objects.append(chunk)
    db.flush()

    try:
        embedder = get_embedder()
        try:
            vectors = embedder.embed_documents([chunk.content for chunk in chunk_objects])
        except EmbeddingError as exc:
            logger.warning("Провайдер эмбеддингов недоступен, использую hash-фолбэк: %s", exc)
            vectors = HashEmbedder(settings.embedding_dim).embed_documents(
                [chunk.content for chunk in chunk_objects]
            )
        records = [
            VectorRecord(
                vector_id=chunk.vector_id,
                item_id=item.id,
                chunk_id=chunk.id,
                text=chunk.content,
                vector=vector,
            )
            for chunk, vector in zip(chunk_objects, vectors)
        ]
        store.upsert(item.user_id, records)
    except Exception as exc:
        logger.exception("Не удалось сохранить эмбеддинги item=%s: %s", item.id, exc)

def _run_pipeline(db: Session, item: Item) -> None:
    analysis = _prepare_content(item)
    apply_auto_tags(db, item, analysis.tags)
    db.flush()

    _vectorize(db, item)
    item.status = "ready"
    db.flush()

def process_item(item_id: int) -> None:
    db = get_session_factory()()
    try:
        item = db.get(Item, item_id)
        if item is None:
            logger.warning("Запись %s не найдена", item_id)
            return
        item.status = "processing"
        item.error_message = None
        db.commit()

        _run_pipeline(db, item)
        db.commit()
        logger.info("Запись %s готова", item_id)
    except Exception as exc:
        db.rollback()
        logger.exception("Ошибка обработки записи %s", item_id)
        item = db.get(Item, item_id)
        if item is not None:
            item.status = "failed"
            item.error_message = str(exc)[:1000]
            db.commit()
    finally:
        db.close()

def delete_item(db: Session, item: Item) -> None:
    settings = get_settings()
    try:
        get_vector_store().delete_by_item(item.user_id, item.id)
    except Exception as exc:
        logger.warning("Не удалось удалить векторы item=%s: %s", item.id, exc)

    if item.file_path:
        file_path = Path(item.file_path)
        try:
            if file_path.is_file() and file_path.resolve().is_relative_to(
                Path(settings.upload_dir).resolve()
            ):
                file_path.unlink()
        except (OSError, ValueError) as exc:
            logger.warning("Не удалось удалить файл %s: %s", file_path, exc)

    user_id = item.user_id
    db.delete(item)
    db.commit()
    cleanup_orphan_tags(db, user_id)
    db.commit()

def mark_pending(db: Session, item: Item) -> None:
    item.status = "pending"
    item.error_message = None
    db.commit()

def update_manual_tags(db: Session, item: Item, tags: list[str]) -> None:
    set_manual_tags(db, item, tags)

    db.flush()
    cleanup_orphan_tags(db, item.user_id)
    db.commit()
    db.refresh(item)

def update_all_tags(db: Session, item: Item, tags: list[str]) -> None:
    set_all_tags(db, item, tags)
    db.flush()
    cleanup_orphan_tags(db, item.user_id)
    db.commit()
    db.refresh(item)

__all__ = [
    "create_item",
    "process_item",
    "delete_item",
    "mark_pending",
    "update_manual_tags",
    "update_all_tags",
    "normalize_tag",
]
