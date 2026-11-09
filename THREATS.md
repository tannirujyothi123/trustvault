“demo credentials are public by design, admin credential is shared privately”.## Document existence leak

Attack: a logged-in user tries another person's document ID to find out if the
file exists.

What I did: if a user has no access, the app returns 404 "not found", the same as
for a document that does not exist. So the attacker cannot tell the difference.
The check runs on every request, including download. Document IDs are random
UUIDs, so they cannot be guessed. Search and list only show documents the user
owns or was given access to.

Tested: on the live app, a viewer with no access got 404 for read, download,
edit and delete.

Accepted risk: response time may differ a little between the two cases. Low
impact because the IDs are random.