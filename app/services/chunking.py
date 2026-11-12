from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"[ \t\u00a0]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")

DEFAULT_SEPARATORS = ("\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ")

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", " ")
    text = _WHITESPACE_RE.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()

def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)

def _split_by_separator(text: str, separator: str) -> list[str]:
    if separator == "":
        return list(text)
    if separator == " ":
        return text.split(" ")
    parts = text.split(separator)
    return [part + separator for part in parts[:-1]] + [parts[-1]] if len(parts) > 1 else [text]

def _merge_pieces(pieces: list[str], chunk_size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}{piece}" if current else piece
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current.strip())
        if len(piece) <= chunk_size:
            current = piece
        else:

            start = 0
            while start < len(piece):
                end = min(start + chunk_size, len(piece))
                chunks.append(piece[start:end].strip())
                if end >= len(piece):
                    break
                start = max(end - overlap, start + 1)
            current = ""
    if current.strip():
        chunks.append(current.strip())

    if overlap <= 0 or len(chunks) < 2:
        return [chunk for chunk in chunks if chunk]
    with_overlap: list[str] = []
    for index, chunk in enumerate(chunks):
        if index == 0:
            with_overlap.append(chunk)
            continue
        tail = chunks[index - 1][-overlap:]
        if tail and not chunk.startswith(tail):
            with_overlap.append(f"{tail}{chunk}")
        else:
            with_overlap.append(chunk)
    return [chunk for chunk in with_overlap if chunk]

def split_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 150,
    max_chunks: int = 120,
) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    chunk_size = max(200, chunk_size)
    overlap = min(max(0, overlap), chunk_size // 2)

    pieces: list[str] = []
    remaining = text
    for separator in DEFAULT_SEPARATORS:
        if len(remaining) <= chunk_size:
            break
        if separator == " ":
            pieces = remaining.split(" ")
            remaining = ""
            break
        parts = remaining.split(separator)
        if len(parts) > 1:

            rebuilt = [part + separator for part in parts[:-1]]
            rebuilt.append(parts[-1])
            pieces = rebuilt
            remaining = ""
            break

    if remaining:
        pieces = [remaining]

    chunks = _merge_pieces(pieces, chunk_size, overlap)

    normalized: list[str] = []
    for chunk in chunks:
        if len(chunk) <= chunk_size * 1.5:
            normalized.append(chunk)
        else:
            step = max(1, chunk_size - overlap)
            for start in range(0, len(chunk), step):
                normalized.append(chunk[start : start + chunk_size].strip())
    return [chunk for chunk in normalized if chunk][:max_chunks]

def make_title_from_text(text: str, max_length: int = 90) -> str:
    text = clean_text(text)
    if not text:
        return "Без названия"
    first_line = text.split("\n", 1)[0]
    sentence = _SENTENCE_RE.split(first_line, maxsplit=1)[0]
    title = (sentence or first_line).strip(" .;:—-")
    if len(title) > max_length:
        title = title[: max_length - 1].rstrip() + "…"
    return title or "Без названия"
