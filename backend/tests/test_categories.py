"""Integration tests for /categories — seeding, CRUD, scoping, and bill rules."""

from tests.conftest import auth, register_and_login

DEFAULT_KEYS = [
    "housing",
    "utilities",
    "insurance",
    "subscriptions",
    "entertainment",
    "transport",
    "healthcare",
    "education",
    "other",
]

_BILL = {
    "name": "Electricity",
    "category": "utilities",
    "frequency": "monthly",
    "amount": "100.00",
    "currency": "PLN",
    "due_day": 15,
    "is_paused": False,
}


def _categories(client, token, query: str = "") -> list[dict]:
    r = client.get(f"/categories{query}", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def _create_custom(client, token, name: str) -> dict:
    r = client.post("/categories", json={"name": name}, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()


def _default_id(client, token, key: str) -> int:
    category = next(
        c
        for c in _categories(client, token, "?include_archived=true")
        if c["key"] == key
    )
    return category["id"]


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def test_registration_seeds_nine_defaults(client):
    token = register_and_login(client, "cat_seed@test.com")

    cats = _categories(client, token)
    assert [c["key"] for c in cats] == sorted(DEFAULT_KEYS)
    assert all(c["name"] is None for c in cats)
    assert all(c["is_archived"] is False for c in cats)
    assert all(isinstance(c["id"], int) for c in cats)


def test_get_categories_is_idempotent(client):
    token = register_and_login(client, "cat_seed_idem@test.com")

    first = _categories(client, token)
    second = _categories(client, token)
    assert first == second


def test_get_categories_restores_a_missing_default(client):
    token = register_and_login(client, "cat_seed_missing@test.com")
    other_id = _default_id(client, token, "other")

    r = client.delete(f"/categories/{other_id}", headers=auth(token))
    assert r.status_code == 204

    cats = _categories(client, token)
    assert "other" in [c["key"] for c in cats]


def test_categories_are_scoped_per_user(client):
    tok_a = register_and_login(client, "cat_scope_a@test.com")
    tok_b = register_and_login(client, "cat_scope_b@test.com")

    custom = _create_custom(client, tok_a, "A only")
    assert "A only" in [c["name"] for c in _categories(client, tok_a)]
    assert "A only" not in [c["name"] for c in _categories(client, tok_b)]

    # B cannot rename, archive, or delete A's category.
    r = client.patch(
        f"/categories/{custom['id']}", json={"name": "Hijack"}, headers=auth(tok_b)
    )
    assert r.status_code == 404
    r = client.patch(
        f"/categories/{custom['id']}", json={"is_archived": True}, headers=auth(tok_b)
    )
    assert r.status_code == 404
    r = client.delete(f"/categories/{custom['id']}", headers=auth(tok_b))
    assert r.status_code == 404

    # A's category is untouched.
    assert "A only" in [c["name"] for c in _categories(client, tok_a)]


def test_categories_require_authentication(client):
    assert client.get("/categories").status_code == 401
    assert client.post("/categories", json={"name": "x"}).status_code == 401


def test_delete_account_cascades_bills_and_categories(client):
    token = register_and_login(client, "cat_delete_user@test.com")
    custom = _create_custom(client, token, "Pets")

    payload = {k: v for k, v in _BILL.items() if k != "category"}
    payload["category_id"] = custom["id"]
    r = client.post("/bills", json=payload, headers=auth(token))
    assert r.status_code == 201

    r = client.delete("/auth/users/me", headers=auth(token))
    assert r.status_code == 204

    # Re-registering the same email starts from a clean slate.
    token2 = register_and_login(client, "cat_delete_user@test.com")
    cats = _categories(client, token2)
    assert [c["key"] for c in cats] == sorted(DEFAULT_KEYS)
    assert all(c["name"] is None for c in cats)


# ---------------------------------------------------------------------------
# Create / rename / archive
# ---------------------------------------------------------------------------


def test_create_custom_category_trims_and_orders_after_defaults(client):
    token = register_and_login(client, "cat_create@test.com")

    r = client.post("/categories", json={"name": "  Pets  "}, headers=auth(token))
    assert r.status_code == 201
    created = r.json()
    assert created["name"] == "Pets"
    assert created["key"] is None
    assert created["is_archived"] is False

    cats = _categories(client, token)
    assert [c["key"] for c in cats[:9]] == sorted(DEFAULT_KEYS)
    assert cats[-1]["name"] == "Pets"


def test_create_blank_or_too_long_name_returns_422(client):
    token = register_and_login(client, "cat_create_invalid@test.com")

    assert (
        client.post(
            "/categories", json={"name": "   "}, headers=auth(token)
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/categories", json={"name": "x" * 51}, headers=auth(token)
        ).status_code
        == 422
    )


def test_duplicate_category_names_rejected_case_insensitively(client):
    token = register_and_login(client, "cat_dupe@test.com")
    _create_custom(client, token, "Pets")

    r = client.post("/categories", json={"name": "pets"}, headers=auth(token))
    assert r.status_code == 422

    other = _create_custom(client, token, "Streaming")
    r = client.patch(
        f"/categories/{other['id']}", json={"name": "PETS"}, headers=auth(token)
    )
    assert r.status_code == 422


def test_rename_custom_category(client):
    token = register_and_login(client, "cat_rename@test.com")
    custom = _create_custom(client, token, "Streaming")

    r = client.patch(
        f"/categories/{custom['id']}", json={"name": "TV"}, headers=auth(token)
    )
    assert r.status_code == 200
    assert r.json()["name"] == "TV"


def test_rename_default_category_keeps_key(client):
    token = register_and_login(client, "cat_rename_default@test.com")
    utilities = _default_id(client, token, "utilities")

    r = client.patch(
        f"/categories/{utilities}", json={"name": "Prąd"}, headers=auth(token)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Prąd"
    assert body["key"] == "utilities"


def test_patch_without_fields_is_a_noop(client):
    token = register_and_login(client, "cat_patch_noop@test.com")
    utilities = _default_id(client, token, "utilities")

    r = client.patch(f"/categories/{utilities}", json={}, headers=auth(token))
    assert r.status_code == 200
    assert r.json()["name"] is None


def test_archive_hides_from_default_list_and_unarchive_restores(client):
    token = register_and_login(client, "cat_archive@test.com")
    custom = _create_custom(client, token, "Pets")

    r = client.patch(
        f"/categories/{custom['id']}", json={"is_archived": True}, headers=auth(token)
    )
    assert r.status_code == 200
    assert r.json()["is_archived"] is True

    assert "Pets" not in [c["name"] for c in _categories(client, token)]
    archived = _categories(client, token, "?include_archived=true")
    assert "Pets" in [c["name"] for c in archived]

    r = client.patch(
        f"/categories/{custom['id']}", json={"is_archived": False}, headers=auth(token)
    )
    assert r.status_code == 200
    assert "Pets" in [c["name"] for c in _categories(client, token)]


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_unused_category(client):
    token = register_and_login(client, "cat_delete@test.com")
    custom = _create_custom(client, token, "Pets")

    r = client.delete(f"/categories/{custom['id']}", headers=auth(token))
    assert r.status_code == 204
    assert "Pets" not in [
        c["name"] for c in _categories(client, token, "?include_archived=true")
    ]

    r = client.patch(
        f"/categories/{custom['id']}", json={"name": "z"}, headers=auth(token)
    )
    assert r.status_code == 404


def test_delete_in_use_category_returns_400(client):
    token = register_and_login(client, "cat_delete_in_use@test.com")
    custom = _create_custom(client, token, "Pets")

    payload = {k: v for k, v in _BILL.items() if k != "category"}
    payload["category_id"] = custom["id"]
    r = client.post("/bills", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text

    r = client.delete(f"/categories/{custom['id']}", headers=auth(token))
    assert r.status_code == 400
    assert "used by existing bills" in r.json()["detail"]

    # Archiving remains possible while a bill references it.
    r = client.patch(
        f"/categories/{custom['id']}", json={"is_archived": True}, headers=auth(token)
    )
    assert r.status_code == 200

    # The bill still resolves the archived category on read.
    bills = client.get("/bills", headers=auth(token)).json()
    assert bills[0]["category"]["name"] == "Pets"
    assert bills[0]["category"]["is_archived"] is True


# ---------------------------------------------------------------------------
# Bill integration
# ---------------------------------------------------------------------------


def test_create_bill_with_category_id_returns_nested_category(client):
    token = register_and_login(client, "cat_bill_create@test.com")
    custom = _create_custom(client, token, "Pets")

    payload = {k: v for k, v in _BILL.items() if k != "category"}
    payload["category_id"] = custom["id"]
    r = client.post("/bills", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    category = r.json()["category"]
    assert category["id"] == custom["id"]
    assert category["name"] == "Pets"
    assert category["key"] is None


def test_create_bill_prefers_category_id_over_legacy_string(client):
    token = register_and_login(client, "cat_bill_prefer@test.com")
    custom = _create_custom(client, token, "Pets")

    payload = {**_BILL, "category_id": custom["id"], "category": "utilities"}
    r = client.post("/bills", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    assert r.json()["category"]["name"] == "Pets"


def test_create_bill_without_any_category_returns_422(client):
    token = register_and_login(client, "cat_bill_missing@test.com")
    payload = {k: v for k, v in _BILL.items() if k != "category"}

    r = client.post("/bills", json=payload, headers=auth(token))
    assert r.status_code == 422


def test_create_bill_with_unknown_legacy_key_returns_422(client):
    token = register_and_login(client, "cat_bill_unknown@test.com")

    r = client.post("/bills", json={**_BILL, "category": "nope"}, headers=auth(token))
    assert r.status_code == 422


def test_create_bill_rejects_archived_category(client):
    token = register_and_login(client, "cat_bill_archived@test.com")
    custom = _create_custom(client, token, "Pets")
    r = client.patch(
        f"/categories/{custom['id']}", json={"is_archived": True}, headers=auth(token)
    )
    assert r.status_code == 200

    payload = {k: v for k, v in _BILL.items() if k != "category"}
    payload["category_id"] = custom["id"]
    r = client.post("/bills", json=payload, headers=auth(token))
    assert r.status_code == 422


def test_update_bill_rejects_archived_category(client):
    token = register_and_login(client, "cat_bill_update_archived@test.com")
    custom = _create_custom(client, token, "Pets")
    r = client.post("/bills", json=_BILL, headers=auth(token))
    assert r.status_code == 201
    bill_id = r.json()["id"]

    r = client.patch(
        f"/categories/{custom['id']}", json={"is_archived": True}, headers=auth(token)
    )
    assert r.status_code == 200

    r = client.patch(
        f"/bills/{bill_id}", json={"category_id": custom["id"]}, headers=auth(token)
    )
    assert r.status_code == 422


def test_update_bill_keeps_an_unchanged_archived_category(client):
    """Editing a bill must not fail because its existing category was archived."""
    token = register_and_login(client, "cat_bill_keep_archived@test.com")
    custom = _create_custom(client, token, "Pets")
    payload = {k: v for k, v in _BILL.items() if k != "category"}
    payload["category_id"] = custom["id"]
    r = client.post("/bills", json=payload, headers=auth(token))
    assert r.status_code == 201, r.text
    bill_id = r.json()["id"]

    r = client.patch(
        f"/categories/{custom['id']}", json={"is_archived": True}, headers=auth(token)
    )
    assert r.status_code == 200

    r = client.patch(
        f"/bills/{bill_id}",
        json={"category_id": custom["id"], "notes": "still pets"},
        headers=auth(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["category"]["id"] == custom["id"]


def test_update_bill_with_legacy_key_and_category_id(client):
    token = register_and_login(client, "cat_bill_update@test.com")
    r = client.post("/bills", json=_BILL, headers=auth(token))
    assert r.status_code == 201
    bill_id = r.json()["id"]

    r = client.patch(
        f"/bills/{bill_id}", json={"category": "housing"}, headers=auth(token)
    )
    assert r.status_code == 200
    assert r.json()["category"]["key"] == "housing"

    custom = _create_custom(client, token, "Pets")
    r = client.patch(
        f"/bills/{bill_id}", json={"category_id": custom["id"]}, headers=auth(token)
    )
    assert r.status_code == 200
    assert r.json()["category"]["name"] == "Pets"


def test_legacy_key_creates_a_deleted_default_again(client):
    token = register_and_login(client, "cat_bill_recreate@test.com")
    education_id = _default_id(client, token, "education")
    r = client.delete(f"/categories/{education_id}", headers=auth(token))
    assert r.status_code == 204

    r = client.post(
        "/bills", json={**_BILL, "category": "education"}, headers=auth(token)
    )
    assert r.status_code == 201, r.text
    assert r.json()["category"]["key"] == "education"
    assert "education" in [c["key"] for c in _categories(client, token)]
