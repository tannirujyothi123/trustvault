# PROMPTS.md

Dated notes on how I used AI in TrustVault. I used it for ideas and for fixing errors, and I checked what it said against the running app and the tests. Entries 1 and 2 are about authorization and auditing. Entries 4 and 5 are mistakes the AI made that I caught.

## 1. 2026-11-04: Authorization, mutation testing on authz.py

Asked: my tests passed (22), but how do I know they would catch a broken authorization rule?

AI said: try mutation testing. Make one small change to `authz.py` (for example remove the inactive-user check), run the tests, and see if any test fails. Then put the file back.

What I did: I wrote a small PowerShell function that changes one line, runs pytest and restores the file with git. Two changes were not caught by any test: removing the inactive-user check and removing the deleted-document check. I added a test for each (`e91d15c`) and ran the same two changes again. This time exactly one test failed each time.

## 2. 2026-11-04: Auditing, review of audit.py

Asked: is my audit log really tamper-resistant?

AI said: the database triggers and the hash chain are a good design, but the hash has no secret key, so someone with database access could rewrite the whole chain. Also, deleting the last rows would not be noticed. It also said a failed audit write should stop the request.

What I did: I did not have time to add HMAC, so I wrote both gaps in THREATS.md as accepted risks. For the third point I checked the code. `log_event` runs before the file is sent and before the document is returned, and it has no try/except, so if the audit write fails the request errors out and no document data is sent. Later I checked the log on the live site: `/api/admin/audit/verify` said intact, and denied reads, downloads, edits, deletes and failed logins all showed up.

## 3. 2026-11-07: SECRET_KEY must come from the environment

Asked: is it safe to keep a default SECRET_KEY for development?

AI said: no. Anyone who knows the default could forge a session cookie and log in as any user.

What I did: I removed the default in `config.py` and made `wsgi.py` stop with an error if the key is missing. The test config has its own key. All 41 tests still passed (`6029fa9`). I put a different, random key in Render.

## 4. 2026-11-07: Postgres driver error on Render (AI was wrong)

Asked: why does the deploy crash with `No module named 'psycopg'`?

AI said: first that Python 3.14 was the problem, then that SQLAlchemy would use psycopg2 for a `postgresql://` URL.

What was wrong: both guesses were wrong. Pinning Python 3.12 did not fix it, and the same error came back. The installed SQLAlchemy wanted `psycopg`, not `psycopg2`.

What I did: I added `psycopg[binary]` to requirements.txt (`496ba27`). My append joined two lines (`pytest>=8.0psycopg[binary]`), which would have broken the build, so I rewrote the file with one package per line (`2fbc1f7`). The deploy then went live.

## 5. 2026-11-07: Login gave 401 on the live site (AI was wrong at first)

Asked: owner and admin login returned 401 on Render, but the same users existed in the database.

AI said: first that the web service had not redeployed, then that the Environment value was probably wrong. The first claim was wrong, the log showed the deploy had run.

What I did: I stopped guessing. I added a temporary route (`/api/debug/db`, `3e21781`) that showed which database the app used. It showed a local SQLite file and 0 users. The cause was my Render variable name, `Database_URL`. Linux variable names are case sensitive, so the app did not see it and used SQLite. I renamed it to `DATABASE_URL`, login worked, and I removed the debug route right away (`8c3f1d2`). The first debug commit also failed to deploy once (`5ea688f`) before the next one worked.

## 6. 2026-11-07: Passwords in the public repo

Asked: how do I seed accounts when the repo is public?

AI said: the admin password must not be in the code.

What I did: `seed.py` now reads the admin password from `SEED_ADMIN_PASSWORD` and stops if it is missing. Demo documents are created only when `SEED_DEMO_DOCS=1`, because files made on my laptop would not exist on Render (`41abb05`). I also reset the admin password in the live database with a small script, and that reset is in the audit log.

## 7. 2026-11-08: Live proof of access control

Asked: how can I show access control working on the real site?

AI said: use a script that logs in as owner, viewer and admin, then check the status codes and the audit log.

What I did: I ran it on the live app. A viewer without a grant got 404 on read, download, edit and delete. After a read grant the viewer got 200, and edit still failed. After the owner revoked, the viewer got 404 again. The admin audit log showed all of it, including the denied rows. I used this as the base for the demo video.