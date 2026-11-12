from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..models import Item, Tag
from .ai import STOPWORDS
from .chunking import clean_text
from .embeddings import EmbeddingError, get_embedder
from .tags import normalize_tag
from .vector_store import get_vector_store

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")
_SUFFIXES = (
    "иями",
    "ями",
    "ами",
    "ение",
    "ание",
    "ость",
    "ого",
    "его",
    "ому",
    "ему",
    "ыми",
    "ими",
    "ых",
    "их",
    "ую",
    "юю",
    "ий",
    "ый",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ой",
    "ей",
    "ов",
    "ев",
    "ам",
    "ям",
    "ах",
    "ях",
    "ом",
    "ем",
    "ы",
    "и",
    "а",
    "я",
    "е",
    "о",
    "у",
    "ю",
)

@dataclass(slots=True)
class SearchHit:
    item_id: int
    score: float
    snippet: str
    match: str

def stem_token(token: str) -> str:
    if len(token) <= 5:
        return token
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token

def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall((text or "").lower().replace("ё", "е")):
        if len(raw) < 2 or raw in STOPWORDS or raw.isdigit():
            continue
        tokens.append(stem_token(raw))
    return tokens

def make_snippet(text: str, query_tokens: list[str], limit: int = 280) -> str:
    text = clean_text(text)
    if not text:
        return ""
    lower = text.lower()
    position = -1
    for token in query_tokens:

        index = lower.find(token)
        if index == -1 and len(token) >= 4:
            index = lower.find(token[: max(4, len(token) - 1)])
        if index != -1:
            position = index
            break
    if position == -1:
        snippet = text[:limit]
        return snippet + ("…" if len(text) > limit else "")
    start = max(0, position - limit // 3)
    end = min(len(text), start + limit)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet += "…"
    return snippet

class _BM25:
    def __init__(self, documents: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.documents = documents
        self.k1 = k1
        self.b = b
        self.doc_lengths = [len(document) for document in documents]
        self.average_length = (
            sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 0.0
        )
        self.document_frequency: Counter[str] = Counter()
        for document in documents:
            self.document_frequency.update(set(document))
        self.total = len(documents)

    def idf(self, token: str) -> float:
        frequency = self.document_frequency.get(token, 0)
        return math.log(1 + (self.total - frequency + 0.5) / (frequency + 0.5))

    def score(self, query_tokens: list[str], index: int) -> float:
        if self.total == 0 or self.average_length == 0:
            return 0.0
        frequencies = Counter(self.documents[index])
        length = self.doc_lengths[index] or 1
        total = 0.0
        for token in query_tokens:
            frequency = frequencies.get(token, 0)
            if not frequency:
                continue
            denominator = frequency + self.k1 * (
                1 - self.b + self.b * length / self.average_length
            )
            total += self.idf(token) * frequency * (self.k1 + 1) / denominator
        return total

@dataclass(slots=True)
class _Document:
    item_id: int
    text: str
    tokens: list[str]

@dataclass(slots=True)
class _ItemContext:
    item: Item
    title_tokens: set[str]
    tag_tokens: set[str]

def _load_candidate_items(
    db: Session,
    user_id: int,
    item_type: str | None,
    tag: str | None,
    limit: int = 800,
) -> list[Item]:
    statement = (
        select(Item)
        .where(Item.user_id == user_id, Item.status != "failed")
        .options(selectinload(Item.chunks), selectinload(Item.tags))
        .order_by(Item.created_at.desc())
        .limit(limit)
    )
    if item_type:
        statement = statement.where(Item.type == item_type)
    if tag:
        statement = statement.join(Item.tags).where(Tag.name == normalize_tag(tag))
    items = list(db.scalars(statement).unique().all())
    return items

def keyword_search(
    db: Session,
    user_id: int,
    query: str,
    limit: int = 20,
    item_type: str | None = None,
    tag: str | None = None,
) -> list[SearchHit]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    items = _load_candidate_items(db, user_id, item_type, tag)
    if not items:
        return []

    contexts: dict[int, _ItemContext] = {}
    documents: list[_Document] = []

    for item in items:
        tag_names = " ".join(tag.name for tag in item.tags)
        context_text = f"{item.title} {item.title} {tag_names} {item.summary}"
        contexts[item.id] = _ItemContext(
            item=item,
            title_tokens=set(tokenize(item.title)),
            tag_tokens=set(tokenize(tag_names)),
        )
        if item.chunks:
            for chunk in item.chunks:
                content = chunk.content
                documents.append(
                    _Document(
                        item_id=item.id,
                        text=content,
                        tokens=tokenize(f"{context_text} {content}"),
                    )
                )
        else:
            content = item.content_text or item.summary or item.title
            documents.append(
                _Document(
                    item_id=item.id,
                    text=content,
                    tokens=tokenize(f"{context_text} {content}"),
                )
            )

    if not documents:
        return []

    bm25 = _BM25([document.tokens for document in documents])
    query_set = set(query_tokens)
    best: dict[int, tuple[float, str, int]] = {}

    for index, document in enumerate(documents):
        score = bm25.score(query_tokens, index)
        if score <= 0:
            continue
        item_context = contexts[document.item_id]
        boost = 0.6 * len(query_set & item_context.title_tokens)
        boost += 0.35 * len(query_set & item_context.tag_tokens)
        score += boost
        current = best.get(document.item_id)
        if current is None or score > current[0]:
            best[document.item_id] = (score, document.text, index)

    phrase = clean_text(query).lower()
    hits: list[SearchHit] = []
    for item_id, (score, text, _index) in best.items():
        item = contexts[item_id].item
        if phrase and phrase in (item.title or "").lower():
            score += 1.5
        snippet = make_snippet(text, query_tokens) or make_snippet(item.summary or item.title, query_tokens)
        hits.append(
            SearchHit(item_id=item_id, score=round(score, 4), snippet=snippet, match="keyword")
        )

    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:limit]

def semantic_search(
    db: Session,
    user_id: int,
    query: str,
    limit: int = 20,
    item_type: str | None = None,
    tag: str | None = None,
) -> list[SearchHit]:
    if not query.strip():
        return []
    settings = get_settings()
    try:
        embedder = get_embedder()
        is_hash = embedder.name.startswith("hash")
        query_vector = embedder.embed_query(query)

        top_k = max(
            limit * (10 if is_hash else 5),
            settings.search_candidate_limit * (3 if is_hash else 1),
        )
        raw_hits = get_vector_store().query(user_id, query_vector, top_k=top_k)
    except EmbeddingError as exc:
        logger.warning("Семантический поиск недоступен: %s", exc)
        return []
    except Exception as exc:
        logger.warning("Ошибка векторного поиска: %s", exc)
        return []

    if not raw_hits:
        return []

    item_ids = list(dict.fromkeys(hit.item_id for hit in raw_hits))
    items = list(
        db.scalars(
            select(Item)
            .where(Item.user_id == user_id, Item.id.in_(item_ids), Item.status != "failed")
            .options(selectinload(Item.tags))
        ).all()
    )
    items_by_id = {item.id: item for item in items}
    normalized_tag = normalize_tag(tag) if tag else None
    query_tokens = set(tokenize(query))

    grouped: dict[int, list] = {}
    for raw_hit in raw_hits:
        grouped.setdefault(raw_hit.item_id, []).append(raw_hit)

    candidates: list[SearchHit] = []
    for item_id, raw_group in grouped.items():
        item = items_by_id.get(item_id)
        if item is None:
            continue
        if item_type and item.type != item_type:
            continue
        if normalized_tag and normalized_tag not in {tag.name for tag in item.tags}:
            continue

        best_cosine = max(float(hit.score) for hit in raw_group)
        tag_names = " ".join(tag.name for tag in item.tags)
        texts = [item.title, item.summary, tag_names]
        texts.extend(hit.text for hit in raw_group if hit.text)
        coverage, coverage_text = _coverage(query_tokens, texts)

        if is_hash:

            if coverage <= 0:
                continue
            score = 0.55 * max(0.0, min(1.0, best_cosine)) + 0.45 * coverage
            if score < settings.search_hash_min_score:
                continue
            best_text = coverage_text or max(raw_group, key=lambda hit: hit.score).text
        else:
            if best_cosine < settings.search_semantic_min_score:
                continue
            score = best_cosine
            best_text = max(raw_group, key=lambda hit: hit.score).text

        snippet = make_snippet(best_text, tokenize(query)) or make_snippet(
            item.summary or item.title, tokenize(query)
        )
        candidates.append(
            SearchHit(
                item_id=item.id,
                score=round(min(1.0, score), 4),
                snippet=snippet,
                match="semantic",
            )
        )

    return _apply_relevance_cutoff(
        candidates,
        min_score=settings.search_hash_min_score if is_hash else settings.search_semantic_min_score,
        relative=settings.search_semantic_relative_cutoff,
        limit=limit,
    )

def _coverage(
    query_tokens: set[str],
    texts: list[str],
) -> tuple[float, str]:
    if not query_tokens:
        return 0.0, ""
    all_tokens: set[str] = set()
    best_text = ""
    best_overlap = 0
    for text in texts:
        tokens = set(tokenize(text))
        if not tokens:
            continue
        all_tokens |= tokens
        overlap = len(query_tokens & tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_text = text
    matched = len(query_tokens & all_tokens)

    prefixes = {token[:4] for token in all_tokens if len(token) >= 5}
    for token in query_tokens:
        if token in all_tokens or len(token) < 5:
            continue
        if token[:4] in prefixes:
            matched += 1
    return min(1.0, matched / len(query_tokens)), best_text

def _apply_relevance_cutoff(
    hits: list[SearchHit],
    min_score: float,
    relative: float,
    limit: int,
) -> list[SearchHit]:
    if not hits:
        return []
    hits.sort(key=lambda hit: hit.score, reverse=True)
    cutoff = max(min_score, hits[0].score * relative)
    return [hit for hit in hits if hit.score >= cutoff][:limit]

def _rrf_fuse(
    lists: list[tuple[str, list[SearchHit]]],
    k: int,
    limit: int,
) -> list[SearchHit]:
    fused: dict[int, dict] = {}
    for source, hits in lists:
        for rank, hit in enumerate(hits, start=1):
            entry = fused.setdefault(
                hit.item_id,
                {"score": 0.0, "snippet": "", "sources": set()},
            )
            entry["score"] += 1.0 / (k + rank)
            entry["sources"].add(source)
            if not entry["snippet"]:
                entry["snippet"] = hit.snippet

    if not fused:
        return []

    best_possible = sum(1.0 / (k + 1) for _source, hits in lists if hits)
    results: list[SearchHit] = []
    for item_id, entry in fused.items():
        sources = entry["sources"]
        match = "hybrid" if len(sources) > 1 else next(iter(sources))
        normalized = entry["score"] / best_possible if best_possible else 0.0
        results.append(
            SearchHit(
                item_id=item_id,
                score=round(min(1.0, normalized), 4),
                snippet=entry["snippet"],
                match=match,
            )
        )
    results.sort(key=lambda hit: hit.score, reverse=True)
    return results[:limit]

def search_items(
    db: Session,
    user_id: int,
    query: str,
    mode: str = "hybrid",
    limit: int = 20,
    item_type: str | None = None,
    tag: str | None = None,
) -> list[SearchHit]:
    settings = get_settings()
    query = clean_text(query)
    if not query:
        return []

    candidate_limit = max(limit, settings.search_candidate_limit)
    if mode == "keyword":
        return keyword_search(db, user_id, query, limit, item_type, tag)
    if mode == "semantic":
        return semantic_search(db, user_id, query, limit, item_type, tag)

    keyword_hits = keyword_search(db, user_id, query, candidate_limit, item_type, tag)
    semantic_hits = semantic_search(db, user_id, query, candidate_limit, item_type, tag)
    return _rrf_fuse(
        [("keyword", keyword_hits), ("semantic", semantic_hits)],
        k=settings.rrf_k,
        limit=limit,
    )
