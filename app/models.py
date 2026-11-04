import uuid
from datetime import datetime, timezone

from flask_login import UserMixin

from .extensions import db


def utcnow_iso() -> str:
    # ISO strings in a fixed format: sortable, comparable, and stable for hashing
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), nullable=False)          # admin | owner | viewer
    active = db.Column(db.Boolean, nullable=False, default=True)
    token_version = db.Column(db.Integer, nullable=False, default=0)   # bump => all old sessions die

    @property
    def is_active(self):                                      # Flask-Login uses this
        return self.active


class Document(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(50), nullable=False, default="general")
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    storage_name = db.Column(db.String(64), nullable=False)   # random name on disk, never user-supplied
    size = db.Column(db.Integer, nullable=False)
    mime = db.Column(db.String(100), nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.String(40), nullable=False, default=utcnow_iso, index=True)
    deleted_at = db.Column(db.String(40), nullable=True)      # soft delete

    owner = db.relationship("User")


class Permission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.String(36), db.ForeignKey("document.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    level = db.Column(db.String(10), nullable=False)          # read | edit
    granted_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.String(40), nullable=False, default=utcnow_iso)

    __table_args__ = (db.UniqueConstraint("document_id", "user_id", name="uq_doc_user"),)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ts = db.Column(db.String(40), nullable=False)
    actor_id = db.Column(db.Integer, nullable=True)           # deliberately NO foreign key: logs outlive users
    action = db.Column(db.String(50), nullable=False)
    doc_id = db.Column(db.String(64), nullable=True)
    outcome = db.Column(db.String(10), nullable=False)        # ok | denied | fail | rejected
    detail = db.Column(db.Text, nullable=False, default="")
    prev_hash = db.Column(db.String(64), nullable=False)
    hash = db.Column(db.String(64), nullable=False)