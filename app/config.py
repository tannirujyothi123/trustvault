import os
from datetime import timedelta


class Config:
    # No default: production must provide SECRET_KEY (checked in wsgi.py).
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///trustvault.db"
    ).replace("postgres://", "postgresql://", 1)
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024          # 10 MB hard cap (Flask rejects bigger with 413)
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(os.getcwd(), "storage"))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Strict"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"   # set COOKIE_SECURE=1 on any https host
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-only"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False