"""python seed.py  -> demo users + two demo documents. Safe to run twice."""
from werkzeug.security import generate_password_hash

from app import create_app
from app.audit import log_event
from app.extensions import db
from app.models import Document, Permission, User
from app.storage import save_bytes

USERS = [
    ("admin@trustvault.test", "Admin#12345", "admin"),
    ("owner1@trustvault.test", "Owner1#12345", "owner"),
    ("owner2@trustvault.test", "Owner2#12345", "owner"),
    ("viewer1@trustvault.test", "Viewer1#12345", "viewer"),
]

app = create_app()
with app.app_context():
    if User.query.first():
        print("already seeded")
    else:
        for email, pw, role in USERS:
            db.session.add(User(email=email, password_hash=generate_password_hash(pw), role=role))
        db.session.commit()
        o1 = User.query.filter_by(email="owner1@trustvault.test").first()
        o2 = User.query.filter_by(email="owner2@trustvault.test").first()
        v1 = User.query.filter_by(email="viewer1@trustvault.test").first()
        for owner, name, body in ((o1, "salary-letter.txt", b"Confidential: salary letter (demo)"),
                                  (o2, "contract.txt", b"Confidential: customer contract (demo)")):
            storage_name, digest = save_bytes(body)
            doc = Document(name=name, category="demo", owner_id=owner.id, storage_name=storage_name,
                           size=len(body), mime="text/plain", sha256=digest)
            db.session.add(doc)
            db.session.flush()
            log_event("doc.upload", actor=owner, doc_id=doc.id, detail={"name": name, "seed": True})
            if owner is o1:
                db.session.add(Permission(document_id=doc.id, user_id=v1.id, level="read", granted_by=o1.id))
                log_event("perm.grant", actor=o1, doc_id=doc.id, detail={"to": v1.id, "level": "read"})
        print("seeded:", ", ".join(e for e, _, _ in USERS))