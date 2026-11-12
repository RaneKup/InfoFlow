from __future__ import annotations

import importlib.util
import logging
import math
import sqlite3
import struct
import threading
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class VectorRecord:
    vector_id: str
    item_id: int
    chunk_id: int | None
    text: str
    vector: list[float]

@dataclass(slots=True)
class VectorHit:
    vector_id: str
    item_id: int
    chunk_id: int | None
    score: float
    text: str

class BaseVectorStore:
    name: str = "base"

    def upsert(self, user_id: int, records: list[VectorRecord]) -> None:
        raise NotImplementedError

    def delete_by_item(self, user_id: int, item_id: int) -> None:
        raise NotImplementedError

    def query(self, user_id: int, vector: list[float], top_k: int = 20) -> list[VectorHit]:
        raise NotImplementedError

    def count(self, user_id: int | None = None) -> int:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError

def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

def _pack(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)

def _unpack(blob: bytes) -> list[float]:
    if not blob:
        return []
    return list(struct.unpack(f"{len(blob) // 4}f", blob))

class LocalVectorStore(BaseVectorStore):

    name = "local"

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _init_schema(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS vectors (
                    vector_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    chunk_id INTEGER,
                    text TEXT NOT NULL DEFAULT '',
                    vector BLOB NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_vectors_user ON vectors(user_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_vectors_item ON vectors(user_id, item_id)"
            )
            connection.commit()

    def upsert(self, user_id: int, records: list[VectorRecord]) -> None:
        if not records:
            return
        rows = [
            (record.vector_id, user_id, record.item_id, record.chunk_id, record.text, _pack(record.vector))
            for record in records
        ]
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO vectors (vector_id, user_id, item_id, chunk_id, text, vector)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(vector_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    item_id = excluded.item_id,
                    chunk_id = excluded.chunk_id,
                    text = excluded.text,
                    vector = excluded.vector
                """,
                rows,
            )
            connection.commit()

    def delete_by_item(self, user_id: int, item_id: int) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "DELETE FROM vectors WHERE user_id = ? AND item_id = ?", (user_id, item_id)
            )
            connection.commit()

    def query(self, user_id: int, vector: list[float], top_k: int = 20) -> list[VectorHit]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT vector_id, item_id, chunk_id, text, vector FROM vectors WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        hits = [
            VectorHit(
                vector_id=row[0],
                item_id=row[1],
                chunk_id=row[2],
                score=_cosine(vector, _unpack(row[4])),
                text=row[3],
            )
            for row in rows
        ]
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[: max(1, top_k)]

    def count(self, user_id: int | None = None) -> int:
        with self._lock, self._connect() as connection:
            if user_id is None:
                row = connection.execute("SELECT COUNT(*) FROM vectors").fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) FROM vectors WHERE user_id = ?", (user_id,)
                ).fetchone()
        return int(row[0]) if row else 0

    def clear(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM vectors")
            connection.commit()

class ChromaVectorStore(BaseVectorStore):

    name = "chroma"

    def __init__(self, path: Path, collection_name: str) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError(
                "chromadb не установлен. Установите chromadb или используйте VECTOR_BACKEND=local."
            ) from exc

        path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(path))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, user_id: int, records: list[VectorRecord]) -> None:
        if not records:
            return
        self._collection.upsert(
            ids=[record.vector_id for record in records],
            embeddings=[record.vector for record in records],
            documents=[record.text for record in records],
            metadatas=[
                {
                    "user_id": user_id,
                    "item_id": record.item_id,
                    "chunk_id": record.chunk_id if record.chunk_id is not None else -1,
                }
                for record in records
            ],
        )

    def delete_by_item(self, user_id: int, item_id: int) -> None:
        try:
            self._collection.delete(
                where={"$and": [{"user_id": user_id}, {"item_id": item_id}]}
            )
        except Exception as exc:
            logger.debug("Не удалось удалить векторы item=%s: %s", item_id, exc)

    def query(self, user_id: int, vector: list[float], top_k: int = 20) -> list[VectorHit]:
        total = self._collection.count()
        if total == 0:
            return []
        response = self._collection.query(
            query_embeddings=[vector],
            n_results=min(max(1, top_k), total),
            where={"user_id": user_id},
            include=["metadatas", "documents", "distances"],
        )
        ids = (response.get("ids") or [[]])[0]
        metadatas = (response.get("metadatas") or [[]])[0]
        documents = (response.get("documents") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]
        hits: list[VectorHit] = []
        for index, vector_id in enumerate(ids):
            metadata = metadatas[index] or {}
            distance = distances[index] if index < len(distances) else 1.0
            hits.append(
                VectorHit(
                    vector_id=vector_id,
                    item_id=int(metadata.get("item_id", 0)),
                    chunk_id=(
                        int(metadata["chunk_id"])
                        if metadata.get("chunk_id", -1) not in (-1, None)
                        else None
                    ),
                    score=max(0.0, 1.0 - float(distance)),
                    text=documents[index] if index < len(documents) else "",
                )
            )
        return hits

    def count(self, user_id: int | None = None) -> int:
        if user_id is None:
            return self._collection.count()
        response = self._collection.get(where={"user_id": user_id}, include=[])
        return len(response.get("ids") or [])

    def clear(self) -> None:
        try:
            self._client.delete_collection(self._collection.name)
        except Exception:
            pass
        self._collection = self._client.get_or_create_collection(
            name=self._collection.name,
            metadata={"hnsw:space": "cosine"},
        )

_store: BaseVectorStore | None = None
_store_signature: tuple | None = None
_store_lock = threading.Lock()

def _build_store(settings: Settings) -> BaseVectorStore:
    requested = settings.vector_backend
    if requested in ("auto", "chroma") and importlib.util.find_spec("chromadb") is not None:
        try:
            return ChromaVectorStore(settings.chroma_path, settings.chroma_collection)
        except Exception as exc:
            if requested == "chroma":
                raise
            logger.warning("ChromaDB недоступна, использую локальное хранилище: %s", exc)
    elif requested == "chroma":
        raise RuntimeError("VECTOR_BACKEND=chroma, но пакет chromadb не установлен")
    return LocalVectorStore(settings.vector_dir / "local_vectors.db")

def get_vector_store(force: bool = False) -> BaseVectorStore:
    global _store, _store_signature
    settings = get_settings()
    signature = (
        settings.vector_backend,
        str(settings.vector_dir),
        str(settings.chroma_path),
        settings.chroma_collection,
    )
    with _store_lock:
        if force or _store is None or signature != _store_signature:
            _store = _build_store(settings)
            _store_signature = signature
            logger.info("Vector store: %s", _store.name)
        return _store

def reset_vector_store() -> None:
    global _store, _store_signature
    with _store_lock:
        _store = None
        _store_signature = None
