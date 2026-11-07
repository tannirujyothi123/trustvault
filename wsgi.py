"""
TrustVault - WSGI application entry point.

This file creates the Flask application instance
for local development and production deployment.
"""

from app import create_app

app = create_app()

# Fail closed: refuse to start without a real secret key, otherwise anyone
# who knows a default key could forge a session cookie and log in as any user.
if not app.config.get("SECRET_KEY"):
    raise RuntimeError("SECRET_KEY must be set (e.g. python -c \"import secrets; print(secrets.token_hex(32))\")")


if __name__ == "__main__":
    app.run()