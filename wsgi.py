"""
TrustVault - WSGI application entry point.

This file creates the Flask application instance
for local development and production deployment.
"""

from app import create_app

app = create_app()


if __name__ == "__main__":
    app.run()