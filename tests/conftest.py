import io

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import User

PW = "pass12345!"


@pytest.fixture
def app(tmp_path):
    class Cfg(TestConfig):
        UPLOAD_DIR = str(tmp_path)

    app = create_app(Cfg)
    with app.app_context():
        for email, role in (("alice@t.test", "owner"), ("bob@t.test", "owner"),
                            ("carol@t.test", "viewer"), ("root@t.test", "admin")):
            db.session.add(User(email=email, password_hash=generate_password_hash(PW), role=role))
        db.session.commit()
    return app


@pytest.fixture
def login(app):
    """login('alice@t.test') -> a fresh client (own cookie jar) logged in as that user."""
    def _login(email):
        c = app.test_client()
        r = c.post("/api/login", json={"email": email, "password": PW})
        assert r.status_code == 200, r.get_json()
        return c
    return _login


def upload(client, name="secret.txt", content=b"top secret", category="hr"):
    return client.post("/api/documents", content_type="multipart/form-data",
                       data={"file": (io.BytesIO(content), name), "category": category})