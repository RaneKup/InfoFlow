from __future__ import annotations

from tests.conftest import auth_headers, create_note, register_user

JWT_NOTE = (
    "Настройка JWT-аутентификации: access-токен и refresh-токен. "
    "Токены доступа передаются в заголовке Authorization, подпись проверяется "
    "секретным ключом. Безопасность зависит от срока жизни токена и ротации ключей."
)
SOUP_NOTE = (
    "Рецепт борща: свёкла, капуста, картофель, морковь и говядина. "
    "Варить бульон два часа, добавить овощи и томатную пасту, подавать со сметаной."
)
DB_NOTE = (
    "PostgreSQL: индексы B-tree и планировщик запросов. EXPLAIN ANALYZE показывает "
    "стоимость выполнения, а составной индекс ускоряет фильтрацию по нескольким колонкам."
)

def _seed_three_notes(client, user) -> dict[str, int]:
    headers = auth_headers(user)
    first = create_note(client, user, JWT_NOTE, title="JWT аутентификация")
    second = create_note(client, user, SOUP_NOTE, title="Рецепт борща")
    third = create_note(client, user, DB_NOTE, title="PostgreSQL индексы")

    client.patch(
        f"/api/items/{first['id']}",
        headers=headers,
        json={"tags": ["jwt", "безопасность"]},
    )
    client.patch(
        f"/api/items/{second['id']}",
        headers=headers,
        json={"tags": ["рецепт", "кулинария"]},
    )
    client.patch(
        f"/api/items/{third['id']}",
        headers=headers,
        json={"tags": ["sql", "база данных"]},
    )
    return {"jwt": first["id"], "soup": second["id"], "db": third["id"]}

def test_keyword_semantic_and_hybrid_search(client):
    user = register_user(client)
    ids = _seed_three_notes(client, user)
    headers = auth_headers(user)

    for mode in ("keyword", "semantic", "hybrid"):
        response = client.get(
            "/api/search",
            headers=headers,
            params={"q": "токены доступа и безопасность", "mode": mode},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["mode"] == mode
        assert payload["results"], f"режим {mode} ничего не нашёл"
        assert payload["results"][0]["id"] == ids["jwt"], payload
        assert payload["results"][0]["snippet"]
        assert payload["results"][0]["match"] in ("keyword", "semantic", "hybrid")

    soup_results = client.get(
        "/api/search",
        headers=headers,
        params={"q": "свёкла капуста бульон", "mode": "hybrid"},
    ).json()["results"]
    assert soup_results[0]["id"] == ids["soup"]

    semantic_results = client.get(
        "/api/search",
        headers=headers,
        params={"q": "токены доступа и безопасность", "mode": "semantic"},
    ).json()["results"]
    semantic_ids = {result["id"] for result in semantic_results}
    assert semantic_ids == {ids["jwt"]}, semantic_results

def test_search_filters_by_tag_and_type(client):
    user = register_user(client)
    ids = _seed_three_notes(client, user)
    headers = auth_headers(user)

    by_tag = client.get(
        "/api/search",
        headers=headers,
        params={"q": "данные", "mode": "hybrid", "tag": "sql"},
    ).json()
    assert by_tag["results"]
    assert all(result["id"] == ids["db"] for result in by_tag["results"])

    by_type = client.get(
        "/api/search",
        headers=headers,
        params={"q": "свёкла", "mode": "hybrid", "type": "note"},
    ).json()
    assert by_type["results"][0]["id"] == ids["soup"]

    listing = client.get(
        "/api/items", headers=headers, params={"tag": "кулинария"}
    ).json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == ids["soup"]

def test_search_is_isolated_between_users(client):
    owner = register_user(client)
    stranger = register_user(client)
    _seed_three_notes(client, owner)

    response = client.get(
        "/api/search",
        headers=auth_headers(stranger),
        params={"q": "JWT токены", "mode": "hybrid"},
    )
    assert response.status_code == 200
    assert response.json()["results"] == []

def test_list_search_and_pagination(client):
    user = register_user(client)
    headers = auth_headers(user)
    for index in range(5):
        create_note(client, user, f"Пятая заметка номер {index} про индексы и базы данных")

    first_page = client.get(
        "/api/items", headers=headers, params={"limit": 2, "offset": 0}
    ).json()
    second_page = client.get(
        "/api/items", headers=headers, params={"limit": 2, "offset": 2}
    ).json()
    assert first_page["total"] == 5
    assert len(first_page["items"]) == 2
    assert len(second_page["items"]) == 2
    assert {item["id"] for item in first_page["items"]}.isdisjoint(
        {item["id"] for item in second_page["items"]}
    )

    filtered = client.get(
        "/api/items", headers=headers, params={"q": "номер 3"}
    ).json()
    assert filtered["total"] == 1
