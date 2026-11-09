# TrustVault write-up

## What I built

TrustVault is a document sharing API where the wrong person cannot read a file, and every access attempt can be proven afterwards. It is built with Flask, SQLAlchemy and Postgres, and runs on Render at https://trustvault-8ko9.onrender.com.

There are three roles. Owners upload documents and give named users read or edit access, and they can take it back. Viewers only see what was shared with them. Admins manage users and read the audit log, but they cannot read document contents. Search works by name, owner, category and date, and only searches documents the user is allowed to see. Uploads are checked for type, size and content.

## Security decisions

- **One permission check.** Every route that touches a document goes through `authorize()` in `authz.py`, including the download route. Nothing is cached, so revoking access works on the very next request.
- **404 for everything.** A user without access gets the same 404 as for a document that does not exist, so IDs cannot be probed.
- **Audit trail.** Every action is logged, and so is every denied attempt and failed login. The audit table is protected by database triggers that block update, delete and truncate. Each row also stores a hash of the row before it, and an admin endpoint checks the chain.
- **Audit before action.** The audit row is written before a document is returned or a file is sent. If the write fails, the request fails and no data is sent.
- **No default secrets.** The app will not start without a SECRET_KEY, and the admin password is never in the repo.

## Testing

There are 41 automated tests. They cover cross-user access, the direct download route, search not leaking names, immediate revocation, deactivated users, upload validation, and the audit log (denied attempts, grants and revokes, tamper detection). I also used mutation testing on `authz.py`: I removed one rule at a time and checked a test failed. Two rules had no test (inactive user and deleted document), so I added them.

I also checked the live site by hand. A viewer with no access got 404 on read, download, edit and delete. After a read grant the viewer got 200 but could not edit. After the owner revoked, the viewer got 404 again. The admin audit log showed all of it, and the hash chain check said intact.

## What I did not finish

- The audit hash has no secret key (HMAC), and deleting the last rows would not be noticed. I wrote this in THREATS.md.
- There is no web page, only the API.
- There is no endpoint to create users. Users come from the seed script.
- No virus scan on uploads.
- On the free Render plan, uploaded files are lost on restart, the first request is slow, and the Postgres database expires on December 7, 2026.

## How I used AI

I used AI to review my code, suggest tests and help debug the deployment. PROMPTS.md has the dated entries. Two of them were AI mistakes that I caught: it guessed the wrong cause for a Postgres driver error, and it first said the service had not redeployed when it had. In the second case I added a temporary debug route to see which database the app used, and found that a wrongly cased variable name (`Database_URL`) made the app fall back to SQLite. I fixed the name and removed the route.