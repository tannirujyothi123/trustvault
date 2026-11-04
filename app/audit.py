"""Tamper-evident audit trail.

Two layers:
 1. DB triggers refuse UPDATE / DELETE (/TRUNCATE on Postgres) on audit_log.
 2. Hash chain: every row stores sha256(prev_hash + its own fields). If someone with DB
    superpowers drops the trigger and edits a row, verify_chain() finds the break.
"""
import hashlib
import json

from sqlalchemy import text

from .extensions import db
from .models import AuditLog, utcnow_iso

GENESIS = "0" * 64


def _digest(prev, ts, actor_id, action, doc_id, outcome, detail):
    payload = json.dumps([prev, ts, actor_id, action, doc_id, outcome, detail],
                         separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def log_event(action, actor=None, doc_id=None, outcome="ok", detail=""):
    """Append one audit row. NOTE: this commits the session, so a change you made just
    before calling it and its audit row are saved in ONE transaction."""
    if db.engine.dialect.name == "postgresql":
        db.session.execute(text("SELECT pg_advisory_xact_lock(424242)"))   # serialise chain writers
    if not isinstance(detail, str):
        detail = json.dumps(detail, sort_keys=True)
    detail = detail[:500]
    doc_id = doc_id[:64] if doc_id else None
    actor_id = actor.id if (actor is not None and getattr(actor, "is_authenticated", False)) else None

    last = AuditLog.query.order_by(AuditLog.id.desc()).first()
    prev = last.hash if last else GENESIS
    ts = utcnow_iso()
    row = AuditLog(ts=ts, actor_id=actor_id, action=action, doc_id=doc_id, outcome=outcome,
                   detail=detail, prev_hash=prev,
                   hash=_digest(prev, ts, actor_id, action, doc_id, outcome, detail))
    db.session.add(row)
    db.session.commit()
    return row


def verify_chain():
    """Returns (True, None) if intact, else (False, id_of_first_bad_row)."""
    prev = GENESIS
    for r in AuditLog.query.order_by(AuditLog.id.asc()).all():
        expected = _digest(prev, r.ts, r.actor_id, r.action, r.doc_id, r.outcome, r.detail)
        if r.prev_hash != prev or r.hash != expected:
            return False, r.id
        prev = r.hash
    return True, None


def install_audit_triggers():
    dialect = db.engine.dialect.name
    if dialect == "sqlite":
        for ev in ("UPDATE", "DELETE"):
            db.session.execute(text(
                f"CREATE TRIGGER IF NOT EXISTS audit_no_{ev.lower()} BEFORE {ev} ON audit_log "
                f"BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;"))
    elif dialect == "postgresql":
        db.session.execute(text(
            "CREATE OR REPLACE FUNCTION audit_no_mod() RETURNS trigger AS $$ "
            "BEGIN RAISE EXCEPTION 'audit_log is append-only'; END; $$ LANGUAGE plpgsql"))
        db.session.execute(text("DROP TRIGGER IF EXISTS audit_no_mod_row ON audit_log"))
        db.session.execute(text(
            "CREATE TRIGGER audit_no_mod_row BEFORE UPDATE OR DELETE ON audit_log "
            "FOR EACH ROW EXECUTE FUNCTION audit_no_mod()"))
        db.session.execute(text("DROP TRIGGER IF EXISTS audit_no_truncate ON audit_log"))
        db.session.execute(text(
            "CREATE TRIGGER audit_no_truncate BEFORE TRUNCATE ON audit_log "
            "FOR EACH STATEMENT EXECUTE FUNCTION audit_no_mod()"))
    db.session.commit()