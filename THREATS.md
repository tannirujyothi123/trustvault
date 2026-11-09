# THREATS.md

These are the attacks I thought about for TrustVault, what I did for each one, and what I knew I was leaving open.

## 1. Someone reads a document that is not theirs

A logged in user could try to read, download, edit or delete another user's document, even by using the direct download link.

Every route checks permission on the server (`load_authorized` in `authz.py`). The download route has the same check as the others. The list and search only return documents the user owns or has been given access to.

I tested this on the live site. A viewer with no access got 404 for read, download, edit and delete.

Admins cannot read document contents. They can manage users and see the audit log, but the same permission check applies to them as to everyone else.

## 2. Guessing which documents exist

If the app said "forbidden" for one case and "not found" for another, an attacker could find out which IDs are real. So I return 404 for both. Document IDs are random UUIDs, so they can't be guessed anyway.

Left open: the response time might be slightly different in the two cases. I think this is low risk because of the random IDs.

## 3. Access that continues after revoking

Permissions are read from the database on every request. I tested it live: the viewer got 200 after I granted access, and 404 right after the owner revoked it. A deactivated user is also logged out on the next request, because the user is loaded again on every request.

## 4. A read-only user editing

A viewer with read access tried to edit and was refused. The attempt was written to the audit log as denied.

## 5. Changing the audit log

Someone could edit or delete audit rows to hide what they did. I did two things. Database triggers block update, delete and truncate on the audit table. Also, every row stores a hash of the row before it, so changing or removing a row breaks the chain. The endpoint /api/admin/audit/verify checks this, and the last live check said intact. Only an admin can read the log. A viewer got 403.

Left open: the hash has no secret key. Someone with full database access could remove the trigger and rewrite the whole chain. Deleting the last few rows would also go unnoticed. A keyed hash (HMAC) and saving the latest hash somewhere outside the database would fix this. I ran out of time.

## 6. Denied attempts not being recorded

Denied reads, downloads, edits and deletes are all written to the audit log with the user and the document ID. Failed logins are logged too. I checked all of these in the admin audit view on the live site.

## 7. Guessing passwords

Login is limited to 5 tries per minute. Passwords are stored as hashes. A wrong email and a wrong password give the same error.

Left open: the limit is stored in memory, so it resets when the server restarts.

## 8. Stolen or fake sessions

The app will not start without a SECRET_KEY from the environment, so there is no default key to guess. Cookies are HttpOnly and SameSite Strict, and Secure on the hosted site. CSRF tokens are required. The session is cleared at login.

## 9. Bad uploads

Uploaded files are checked in `validate_upload` before they are saved, and rejected uploads are written to the audit log. Files are not in a public folder. They can only be downloaded through the route that checks permission and logs the download.

## 10. Secrets in a public repo

No secret key or admin password is in the code. The admin password is given as an environment variable when the database is seeded. The seed script only creates demo documents if I ask it to, so the live database has none.

Left open: the owner and viewer demo passwords are public on purpose, so reviewers can test. The admin password is shared privately.

## Deployment risks I accepted

- It runs on Render's free plan, so the first request after a quiet period can take up to a minute.
- Uploaded files are saved on Render's disk, which is wiped on restart or redeploy. A real system would use object storage.
- The free Postgres database expires on December 7, 2026 and has no backups.
- There is one server and one database, with no failover.