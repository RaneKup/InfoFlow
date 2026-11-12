from __future__ import annotations

import hashlib
import importlib.util
import logging
import math
import re
import threading
from abc import ABC, abstractmethod

import httpx

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")

class EmbeddingError(RuntimeError):
    pass

class BaseEmbedder(ABC):
    name: str = "base"
    dim: int = 0

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        if not vectors:
            return [0.0] * max(1, self.dim)
        return vectors[0]

class HashEmbedder(BaseEmbedder):

    def __init__(self, dim: int = 384) -> None:
        self.dim = max(64, dim)
        self.name = f"hash-{self.dim}"

    @staticmethod
    def _hash(token: str) -> int:
        return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big")

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        words = _WORD_RE.findall(text.lower())
        if not words:
            return vector

        def add(token: str, weight: float) -> None:
            hashed = self._hash(token)
            index = hashed % self.dim
            sign = 1.0 if (hashed >> 63) & 1 else -1.0
            vector[index] += sign * weight

        for word in words:
            add(f"w:{word}", 1.0)
            if len(word) > 4:
                for start in range(len(word) - 2):
                    add(f"c:{word[start:start + 3]}", 0.25)

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

class SentenceTransformerEmbedder(BaseEmbedder):

    def __init__(self, model_name: str, fallback_dim: int = 384) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingError(
                "sentence-transformers не установлен. "
                "Установите его или используйте EMBEDDING_PROVIDER=hash/ollama."
            ) from exc

        self.name = f"st:{model_name}"
        try:
            self._model = SentenceTransformer(model_name)
        except Exception as exc:
            raise EmbeddingError(f"Не удалось загрузить модель эмбеддингов: {exc}") from exc
        dim = self._model.get_sentence_embedding_dimension()
        self.dim = int(dim or fallback_dim)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            vectors = self._model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=16,
            )
        except Exception as exc:
            raise EmbeddingError(f"Ошибка векторизации: {exc}") from exc
        return [list(map(float, vector)) for vector in vectors]

class OllamaEmbedder(BaseEmbedder):

    def __init__(self, base_url: str, model: str, fallback_dim: int = 384) -> None:
        root = base_url.rstrip("/")
        if root.endswith("/v1"):
            root = root[:-3]
        self._root = root
        self._model = model
        self.dim = fallback_dim
        self.name = f"ollama:{model}"

    def _request(self, texts: list[str]) -> list[list[float]]:
        with httpx.Client(timeout=120.0) as client:
            try:
                response = client.post(
                    f"{self._root}/api/embed",
                    json={"model": self._model, "input": texts},
                )
                if response.status_code == 404:

                    vectors: list[list[float]] = []
                    for text in texts:
                        legacy = client.post(
                            f"{self._root}/api/embeddings",
                            json={"model": self._model, "prompt": text},
                        )
                        legacy.raise_for_status()
                        vectors.append([float(value) for value in legacy.json()["embedding"]])
                    return vectors
                response.raise_for_status()
                data = response.json()
                embeddings = data.get("embeddings") or [data.get("embedding")]
                if not embeddings or embeddings[0] is None:
                    raise EmbeddingError("Ollama вернул пустой ответ")
                return [[float(value) for value in vector] for vector in embeddings]
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                raise EmbeddingError(f"Ollama недоступен: {exc}") from exc

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._request(texts)
        if vectors and vectors[0]:
            self.dim = len(vectors[0])
        return vectors

_embedder: BaseEmbedder | None = None
_embedder_signature: tuple | None = None
_embedder_lock = threading.Lock()

def _build_embedder(settings: Settings) -> BaseEmbedder:
    provider = settings.embedding_provider
    if provider == "hash":
        return HashEmbedder(settings.embedding_dim)

    if provider == "ollama":
        return OllamaEmbedder(
            settings.ollama_base_url,
            settings.ollama_embedding_model,
            settings.embedding_dim,
        )

    if provider in ("local", "sentence"):
        return SentenceTransformerEmbedder(settings.embedding_model, settings.embedding_dim)

    if importlib.util.find_spec("sentence_transformers") is not None:
        try:
            return SentenceTransformerEmbedder(settings.embedding_model, settings.embedding_dim)
        except EmbeddingError as exc:
            logger.warning("Семантическая модель недоступна, переключаюсь на hash: %s", exc)
    return HashEmbedder(settings.embedding_dim)

def get_embedder(force: bool = False) -> BaseEmbedder:
    global _embedder, _embedder_signature
    settings = get_settings()
    signature = (
        settings.embedding_provider,
        settings.embedding_model,
        settings.embedding_dim,
        settings.ollama_base_url,
        settings.ollama_embedding_model,
    )
    with _embedder_lock:
        if force or _embedder is None or signature != _embedder_signature:
            _embedder = _build_embedder(settings)
            _embedder_signature = signature
            logger.info("Embeddings: %s (dim=%s)", _embedder.name, _embedder.dim)
        return _embedder

def reset_embedder() -> None:
    global _embedder, _embedder_signature
    with _embedder_lock:
        _embedder = None
        _embedder_signature = None
