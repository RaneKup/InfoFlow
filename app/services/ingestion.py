from __future__ import annotations

import io
import ipaddress
import logging
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import get_settings
from .chunking import clean_text

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (compatible; InfoFlowBot/1.0; +https://github.com/) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".csv",
    ".tsv",
    ".json",
    ".log",
    ".yml",
    ".yaml",
    ".py",
    ".js",
    ".ts",
    ".css",
    ".sql",
}

class IngestionError(RuntimeError):
    pass

@dataclass(slots=True)
class FetchedPage:
    title: str
    text: str
    final_url: str

def _is_public_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )

def assert_safe_url(url: str) -> None:
    settings = get_settings()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise IngestionError("Поддерживаются только http/https-ссылки")
    if not parsed.hostname:
        raise IngestionError("В ссылке отсутствует домен")
    if parsed.port and parsed.port not in (80, 443, 8080, 8443):

        if not settings.allow_private_urls:
            raise IngestionError("Нестандартный порт запрещён")
    if settings.allow_private_urls:
        return

    host = parsed.hostname
    if host.lower() in ("localhost", "localhost.localdomain"):
        raise IngestionError("Локальные адреса запрещены")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror as exc:
        raise IngestionError(f"Не удалось разрешить домен {host}") from exc
    if not addresses or any(not _is_public_ip(address) for address in addresses):
        raise IngestionError("Ссылки на локальную сеть запрещены")

def _extract_html(html: bytes, base_url: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(
        ["script", "style", "noscript", "nav", "footer", "aside", "form", "svg", "iframe", "button"]
    ):
        tag.decompose()

    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = str(og_title["content"]).strip()
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        heading = soup.find("h1")
        if heading:
            title = heading.get_text(" ", strip=True)

    container = soup.find("article") or soup.find("main") or soup.body or soup
    lines = [
        clean_text(line)
        for line in container.get_text("\n").split("\n")
        if clean_text(line)
    ]

    deduped: list[str] = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)
    text = clean_text("\n".join(deduped))
    return clean_text(title), text

def _fetch_direct(url: str, max_chars: int, timeout: float) -> FetchedPage:
    assert_safe_url(url)
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers=headers,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "application/pdf" in content_type or response.content[:4] == b"%PDF":
                text = extract_pdf_bytes(response.content)
                title = Path(urlparse(str(response.url)).path).stem.replace("_", " ").replace("-", " ")
                return FetchedPage(title=title, text=text[:max_chars], final_url=str(response.url))
            if not any(
                marker in content_type
                for marker in ("text/html", "application/xhtml", "text/plain", "application/xml")
            ):
                raise IngestionError(f"Неподдерживаемый тип содержимого: {content_type or 'неизвестно'}")
            title, text = _extract_html(response.content, str(response.url))
            if not text and not title:
                raise IngestionError("На странице не удалось найти текст")
            return FetchedPage(
                title=title[:500],
                text=text[:max_chars],
                final_url=str(response.url),
            )
    except httpx.HTTPStatusError as exc:
        raise IngestionError(
            f"Сайт вернул ошибку {exc.response.status_code} для {url}"
        ) from exc
    except httpx.HTTPError as exc:
        raise IngestionError(f"Не удалось загрузить страницу: {exc}") from exc

def _fetch_with_jina(url: str, max_chars: int, timeout: float) -> FetchedPage:
    settings = get_settings()
    reader_url = f"{settings.jina_reader_url.rstrip('/')}/{url}"
    headers = {"X-Return-Format": "markdown", "User-Agent": _USER_AGENT}
    if settings.jina_api_key:
        headers["Authorization"] = f"Bearer {settings.jina_api_key}"
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        response = client.get(reader_url, headers=headers)
        response.raise_for_status()
        raw = response.text

    title = ""
    body_lines: list[str] = []
    in_content = False
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("Title:"):
            title = stripped.removeprefix("Title:").strip()
            continue
        if stripped.startswith("Markdown Content:"):
            in_content = True
            continue
        if stripped.startswith(("URL Source:", "Published Time:", "Warning:")):
            continue
        if in_content or not any(
            stripped.startswith(prefix)
            for prefix in ("Title:", "URL Source:", "Published Time:")
        ):
            body_lines.append(line)
    text = clean_text("\n".join(body_lines))
    if not title:
        for line in body_lines:
            if line.strip().startswith("#"):
                title = line.strip().lstrip("#").strip()
                break
    if not text:
        raise IngestionError("Jina Reader вернул пустой текст")
    return FetchedPage(
        title=title[:500] or Path(urlparse(url).path).stem,
        text=text[:max_chars],
        final_url=url,
    )

def fetch_web_page(url: str) -> FetchedPage:
    settings = get_settings()
    if settings.jina_api_key:
        try:
            return _fetch_with_jina(
                url,
                settings.max_content_chars,
                settings.ingestion_timeout_seconds,
            )
        except Exception as exc:
            logger.warning("Jina Reader недоступен, скачиваю напрямую: %s", exc)
    return _fetch_direct(url, settings.max_content_chars, settings.ingestion_timeout_seconds)

def extract_pdf_bytes(data: bytes, max_pages: int = 150) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise IngestionError("Для PDF установите пакет pypdf") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise IngestionError("PDF защищён паролем") from exc
        pages: list[str] = []
        for page in reader.pages[:max_pages]:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(page_text)
        text = clean_text("\n\n".join(pages))
    except IngestionError:
        raise
    except Exception as exc:
        raise IngestionError(f"Не удалось прочитать PDF: {exc}") from exc
    if not text:
        raise IngestionError("В PDF не найден текстовый слой (возможно, это скан)")
    return text

def extract_pdf(path: str | Path) -> str:
    return extract_pdf_bytes(Path(path).read_bytes())

def _decode_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251", "koi8-r"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")

def extract_file_text(
    path: str | Path,
    mime_type: str | None = None,
    filename: str | None = None,
) -> str:
    file_path = Path(path)
    suffix = Path(filename or file_path.name).suffix.lower()
    mime = (mime_type or "").lower()

    if suffix == ".pdf" or "application/pdf" in mime:
        return extract_pdf(file_path)

    data = file_path.read_bytes()
    if suffix in (".html", ".htm") or "text/html" in mime:
        _title, text = _extract_html(data, "")
        if not text:
            raise IngestionError("В HTML-файле не найден текст")
        return text

    if suffix in _TEXT_EXTENSIONS or mime.startswith("text/") or not suffix:
        return clean_text(_decode_bytes(data))

    try:
        return clean_text(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise IngestionError(
            f"Формат {suffix or mime or 'файла'} пока не поддерживается. "
            "Поддерживаются PDF, HTML, TXT, MD, CSV, JSON и другие текстовые форматы."
        ) from exc
