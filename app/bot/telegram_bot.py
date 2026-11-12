from __future__ import annotations

import asyncio
import logging
import secrets
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from ..config import ensure_directories, get_settings
from ..database import get_session_factory, init_db
from ..models import Item, User
from ..security import hash_password, verify_password
from ..services.pipeline import create_item, process_item
from ..services.search import search_items

logger = logging.getLogger(__name__)

_HELP = (
    "InfoFlow AI — ваша личная база знаний.\n\n"
    "Команды:\n"
    "/save <текст или ссылка> — сохранить\n"
    "/search <запрос> — найти по смыслу\n"
    "/recent — последние записи\n"
    "/link <email> <пароль> — привязать веб-аккаунт\n"
    "/help — эта справка\n\n"
    "Можно просто отправить текст, ссылку, PDF или голосовое сообщение — "
    "я сохраню и обработаю материал."
)

def _get_or_create_user(telegram_id: int) -> User:
    settings = get_settings()
    db = get_session_factory()()
    try:
        user = db.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is not None:
            return user
        if not settings.telegram_auto_provision:
            raise PermissionError(
                "Аккаунт не привязан. Выполните /link <email> <пароль>."
            )
        email = f"tg{telegram_id}@telegram.infoflow.app"
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(secrets.token_urlsafe(32)),
                telegram_id=telegram_id,
            )
            db.add(user)
        else:
            user.telegram_id = telegram_id
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()

def _link_account(telegram_id: int, email: str, password: str) -> str:
    db = get_session_factory()()
    try:
        user = db.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None or not verify_password(password, user.password_hash):
            raise PermissionError("Неверный email или пароль")
        if user.telegram_id not in (None, telegram_id):
            other = db.scalar(select(User).where(User.telegram_id == telegram_id))
            if other is not None:
                other.telegram_id = None
                db.commit()
        user.telegram_id = telegram_id
        db.commit()
        return user.email
    finally:
        db.close()

def _save_text(user_id: int, text: str, url: str | None = None) -> dict[str, Any]:
    db = get_session_factory()()
    try:
        user = db.get(User, user_id)
        if user is None:
            return {"ok": False, "error": "Пользователь не найден"}
        item = create_item(
            db,
            user,
            item_type="link" if url else "note",
            text=None if url else text,
            url=url,
            title=None,
        )
        item_id = item.id
    finally:
        db.close()

    process_item(item_id)

    db = get_session_factory()()
    try:
        item = db.get(Item, item_id)
        if item is None:
            return {"ok": False, "error": "Запись не найдена"}
        return {
            "ok": item.status == "ready",
            "id": item.id,
            "title": item.title,
            "summary": item.summary,
            "tags": [tag.name for tag in item.tags],
            "status": item.status,
            "error": item.error_message,
        }
    finally:
        db.close()

def _save_file(user_id: int, path: str, filename: str, mime_type: str | None) -> dict[str, Any]:
    db = get_session_factory()()
    try:
        user = db.get(User, user_id)
        if user is None:
            return {"ok": False, "error": "Пользователь не найден"}
        file_size = Path(path).stat().st_size if Path(path).is_file() else None
        item = create_item(
            db,
            user,
            item_type="file",
            file_path=path,
            file_name=filename,
            file_size=file_size,
            mime_type=mime_type,
        )
        item_id = item.id
    finally:
        db.close()

    process_item(item_id)

    db = get_session_factory()()
    try:
        item = db.get(Item, item_id)
        if item is None:
            return {"ok": False, "error": "Запись не найдена"}
        return {
            "ok": item.status == "ready",
            "id": item.id,
            "title": item.title,
            "summary": item.summary,
            "tags": [tag.name for tag in item.tags],
            "status": item.status,
            "error": item.error_message,
        }
    finally:
        db.close()

def _search(user_id: int, query: str, limit: int = 5) -> list[dict[str, Any]]:
    db = get_session_factory()()
    try:
        hits = search_items(db, user_id, query, mode="hybrid", limit=limit)
        if not hits:
            return []
        items = db.scalars(
            select(Item).where(Item.user_id == user_id, Item.id.in_([hit.item_id for hit in hits]))
        ).all()
        items_by_id = {item.id: item for item in items}
        results: list[dict[str, Any]] = []
        for hit in hits:
            item = items_by_id.get(hit.item_id)
            if item is None:
                continue
            results.append(
                {
                    "id": item.id,
                    "title": item.title,
                    "summary": item.summary,
                    "url": item.original_url,
                    "score": hit.score,
                    "type": item.type,
                }
            )
        return results
    finally:
        db.close()

def _recent(user_id: int, limit: int = 5) -> list[dict[str, Any]]:
    db = get_session_factory()()
    try:
        items = db.scalars(
            select(Item)
            .where(Item.user_id == user_id)
            .order_by(Item.created_at.desc())
            .limit(limit)
        ).all()
        return [
            {
                "id": item.id,
                "title": item.title,
                "summary": item.summary,
                "type": item.type,
                "status": item.status,
            }
            for item in items
        ]
    finally:
        db.close()

def _format_saved(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        error = result.get("error") or "неизвестная ошибка"
        return f"⚠️ Сохранено, но обработка не удалась: {error}\nЗапись #{result.get('id')}"
    summary = (result.get("summary") or "").strip()
    if len(summary) > 700:
        summary = summary[:697] + "…"
    tags = result.get("tags") or []
    tag_line = f"\n🏷 {', '.join(tags)}" if tags else ""
    return f"✅ Сохранено: {result.get('title')}\n\n{summary}{tag_line}"

def _format_search(results: list[dict[str, Any]]) -> str:
    if not results:
        return "Ничего не найдено. Попробуйте сформулировать запрос иначе."
    lines = ["🔎 Найденное:"]
    for index, result in enumerate(results, start=1):
        summary = (result.get("summary") or "").strip()
        if len(summary) > 240:
            summary = summary[:237] + "…"
        lines.append(f"{index}. {result.get('title')}\n{summary}")
    return "\n\n".join(lines)

def run_bot() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN не задан. Добавьте токен в .env и повторите запуск."
        )
    try:
        from telegram import Update
        from telegram.ext import (
            Application,
            CommandHandler,
            ContextTypes,
            MessageHandler,
            filters,
        )
    except ImportError as exc:
        raise SystemExit(
            "Установите python-telegram-bot: pip install python-telegram-bot"
        ) from exc

    ensure_directories(settings)
    if settings.auto_create_tables:
        init_db()

    async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(
            "Привет! Я InfoFlow AI.\n\n" + _HELP
        )

    async def help_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(_HELP)

    async def link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or []
        if len(args) < 2:
            await update.effective_message.reply_text(
                "Использование: /link email@example.com ваш_пароль"
            )
            return
        telegram_id = update.effective_user.id
        try:
            email = await asyncio.to_thread(_link_account, telegram_id, args[0], args[1])
        except PermissionError as exc:
            await update.effective_message.reply_text(f"⚠️ {exc}")
            return
        await update.effective_message.reply_text(
            f"✅ Аккаунт {email} привязан. Теперь веб-интерфейс и бот используют одну базу."
        )

    async def save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        text = " ".join(context.args or []).strip()
        if not text and message.reply_to_message and message.reply_to_message.text:
            text = message.reply_to_message.text
        if not text:
            await message.reply_text("Использование: /save <текст или ссылка>")
            return
        user = _get_or_create_user(update.effective_user.id)
        await message.reply_text("⏳ Сохраняю и обрабатываю…")
        is_url = text.startswith(("http://", "https://"))
        result = await asyncio.to_thread(
            _save_text,
            user.id,
            text,
            text if is_url else None,
        )
        await message.reply_text(_format_saved(result))

    async def on_text(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        text = (message.text or "").strip()
        if not text:
            return
        user = _get_or_create_user(update.effective_user.id)
        await message.reply_text("⏳ Сохраняю и обрабатываю…")
        is_url = text.startswith(("http://", "https://"))
        result = await asyncio.to_thread(
            _save_text,
            user.id,
            text,
            text if is_url else None,
        )
        await message.reply_text(_format_saved(result))

    async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from ..services.ai import transcribe_audio

        message = update.effective_message
        media = message.voice or message.audio
        if media is None:
            return
        user = _get_or_create_user(update.effective_user.id)
        temp_dir = Path(settings.data_dir) / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        path = temp_dir / f"voice_{uuid4().hex}.ogg"
        try:
            tg_file = await context.bot.get_file(media.file_id)
            await tg_file.download_to_drive(custom_path=str(path))
            await message.reply_text("⏳ Расшифровываю голосовое сообщение…")
            text = await asyncio.to_thread(transcribe_audio, path)
            result = await asyncio.to_thread(_save_text, user.id, text, None)
            await message.reply_text(f"🗣 {text[:300]}\n\n" + _format_saved(result))
        except Exception as exc:
            await message.reply_text(f"⚠️ Не удалось обработать аудио: {exc}")
        finally:
            path.unlink(missing_ok=True)

    async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        document = message.document
        if document is None:
            return
        user = _get_or_create_user(update.effective_user.id)
        filename = Path(document.file_name or "document.pdf").name
        target = Path(settings.upload_dir) / f"{uuid4().hex}{Path(filename).suffix[:16]}"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            await message.reply_text("⏳ Загружаю и обрабатываю файл…")
            tg_file = await context.bot.get_file(document.file_id)
            await tg_file.download_to_drive(custom_path=str(target))
            result = await asyncio.to_thread(
                _save_file,
                user.id,
                str(target),
                filename,
                document.mime_type,
            )
            await message.reply_text(_format_saved(result))
        except Exception as exc:
            target.unlink(missing_ok=True)
            await message.reply_text(f"⚠️ Не удалось обработать файл: {exc}")

    async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = " ".join(context.args or []).strip()
        if not query:
            await update.effective_message.reply_text("Использование: /search <запрос>")
            return
        user = _get_or_create_user(update.effective_user.id)
        results = await asyncio.to_thread(_search, user.id, query)
        await update.effective_message.reply_text(_format_search(results))

    async def recent(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        user = _get_or_create_user(update.effective_user.id)
        items = await asyncio.to_thread(_recent, user.id)
        if not items:
            await update.effective_message.reply_text("Пока ничего не сохранено.")
            return
        lines = ["🕘 Последние записи:"]
        for item in items:
            icon = {"link": "🔗", "note": "📝", "file": "📄"}.get(item["type"], "•")
            lines.append(f"{icon} #{item['id']} — {item['title']} ({item['status']})")
        lines.append("\nПодробнее — в веб-интерфейсе.")
        await update.effective_message.reply_text("\n".join(lines))

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.exception("Ошибка Telegram-бота", exc_info=context.error)

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("link", link))
    application.add_handler(CommandHandler("save", save))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("recent", recent))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, on_voice))
    application.add_handler(MessageHandler(filters.Document.ALL, on_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    application.add_error_handler(error_handler)

    logger.info("Telegram-бот запущен")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_bot()
