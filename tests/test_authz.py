
"""One user must never reach another user's documents.
Each test maps to a THREATS.md entry.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.audit import verify_chain
from app.authz import authorize
from app.extensions import db
from app.models import AuditLog, Document, User
from tests.conftest import upload


def make_doc(login):
    alice = login("alice@t.test")
    r = upload(alice)
    assert r.status_code == 201
    return alice, r.get_json()["id"]


def download_data(client, doc_id):
    """Download a file and close the response safely."""
    response = client.get(f"/api/documents/{doc_id}/download")
    try:
        return response.status_code, response.data
    finally:
        response.close()


def test_unauthenticated_cannot_download(app, login):
    _, doc_id = make_doc(login)
    r = app.test_client().get(
        f"/api/documents/{doc_id}/download"
    )
    assert r.status_code == 401
    r.close()


def test_other_owner_cannot_touch_document(login):
    alice, doc_id = make_doc(login)
    bob = login("bob@t.test")

    assert bob.get(f"/api/documents/{doc_id}").status_code == 404
    assert bob.get(f"/api/documents/{doc_id}/download").status_code == 404
    assert bob.patch(
        f"/api/documents/{doc_id}",
        json={"category": "x"}
    ).status_code == 404
    assert bob.delete(f"/api/documents/{doc_id}").status_code == 404
    assert bob.get(f"/api/documents/{doc_id}/grants").status_code == 404

    assert bob.post(
        f"/api/documents/{doc_id}/grants",
        json={"email": "bob@t.test", "level": "edit"}
    ).status_code == 404

    assert download_data(alice, doc_id)[1] == b"top secret"


def test_nonexistent_and_forbidden_look_identical(login):
    _, doc_id = make_doc(login)
    bob = login("bob@t.test")

    a = bob.get(f"/api/documents/{doc_id}")
    b = bob.get(
        "/api/documents/00000000-0000-0000-0000-000000000000"
    )

    assert a.status_code == b.status_code == 404
    assert a.get_json() == b.get_json()


def test_search_and_list_do_not_leak(login):
    make_doc(login)
    bob = login("bob@t.test")

    assert bob.get("/api/documents").get_json() == []
    assert bob.get("/api/documents?q=secret").get_json() == []
    assert bob.get("/api/documents?owner=alice@t.test").get_json() == []


def test_read_grant_allows_download_but_nothing_else(login):
    alice, doc_id = make_doc(login)
    carol = login("carol@t.test")

    assert download_data(carol, doc_id)[0] == 404

    alice.post(
        f"/api/documents/{doc_id}/grants",
        json={"email": "carol@t.test", "level": "read"}
    )

    assert download_data(carol, doc_id) == (200, b"top secret")

    assert carol.patch(
        f"/api/documents/{doc_id}",
        json={"category": "x"}
    ).status_code == 404

    assert carol.delete(f"/api/documents/{doc_id}").status_code == 404

    assert carol.post(
        f"/api/documents/{doc_id}/grants",
        json={"email": "carol@t.test", "level": "edit"}
    ).status_code == 404


def test_edit_grant_cannot_share_or_delete(login):
    alice, doc_id = make_doc(login)
    carol = login("carol@t.test")

    alice.post(
        f"/api/documents/{doc_id}/grants",
        json={"email": "carol@t.test", "level": "edit"}
    )

    assert carol.patch(
        f"/api/documents/{doc_id}",
        json={"category": "x"}
    ).status_code == 200

    assert carol.delete(f"/api/documents/{doc_id}").status_code == 404

    assert carol.post(
        f"/api/documents/{doc_id}/grants",
        json={"email": "bob@t.test", "level": "read"}
    ).status_code == 404


def test_revocation_is_immediate_for_an_existing_session(login):
    alice, doc_id = make_doc(login)
    carol = login("carol@t.test")

    alice.post(
        f"/api/documents/{doc_id}/grants",
        json={"email": "carol@t.test", "level": "read"}
    )

    assert download_data(carol, doc_id)[0] == 200

    r = alice.delete(
        f"/api/documents/{doc_id}/grants/{_uid('carol@t.test')}"
    )
    assert r.status_code == 200

    assert download_data(carol, doc_id)[0] == 404


def test_deactivated_user_session_dies_immediately(login):
    carol = login("carol@t.test")
    assert carol.get("/api/me").status_code == 200

    root = login("root@t.test")

    assert root.post(
        f"/api/admin/users/{_uid('carol@t.test')}/deactivate"
    ).status_code == 200

    assert carol.get("/api/me").status_code == 401


def test_viewer_cannot_upload_and_non_admin_cannot_see_audit(login):
    carol = login("carol@t.test")

    assert upload(carol).status_code == 403
    assert carol.get("/api/admin/audit").status_code == 403
    assert login("alice@t.test").get(
        "/api/admin/audit/verify"
    ).status_code == 403


def test_admin_cannot_read_document_contents(login):
    _, doc_id = make_doc(login)
    root = login("root@t.test")

    assert root.get(
        f"/api/documents/{doc_id}/download"
    ).status_code == 404

    assert root.get("/api/admin/audit").status_code == 200


def test_refused_attempts_are_in_the_audit_trail(login):
    _, doc_id = make_doc(login)
    bob = login("bob@t.test")

    bob.get(f"/api/documents/{doc_id}/download")

    rows = login("root@t.test").get(
        f"/api/admin/audit?outcome=denied&doc_id={doc_id}"
    ).get_json()

    assert any(
        r["action"] == "doc.download"
        and r["actor_id"] == _uid("bob@t.test")
        for r in rows
    )


def test_grant_and_revoke_are_audited(login):
    alice, doc_id = make_doc(login)

    alice.post(
        f"/api/documents/{doc_id}/grants",
        json={"email": "carol@t.test", "level": "read"}
    )

    alice.delete(
        f"/api/documents/{doc_id}/grants/{_uid('carol@t.test')}"
    )

    actions = {
        r["action"]
        for r in login("root@t.test").get(
            f"/api/admin/audit?doc_id={doc_id}"
        ).get_json()
    }

    assert {"doc.upload", "perm.grant", "perm.revoke"} <= actions


def test_audit_log_cannot_be_updated_or_deleted(app, login):
    login("alice@t.test")

    with app.app_context():
        for sql in (
            "UPDATE audit_log SET outcome='ok'",
            "DELETE FROM audit_log"
        ):
            with pytest.raises(DBAPIError):
                db.session.execute(text(sql))
            db.session.rollback()


def test_hash_chain_detects_tampering_even_without_the_trigger(app, login):
    login("alice@t.test")
    login("bob@t.test")

    with app.app_context():
        assert verify_chain() == (True, None)

        db.session.execute(text("DROP TRIGGER audit_no_update"))
        db.session.execute(
            text("UPDATE audit_log SET detail='tampered' WHERE id=1")
        )
        db.session.commit()

        ok, bad = verify_chain()
        assert ok is False and bad == 1


@pytest.mark.parametrize("name,content", [
    ("evil.exe", b"MZ\x90\x00"),
    ("fake.pdf", b"<html>not a pdf</html>"),
    ("fake.png", b"%PDF-1.4"),
    ("empty.txt", b""),
    ("../../etc/passwd", b"x"),
])
def test_bad_uploads_are_rejected(login, name, content):
    assert upload(
        login("alice@t.test"),
        name=name,
        content=content
    ).status_code == 400


def test_uploaded_file_is_not_served_by_guessable_path(app, login):
    alice, doc_id = make_doc(login)

    assert app.test_client().get(
        "/storage/secret.txt"
    ).status_code == 404

    assert alice.get("/static/../storage").status_code in (404,)


def test_deleted_document_is_unreachable_to_everyone(login):
    """Kills the mutation that removes the deleted_at check in authorize()."""

    alice, doc_id = make_doc(login)
    carol = login("carol@t.test")

    r = alice.post(
        f"/api/documents/{doc_id}/grants",
        json={"email": "carol@t.test", "level": "read"}
    )
    assert r.status_code in (200, 201)

    assert download_data(carol, doc_id)[0] == 200

    assert alice.delete(
        f"/api/documents/{doc_id}"
    ).status_code in (200, 204)

    assert download_data(alice, doc_id)[0] == 404
    assert alice.get(f"/api/documents/{doc_id}").status_code == 404
    assert download_data(carol, doc_id)[0] == 404
    assert carol.get(f"/api/documents/{doc_id}").status_code == 404


def test_authorize_itself_refuses_inactive_user(app, login):
    """Tests inactive-user authorization directly."""

    from types import SimpleNamespace

    _, doc_id = make_doc(login)

    with app.app_context():
        doc = db.session.get(Document, doc_id)

        active = SimpleNamespace(
            id=doc.owner_id,
            is_authenticated=True,
            is_active=True
        )

        inactive = SimpleNamespace(
            id=doc.owner_id,
            is_authenticated=True,
            is_active=False
        )

        assert authorize(active, doc, "read") is True
        assert authorize(inactive, doc, "read") is False


_APP = {}


@pytest.fixture(autouse=True)
def _remember_app(app):
    _APP["app"] = app


def _uid(email):
    with _APP["app"].app_context():
        return User.query.filter_by(email=email).first().id
