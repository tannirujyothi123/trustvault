
from tests.conftest import upload
from app.models import User


def make_document(login):
    alice = login("alice@t.test")
    response = upload(alice)
    assert response.status_code == 201
    return alice, response.get_json()["id"]


def get_user_id(app, email):
    with app.app_context():
        return User.query.filter_by(email=email).first().id


def test_upload_without_file(login):
    alice = login("alice@t.test")
    response = alice.post("/api/documents", data={})
    assert response.status_code == 400


def test_search_by_category(login):
    alice, doc_id = make_document(login)

    response = alice.get("/api/documents?category=hr")
    assert response.status_code == 200
    assert any(d["id"] == doc_id for d in response.get_json())


def test_search_by_owner(login):
    alice, doc_id = make_document(login)

    response = alice.get("/api/documents?owner=ALICE@T.TEST")
    assert response.status_code == 200
    assert any(d["id"] == doc_id for d in response.get_json())


def test_search_by_name(login):
    alice, doc_id = make_document(login)

    response = alice.get("/api/documents?q=SECRET")
    assert response.status_code == 200
    assert any(d["id"] == doc_id for d in response.get_json())


def test_search_invalid_date_from(login):
    alice, _ = make_document(login)

    response = alice.get("/api/documents?date_from=invalid")
    assert response.status_code == 400


def test_search_invalid_date_to(login):
    alice, _ = make_document(login)

    response = alice.get("/api/documents?date_to=invalid")
    assert response.status_code == 400


def test_search_valid_date_filters(login):
    alice, doc_id = make_document(login)

    response = alice.get(
        "/api/documents?date_from=2020-01-01&date_to=2035-12-31"
    )

    assert response.status_code == 200
    assert any(d["id"] == doc_id for d in response.get_json())


def test_document_detail(login):
    alice, doc_id = make_document(login)

    response = alice.get(f"/api/documents/{doc_id}")

    assert response.status_code == 200
    assert response.get_json()["name"] == "secret.txt"


def test_edit_document_name(login):
    alice, doc_id = make_document(login)

    response = alice.patch(
        f"/api/documents/{doc_id}",
        json={"name": "updated.txt"}
    )

    assert response.status_code == 200
    assert response.get_json()["name"] == "updated.txt"


def test_edit_document_category(login):
    alice, doc_id = make_document(login)

    response = alice.patch(
        f"/api/documents/{doc_id}",
        json={"category": "finance"}
    )

    assert response.status_code == 200
    assert response.get_json()["category"] == "finance"


def test_edit_document_invalid_name(login):
    alice, doc_id = make_document(login)

    response = alice.patch(
        f"/api/documents/{doc_id}",
        json={"name": "invalid"}
    )

    assert response.status_code == 400


def test_edit_document_invalid_category(login):
    alice, doc_id = make_document(login)

    response = alice.patch(
        f"/api/documents/{doc_id}",
        json={"category": "   "}
    )

    assert response.status_code == 400


def test_edit_document_empty_json(login):
    alice, doc_id = make_document(login)

    response = alice.patch(
        f"/api/documents/{doc_id}",
        json={}
    )

    assert response.status_code == 200


def test_list_grants(login):
    alice, doc_id = make_document(login)

    response = alice.post(
        f"/api/documents/{doc_id}/grants",
        json={"email": "carol@t.test", "level": "read"}
    )
    assert response.status_code == 201

    response = alice.get(f"/api/documents/{doc_id}/grants")

    assert response.status_code == 200
    assert any(
        grant["email"] == "carol@t.test"
        for grant in response.get_json()
    )


def test_grant_invalid_level(login):
    alice, doc_id = make_document(login)

    response = alice.post(
        f"/api/documents/{doc_id}/grants",
        json={"email": "carol@t.test", "level": "admin"}
    )

    assert response.status_code == 400


def test_grant_unknown_user(login):
    alice, doc_id = make_document(login)

    response = alice.post(
        f"/api/documents/{doc_id}/grants",
        json={"email": "unknown@t.test", "level": "read"}
    )

    assert response.status_code == 404


def test_grant_to_self(login):
    alice, doc_id = make_document(login)

    response = alice.post(
        f"/api/documents/{doc_id}/grants",
        json={"email": "alice@t.test", "level": "read"}
    )

    assert response.status_code == 400


def test_update_existing_grant(login):
    alice, doc_id = make_document(login)

    first = alice.post(
        f"/api/documents/{doc_id}/grants",
        json={"email": "carol@t.test", "level": "read"}
    )
    assert first.status_code == 201

    second = alice.post(
        f"/api/documents/{doc_id}/grants",
        json={"email": "carol@t.test", "level": "edit"}
    )
    assert second.status_code == 201

    grants = alice.get(
        f"/api/documents/{doc_id}/grants"
    ).get_json()

    carol_grant = next(
        g for g in grants if g["email"] == "carol@t.test"
    )

    assert carol_grant["level"] == "edit"


def test_revoke_nonexistent_grant(login):
    alice, doc_id = make_document(login)

    bob_id = get_user_id(_APP["app"], "bob@t.test")

    response = alice.delete(
        f"/api/documents/{doc_id}/grants/{bob_id}"
    )

    assert response.status_code == 404


_APP = {}


import pytest


@pytest.fixture(autouse=True)
def remember_app(app):
    _APP["app"] = app
