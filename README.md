# TrustVault

Secure document sharing where the wrong person cannot read a file, and every access attempt (allowed or denied) is recorded in a tamper-evident audit log.

Live app: https://trustvault-8ko9.onrender.com

It runs on Render's free plan, so the first request after a quiet period can take up to a minute. Open `/api/csrf` once to wake it up.

This is a JSON API (Flask, SQLAlchemy, Postgres). There is no web page. Use the examples below or the PowerShell steps in "Try it".

## Roles

- **owner**: uploads documents, shares them with named users, can revoke.
- **viewer**: can only open documents that were shared with them.
- **admin**: manages users and reads the audit log. Admins cannot read document contents.

## Demo accounts

| Role | Email | Password |
|---|---|---|
| owner | owner1@trustvault.test | Owner1#12345 |
| owner | owner2@trustvault.test | Owner2#12345 |
| viewer | viewer1@trustvault.test | Viewer1#12345 |
| admin | admin@trustvault.test | shared privately with the reviewers |

The owner and viewer passwords are public on purpose so reviewers can test.

## API and who can call it

Paths start with `/api`. Everything is checked on the server on every request, including the download route.

| Endpoint | Who can call it |
|---|---|
| `GET /csrf` | anyone |
| `POST /login` | anyone (5 tries per minute) |
| `POST /logout` | logged in |
| `GET /me` | logged in |
| `POST /documents` | owner only |
| `GET /documents` | logged in, returns only documents the user owns or was given |
| `GET /documents/<id>` | owner, or a user with a read or edit grant |
| `GET /documents/<id>/download` | owner, or a user with a read or edit grant |
| `PATCH /documents/<id>` | owner, or a user with an edit grant |
| `DELETE /documents/<id>` | owner only (soft delete) |
| `GET /documents/<id>/grants` | owner only |
| `POST /documents/<id>/grants` | owner only |
| `DELETE /documents/<id>/grants/<user_id>` | owner only |
| `GET /admin/audit` | admin only |
| `GET /admin/audit/verify` | admin only |
| `GET /admin/users` | admin only |
| `POST /admin/users/<id>/deactivate` | admin only |

Anyone without access to a document gets `404 {"error": "not found"}`, the same as for a document that does not exist. Wrong role gets `403`. Not logged in gets `401`.

Request details:

- Upload: multipart form with `file` and optional `category`.
- Search: `GET /documents?q=name&category=x&owner=email&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD` (max 50 results).
- Grant: JSON `{"email": "user@example.com", "level": "read"}` where level is `read` or `edit`.
- Edit: JSON with `name` and/or `category`.
- Audit filters: `outcome`, `action`, `doc_id`, `actor_id`, `limit`.

### CSRF and login

State-changing requests need a CSRF token. Call `GET /api/csrf`, send the value in the `X-CSRFToken` header, and keep the session cookie. Login clears the session, so fetch a new token after logging in. Over HTTPS the request also needs a `Referer` or `Origin` header.

## What gets audited

Uploads, reads, downloads, edits, deletes, grants, revokes, logins (including failed ones), user deactivation, and every denied attempt. Each row stores a hash of the previous row, and database triggers block UPDATE, DELETE and TRUNCATE on the table. `GET /api/admin/audit/verify` checks the chain.

## Run locally

```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:TV_DEV = "1"
$env:SECRET_KEY = "any-local-value"
python -m flask --app wsgi run
```

Without `SECRET_KEY` the app refuses to start. The local database is SQLite in `instance/`.

Create the demo users:

```
$env:SEED_ADMIN_PASSWORD = "choose-a-strong-password"
python seed.py
```

Add `$env:SEED_DEMO_DOCS = "1"` to also create two demo documents. Only do this locally, because the files are written to your machine.

## Tests

```
python -m pytest -q
```

41 tests, including ones that show one user cannot read, download, edit or delete another user's document, that revoking takes effect at once, and that denied attempts are audited.

## Deploy on Render

1. Create a Postgres database on Render (same region as the web service).
2. Create a Web Service from this repo, branch `main`.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn wsgi:app`
5. Environment variables (names are case sensitive):

| Name | Value |
|---|---|
| `SECRET_KEY` | long random string, for example `python -c "import secrets; print(secrets.token_hex(32))"` |
| `COOKIE_SECURE` | `1` |
| `DATABASE_URL` | the Postgres Internal Database URL |
| `PYTHON_VERSION` | `3.12.8` |

6. After the first deploy, seed the database from your own computer with the Postgres External Database URL:

```
$env:DATABASE_URL = "external url"
$env:SECRET_KEY = "any-value"
$env:SEED_ADMIN_PASSWORD = "strong-password"
python seed.py
```

Then clear those variables from the terminal.

## Known limits

- There is no endpoint to create users. Users come from `seed.py`. Admins can list and deactivate them.
- Free Render plan: slow first request, uploaded files are lost on restart or redeploy, the free Postgres expires on December 7, 2026.
- The audit hash has no secret key, and removing the last rows would not be detected. See THREATS.md.

## More

- THREATS.md: attacks considered, what I did, what I accepted.
- PROMPTS.md: dated notes on how I used AI, including its mistakes.