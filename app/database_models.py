"""
app/database_models.py — Blockchain-Index Model
================================================
Contains ONLY CertificateRecord — a lightweight SQL index mapping
certificate hashes to issuer metadata, used by the upload/verify pipeline.

All other models (User, VerifiableCredential, AnalyticsLog, AuditLog, etc.)
live in app/database.py and must be imported from there.

NOTE: Do NOT re-add User, VerifiableCredential, or AnalyticsLog here —
they are canonical in database.py and duplicating them causes SQLAlchemy
mapper conflicts and broken password-checking behavior.
"""

from . import db


class CertificateRecord(db.Model):
    """
    Lightweight SQL index for documents recorded on the blockchain.
    Stores enough metadata for fast hash-based lookups without duplicating
    the full document content (which lives in Document + encrypted blobs).
    """
    __tablename__ = 'certificate_record'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    hash_value = db.Column(db.String(64), nullable=False, index=True)
    institution = db.Column(db.String(100), nullable=False)
    is_valid = db.Column(db.Boolean, default=True)
    encrypted_metadata = db.Column(db.Text, nullable=True)