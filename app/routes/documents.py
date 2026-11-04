import json
from datetime import date

from flask import Blueprint, jsonify, request, send_file
from flask_login import current_user, login_required
from sqlalchemy import and_, func, or_
from werkzeug.utils import secure_filename

from ..audit import log_event
from ..authz import load_authorized, roles_required
from ..extensions import db
from ..models import Document, Permission, User, utcnow_iso
from ..storage import UploadError, path_for, save_bytes, validate_upload

bp = Blueprint("documents", __name__, url_prefix="/api/documents")


def doc_json(d):
    return {"id": d.id, "name": d.name, "category": d.category, "owner": d.owner.email,
            "size": d.size, "mime": d.mime, "sha256": d.sha256, "created_at": d.created_at}


def visible_documents(user):
    """Only documents the user owns or was granted. Used by list AND search, so search can
    never reveal a name the user could not open."""
    return (Document.query
            .filter(Document.deleted_at.is_(None))
            .outerjoin(Permission, and_(Permission.document_id == Document.id,
                                        Permission.user_id == user.id))
            .filter(or_(Document.owner_id == user.id, Permission.id.isnot(None))))


def _day(value, end=False):
    try:
        date.fromisoformat(value)
    except ValueError:
        return None
    return value + ("T23:59:59.999999+00:00" if end else "")


@bp.post("")
@login_required
@roles_required("owner")
def upload():
    f = request.files.get("file")
    if f is None:
        return jsonify(error="file is required"), 400
    category = (request.form.get("category") or "general").strip()[:50] or "general"
    try:
        name, mime, data = validate_upload(f)
    except UploadError as e:
        log_event("doc.upload", actor=current_user, outcome="rejected", detail=str(e))
        return jsonify(error=str(e)), 400
    storage_name, digest = save_bytes(data)
    doc = Document(name=name, category=category, owner_id=current_user.id,
                   storage_name=storage_name, size=len(data), mime=mime, sha256=digest)
    db.session.add(doc)
    db.session.flush()
    log_event("doc.upload", actor=current_user, doc_id=doc.id, detail={"name": name, "size": len(data)})
    return jsonify(doc_json(doc)), 201


@bp.get("")
@login_required
def search():
    q = visible_documents(current_user)
    term = request.args.get("q", "").strip().lower()
    if term:
        q = q.filter(func.lower(Document.name).contains(term, autoescape=True))
    if request.args.get("category"):
        q = q.filter(Document.category == request.args["category"])
    if request.args.get("owner"):
        q = q.filter(Document.owner.has(User.email == request.args["owner"].strip().lower()))
    if request.args.get("date_from"):
        start = _day(request.args["date_from"])
        if start is None:
            return jsonify(error="date_from must be YYYY-MM-DD"), 400
        q = q.filter(Document.created_at >= start)
    if request.args.get("date_to"):
        end = _day(request.args["date_to"], end=True)
        if end is None:
            return jsonify(error="date_to must be YYYY-MM-DD"), 400
        q = q.filter(Document.created_at <= end)
    docs = q.order_by(Document.created_at.desc()).limit(50).all()
    return jsonify([doc_json(d) for d in docs])


@bp.get("/<doc_id>")
@login_required
def detail(doc_id):
    doc = load_authorized(doc_id, "read")
    log_event("doc.read", actor=current_user, doc_id=doc.id)
    return jsonify(doc_json(doc))


@bp.get("/<doc_id>/download")
@login_required
def download(doc_id):
    doc = load_authorized(doc_id, "download")       # <-- THE check for downloads
    log_event("doc.download", actor=current_user, doc_id=doc.id, detail={"sha256": doc.sha256})
    return send_file(path_for(doc.storage_name), as_attachment=True,
                     download_name=doc.name, mimetype=doc.mime)


@bp.patch("/<doc_id>")
@login_required
def edit(doc_id):
    doc = load_authorized(doc_id, "edit")
    data = request.get_json(silent=True) or {}
    changes = {}
    if "name" in data:
        new_name = secure_filename(str(data["name"]))
        if not new_name or "." not in new_name:
            return jsonify(error="invalid name"), 400
        changes["name"] = [doc.name, new_name]
        doc.name = new_name
    if "category" in data:
        new_cat = str(data["category"]).strip()[:50]
        if not new_cat:
            return jsonify(error="invalid category"), 400
        changes["category"] = [doc.category, new_cat]
        doc.category = new_cat
    log_event("doc.edit", actor=current_user, doc_id=doc.id, detail=json.dumps(changes))
    return jsonify(doc_json(doc))


@bp.delete("/<doc_id>")
@login_required
def delete(doc_id):
    doc = load_authorized(doc_id, "delete")
    doc.deleted_at = utcnow_iso()                    # soft delete: file kept, document unreachable
    log_event("doc.delete", actor=current_user, doc_id=doc.id)
    return jsonify(ok=True)


# ---- permissions (owner only) -------------------------------------------------------------

@bp.get("/<doc_id>/grants")
@login_required
def list_grants(doc_id):
    doc = load_authorized(doc_id, "share")
    rows = (db.session.query(Permission, User).join(User, User.id == Permission.user_id)
            .filter(Permission.document_id == doc.id).all())
    return jsonify([{"user_id": u.id, "email": u.email, "level": p.level} for p, u in rows])


@bp.post("/<doc_id>/grants")
@login_required
def grant(doc_id):
    doc = load_authorized(doc_id, "share")
    data = request.get_json(silent=True) or {}
    level = data.get("level")
    if level not in ("read", "edit"):
        return jsonify(error="level must be 'read' or 'edit'"), 400
    target = User.query.filter_by(email=str(data.get("email", "")).strip().lower()).first()
    if target is None or not target.is_active:
        return jsonify(error="user not found"), 404
    if target.id == current_user.id:
        return jsonify(error="you already own this document"), 400
    perm = Permission.query.filter_by(document_id=doc.id, user_id=target.id).first()
    if perm is None:
        perm = Permission(document_id=doc.id, user_id=target.id, level=level, granted_by=current_user.id)
        db.session.add(perm)
    else:
        perm.level = level
    log_event("perm.grant", actor=current_user, doc_id=doc.id, detail={"to": target.id, "level": level})
    return jsonify(ok=True), 201


@bp.delete("/<doc_id>/grants/<int:user_id>")
@login_required
def revoke(doc_id, user_id):
    doc = load_authorized(doc_id, "share")
    perm = Permission.query.filter_by(document_id=doc.id, user_id=user_id).first()
    if perm is None:
        return jsonify(error="no such grant"), 404
    db.session.delete(perm)
    log_event("perm.revoke", actor=current_user, doc_id=doc.id, detail={"from": user_id})
    return jsonify(ok=True)