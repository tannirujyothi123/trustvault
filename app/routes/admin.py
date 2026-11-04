from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ..audit import log_event, verify_chain
from ..authz import roles_required
from ..extensions import db
from ..models import AuditLog, User

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@bp.get("/audit")
@login_required
@roles_required("admin")
def audit():
    q = AuditLog.query
    if request.args.get("outcome"):
        q = q.filter(AuditLog.outcome == request.args["outcome"])
    if request.args.get("action"):
        q = q.filter(AuditLog.action == request.args["action"])
    if request.args.get("doc_id"):
        q = q.filter(AuditLog.doc_id == request.args["doc_id"])
    if request.args.get("actor_id", type=int):
        q = q.filter(AuditLog.actor_id == request.args.get("actor_id", type=int))
    limit = min(request.args.get("limit", 100, type=int), 500)
    rows = q.order_by(AuditLog.id.desc()).limit(limit).all()
    return jsonify([{"id": r.id, "ts": r.ts, "actor_id": r.actor_id, "action": r.action,
                     "doc_id": r.doc_id, "outcome": r.outcome, "detail": r.detail} for r in rows])


@bp.get("/audit/verify")
@login_required
@roles_required("admin")
def audit_verify():
    ok, bad_id = verify_chain()
    return jsonify(intact=ok, first_broken_row=bad_id)


@bp.get("/users")
@login_required
@roles_required("admin")
def users():
    return jsonify([{"id": u.id, "email": u.email, "role": u.role, "active": u.active}
                    for u in User.query.order_by(User.id).all()])


@bp.post("/users/<int:user_id>/deactivate")
@login_required
@roles_required("admin")
def deactivate(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify(error="not found"), 404
    if user.id == current_user.id:
        return jsonify(error="you cannot deactivate yourself"), 400
    user.active = False
    user.token_version += 1                  # every session / token issued before now is dead
    log_event("user.deactivate", actor=current_user, detail={"user_id": user.id})
    return jsonify(ok=True)