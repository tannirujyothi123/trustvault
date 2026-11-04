"""THE authorisation decision lives here. Every route that touches a document goes through
authorize() (usually via load_authorized). Nothing is cached: grants are read from the DB on
every call, which is what makes revocation immediate.

Model:
  owner of the document -> read, download, edit, delete, share
  grant 'edit'          -> read, download, edit
  grant 'read'          -> read, download
  everyone else         -> nothing (including admins: admins manage users + see the audit
                           trail, but cannot read document contents)
"""
from functools import wraps

from flask import abort, request
from flask_login import current_user

from .audit import log_event
from .extensions import db
from .models import Document, Permission

OWNER_ACTIONS = {"read", "download", "edit", "delete", "share"}


def authorize(user, doc, action) -> bool:
    if doc is None or doc.deleted_at is not None:
        return False
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if doc.owner_id == user.id:
        return action in OWNER_ACTIONS
    perm = Permission.query.filter_by(document_id=doc.id, user_id=user.id).first()
    if perm is None:
        return False
    if action in ("read", "download"):
        return True
    if action == "edit":
        return perm.level == "edit"
    return False        # delete / share are owner-only, whatever the grant says


def load_authorized(doc_id, action):
    """Fetch a document or stop. 'does not exist' and 'not yours' look identical (404),
    and the refused attempt is written to the audit trail."""
    doc = db.session.get(Document, doc_id)
    if not authorize(current_user, doc, action):
        log_event(f"doc.{action}", actor=current_user, doc_id=doc_id, outcome="denied")
        abort(404)
    return doc


def roles_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if current_user.role not in roles:
                log_event("access.role", actor=current_user, outcome="denied", detail=request.path)
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return deco