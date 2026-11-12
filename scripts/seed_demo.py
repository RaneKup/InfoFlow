from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import select

from app.config import ensure_directories, get_settings
from app.database import get_session_factory, init_db
from app.models import User
from app.security import hash_password
from app.services.pipeline import create_item, process_item

DEMO_EMAIL = "demo@infoflow.ru"
DEMO_PASSWORD = "demo12345"

DEMO_ITEMS = [
    {
        "title": "JWT-аутентификация в FastAPI",
        "text": (
            "JWT-аутентификация строится на двух токенах: access-токен живёт 15 минут "
            "и передаётся в заголовке Authorization, refresh-токен хранится в защищённой "
            "cookie и позволяет выпустить новую пару. Секретный ключ нельзя держать в коде — "
            "только в переменных окружения. Дополнительно ограничивайте срок жизни токена, "
            "проверяйте подпись и используйте HTTPS. Для защиты от кражи refresh-токена "
            "применяйте ротацию и привязку к устройству."
        ),
        "tags": ["jwt", "fastapi", "безопасность"],
    },
    {
        "title": "Идея: автоматический дайджест сохранённых ссылок",
        "text": (
            "Идея для InfoFlow: раз в неделю собирать сохранённые за неделю материалы, "
            "группировать их по темам и присылать краткий дайджест в Telegram. "
            "Можно добавить кнопку «вернуться к этому позже» и напоминания по необработанным "
            "заметкам. Ценность — человек не теряет контекст и видит, что уже изучил."
        ),
        "tags": ["идея", "telegram", "продукт"],
    },
    {
        "title": "PostgreSQL: индексы и EXPLAIN ANALYZE",
        "text": (
            "Индекс B-tree ускоряет поиск по равенству и диапазону, но замедляет вставку. "
            "Составной индекс работает слева направо: (user_id, created_at) поможет фильтру "
            "по пользователю и сортировке по дате. EXPLAIN ANALYZE показывает реальное время "
            "выполнения и число строк, а не только оценку планировщика. Следите за seq scan "
            "на больших таблицах и не создавайте индексы «на всякий случай»."
        ),
        "tags": ["postgresql", "sql", "производительность"],
    },
    {
        "title": "Гибридный поиск и Reciprocal Rank Fusion",
        "text": (
            "BM25 хорошо ловит точные совпадения: имена файлов, артикулы, термины. "
            "Векторный поиск находит близкие по смыслу записи, даже если слова запроса "
            "не встречаются в тексте. Reciprocal Rank Fusion объединяет два ранжированных "
            "списка без подбора весов: score = Σ 1 / (k + rank), обычно k = 60. "
            "Подход устойчив к разной шкале оценок BM25 и косинусного сходства."
        ),
        "tags": ["поиск", "rrf", "bm25", "embeddings"],
    },
]

def main() -> None:
    settings = get_settings()
    ensure_directories(settings)
    init_db()

    db = get_session_factory()()
    try:
        user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
        if user is None:
            user = User(email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD))
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"Создан пользователь {DEMO_EMAIL} / {DEMO_PASSWORD}")
        else:
            print(f"Пользователь {DEMO_EMAIL} уже существует")

        existing = {
            item.title
            for item in user.items
        } if user.items else set()
        created = 0
        for payload in DEMO_ITEMS:
            if payload["title"] in existing:
                continue
            item = create_item(
                db,
                user,
                item_type="note",
                title=payload["title"],
                text=payload["text"],
                manual_tags=payload["tags"],
            )
            process_item(item.id)
            created += 1
        db.refresh(user)
        print(f"Добавлено записей: {created}. Всего: {len(user.items)}")
        print("Веб-интерфейс: http://localhost:8000")
        print(f"Логин: {DEMO_EMAIL} · Пароль: {DEMO_PASSWORD}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
