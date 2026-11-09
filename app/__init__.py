import os

from flask import Flask, jsonify

from .config import Config
from .extensions import csrf, db, limiter, login_manager


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(config or Config)

    if (not app.config.get("TESTING") and app.config["SECRET_KEY"] == "dev-only-change-me"
            and os.environ.get("TV_DEV") != "1"):
        raise RuntimeError("Set SECRET_KEY (or TV_DEV=1 for local development)")

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from .routes.admin import bp as admin_bp
    from .routes.auth import bp as auth_bp
    from .routes.documents import bp as docs_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(docs_bp)
    app.register_blueprint(admin_bp)

    for code, msg in ((400, "bad request"), (401, "authentication required"), (403, "forbidden"),
                      (404, "not found"), (405, "method not allowed"), (413, "file too large"),
                      (429, "too many requests"), (500, "server error")):
        app.register_error_handler(code, lambda e, m=msg, c=code: (jsonify(error=m), c))

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/")
    def index():
        return jsonify(
            name="TrustVault",
            status="ok",
            docs="https://github.com/tannirujyothi123/trustvault#readme",
            note="JSON API. See the README for endpoints and demo accounts.",
        )

    with app.app_context():
        from .audit import install_audit_triggers
        db.create_all()
        install_audit_triggers()

    return app