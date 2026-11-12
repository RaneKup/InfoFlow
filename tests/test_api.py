from __future__ import annotations

from tests.conftest import auth_headers, create_note, register_user

JWT_TEXT = (
    "JWT-аутентификация в FastAPI строится на access-токенах и refresh-токенах. "
    "Access-токен живёт недолго и передаётся в заголовке Authorization. "
    "Refresh-токен хранится безопасно и позволяет получить новую пару токенов. "
    "Нельзя хранить секретный ключ в коде, его нужно выносить в переменные окружения. "
    "Дополнительно стоит ограничивать срок жизни токена и проверять подпись."
)

def test_health_and_frontend(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"
    assert payload["ai_provider"] in ("heuristic", "none")
    assert payload["embedding_provider"] == "hash"
    assert payload["vector_backend"] == "local"

    index = client.get("/")
    assert index.status_code == 200
    assert "InfoFlow" in index.text
    assert "text/html" in index.headers["content-type"]

def test_register_login_and_profile(client):
    user = register_user(client)
    assert user["user"]["email"] == user["email"]

    login = client.post(
        "/api/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    assert login.status_code == 200
    assert login.json()["access_token"]

    wrong = client.post(
        "/api/auth/login",
        json={"email": user["email"], "password": "wrong-password"},
    )
    assert wrong.status_code == 401

    duplicate = client.post(
        "/api/auth/register",
        json={"email": user["email"], "password": "another-password"},
    )
    assert duplicate.status_code == 409

    me = client.get("/api/auth/me", headers=auth_headers(user))
    assert me.status_code == 200
    assert me.json()["email"] == user["email"]

    anonymous = client.get("/api/auth/me")
    assert anonymous.status_code == 401

    bad_token = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid"})
    assert bad_token.status_code == 401

def test_note_pipeline_generates_summary_and_tags(client):
    user = register_user(client)
    item = create_note(client, user, JWT_TEXT, title="JWT аутентификация")

    detail = client.get(f"/api/items/{item['id']}", headers=auth_headers(user)).json()
    assert detail["status"] == "ready"
    assert detail["type"] == "note"
    assert detail["title"] == "JWT аутентификация"
    assert detail["summary"]
    assert len(detail["tags"]) >= 2
    assert detail["content_text"] == JWT_TEXT
    assert all(tag["name"] for tag in detail["tags"])

    listing = client.get("/api/items", headers=auth_headers(user)).json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == item["id"]

    tags = client.get("/api/tags", headers=auth_headers(user)).json()
    assert tags
    assert sum(tag["items_count"] for tag in tags) >= 2

    stats = client.get("/api/stats", headers=auth_headers(user)).json()
    assert stats["total_items"] == 1
    assert stats["by_type"]["note"] == 1
    assert stats["by_status"]["ready"] == 1

def test_update_tags_and_reprocess(client):
    user = register_user(client)
    item = create_note(client, user, JWT_TEXT)
    headers = auth_headers(user)

    updated = client.patch(
        f"/api/items/{item['id']}",
        headers=headers,
        json={"title": "Новый заголовок", "tags": ["работа", "Python"]},
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["title"] == "Новый заголовок"
    manual = {tag["name"] for tag in payload["tags"] if not tag["is_auto_generated"]}
    assert manual == {"работа", "python"}

    reprocess = client.post(f"/api/items/{item['id']}/reprocess", headers=headers)
    assert reprocess.status_code == 202
    detail = client.get(f"/api/items/{item['id']}", headers=headers).json()
    assert detail["status"] == "ready"
    manual_after = {tag["name"] for tag in detail["tags"] if not tag["is_auto_generated"]}
    assert manual_after == {"работа", "python"}

def test_replace_tags_removes_auto_tags(client):
    user = register_user(client)
    item = create_note(client, user, JWT_TEXT, title="JWT аутентификация")
    headers = auth_headers(user)

    detail = client.get(f"/api/items/{item['id']}", headers=headers).json()
    assert any(tag["is_auto_generated"] for tag in detail["tags"])

    replaced = client.patch(
        f"/api/items/{item['id']}",
        headers=headers,
        json={"tags": ["моя тема", "jwt"], "replace_tags": True},
    )
    assert replaced.status_code == 200
    tags = replaced.json()["tags"]
    assert {tag["name"] for tag in tags} == {"моя тема", "jwt"}
    assert all(not tag["is_auto_generated"] for tag in tags)

def test_heuristic_tags_are_topical(client):
    user = register_user(client)
    item = create_note(client, user, JWT_TEXT, title="JWT аутентификация")
    detail = client.get(f"/api/items/{item['id']}", headers=auth_headers(user)).json()
    names = {tag["name"] for tag in detail["tags"]}

    assert "jwt" in names
    assert "аутентификация" in names
    assert not names & {"который", "которая", "является", "также", "нужно", "нельзя"}
    assert len(names) >= 2

def test_file_upload_and_download(client):
    user = register_user(client)
    headers = auth_headers(user)
    content = "Конспект по PostgreSQL: индексы B-tree ускоряют поиск по диапазону.".encode("utf-8")

    response = client.post(
        "/api/items/upload",
        headers=headers,
        files={"file": ("postgres.txt", content, "text/plain")},
        data={"title": "PostgreSQL конспект", "tags": "sql, база данных"},
    )
    assert response.status_code == 202, response.text
    item_id = response.json()["id"]

    detail = client.get(f"/api/items/{item_id}", headers=headers).json()
    assert detail["status"] == "ready"
    assert detail["type"] == "file"
    assert detail["file_name"] == "postgres.txt"
    assert detail["summary"]

    download = client.get(f"/api/items/{item_id}/download", headers=headers)
    assert download.status_code == 200
    assert download.content == content

def test_user_data_isolation_and_delete(client):
    owner = register_user(client)
    stranger = register_user(client)
    item = create_note(client, owner, JWT_TEXT)

    foreign_get = client.get(f"/api/items/{item['id']}", headers=auth_headers(stranger))
    assert foreign_get.status_code == 404

    foreign_delete = client.delete(
        f"/api/items/{item['id']}", headers=auth_headers(stranger)
    )
    assert foreign_delete.status_code == 404

    stranger_list = client.get("/api/items", headers=auth_headers(stranger)).json()
    assert stranger_list["total"] == 0

    deleted = client.delete(f"/api/items/{item['id']}", headers=auth_headers(owner))
    assert deleted.status_code == 204
    assert client.get(f"/api/items/{item['id']}", headers=auth_headers(owner)).status_code == 404
    listing = client.get("/api/items", headers=auth_headers(owner)).json()
    assert listing["total"] == 0

def test_item_validation(client):
    user = register_user(client)
    headers = auth_headers(user)

    bad_link = client.post(
        "/api/items",
        headers=headers,
        json={"type": "link", "url": "not-a-url"},
    )
    assert bad_link.status_code == 422

    empty_note = client.post(
        "/api/items",
        headers=headers,
        json={"type": "note", "text": "   "},
    )
    assert empty_note.status_code == 422

    manual_file = client.post(
        "/api/items",
        headers=headers,
        json={"type": "file"},
    )
    assert manual_file.status_code == 422
