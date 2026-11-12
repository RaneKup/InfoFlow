from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

ItemType = Literal["link", "note", "file"]
SearchMode = Literal["hybrid", "keyword", "semantic"]

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    telegram_id: int | None = None
    created_at: datetime

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_auto_generated: bool

class TagStat(BaseModel):
    id: int
    name: str
    is_auto_generated: bool
    items_count: int

class ItemCreate(BaseModel):
    type: ItemType = "link"
    url: str | None = Field(default=None, max_length=4096)
    text: str | None = Field(default=None, max_length=500_000)
    title: str | None = Field(default=None, max_length=512)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _validate_payload(self) -> "ItemCreate":
        if self.type == "file":
            raise ValueError("Файлы загружаются через POST /api/items/upload")
        if self.type == "link":
            if not self.url or not self.url.strip():
                raise ValueError("Для типа 'link' обязателен параметр url")
            parsed = urlparse(self.url.strip())
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError("URL должен начинаться с http:// или https://")
        if self.type == "note" and (not self.text or not self.text.strip()):
            raise ValueError("Для типа 'note' обязателен непустой параметр text")
        return self

class ItemUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=512)
    summary: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = Field(default=None, max_length=20)

    replace_tags: bool = False

class ItemListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str
    original_url: str | None = None
    summary: str
    status: str
    error_message: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    created_at: datetime
    updated_at: datetime
    tags: list[TagOut] = Field(default_factory=list)

class ItemOut(ItemListItem):
    content_text: str = ""

class ItemListOut(BaseModel):
    items: list[ItemListItem]
    total: int
    limit: int
    offset: int

class SearchResultOut(ItemListItem):
    score: float
    snippet: str
    match: str

class SearchResponse(BaseModel):
    query: str
    mode: SearchMode
    total: int
    took_ms: int
    results: list[SearchResultOut]

class StatsOut(BaseModel):
    total_items: int
    by_type: dict[str, int]
    by_status: dict[str, int]
    tags_count: int
    last_saved_at: datetime | None = None

class HealthOut(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    database: str
    ai_provider: str
    embedding_provider: str
    vector_backend: str

class MessageOut(BaseModel):
    message: str
