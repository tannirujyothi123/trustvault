from flask import Blueprint, jsonify, request, session
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import generate_csrf
from werkzeug.security import check_password_hash, generate_password_hash

from ..audit import log_event
from ..extensions import db, limiter, login_manager
from ..models import User

bp = Blueprint("auth", __name__, url_prefix="/api")

# compared against when the email is unknown, so timing does not reveal which emails exist
_DUMMY_HASH = generate_password_hash("not-a-real-password")


@login_manager.user_loader
def load_user(user_id):
    """Runs on EVERY request. This is why deactivation / token_version bumps work instantly."""
    try:
        user = db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
    if user is None or not user.is_active:
        return None
    if session.get("tv") != user.token_version:
        return None
    return user


@login_manager.unauthorized_handler
def unauthorized():
    return jsonify(error="authentication required"), 401


@bp.get("/csrf")
def csrf_token():
    return jsonify(csrf_token=generate_csrf())


@bp.post("/login")
@limiter.limit("5 per minute")
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    user = User.query.filter_by(email=email).first()
    password_ok = check_password_hash(user.password_hash if user else _DUMMY_HASH, password)
    if user is None or not password_ok or not user.is_active:
        log_event("auth.login", outcome="fail", detail=email[:100])
        return jsonify(error="invalid credentials"), 401      # same message for every failure
    session.clear()                                           # no session fixation
    login_user(user)
    session["tv"] = user.token_version
    session.permanent = True
    log_event("auth.login", actor=user)
    return jsonify(id=user.id, email=user.email, role=user.role)


@bp.post("/logout")
@login_required
def logout():
    log_event("auth.logout", actor=current_user)
    logout_user()
    session.clear()
    return jsonify(ok=True)


@bp.get("/me")
@login_required
def me():
    return jsonify(id=current_user.id, email=current_user.email, role=current_user.role)