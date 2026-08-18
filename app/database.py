from . import db, login_manager, app
from flask_login import UserMixin
import hashlib
import pyotp
import uuid
import os
from datetime import datetime, timezone, timedelta

class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=True)   # nullable for OAuth users
    salt = db.Column(db.String(32), nullable=True)             # nullable for OAuth users
    role = db.Column(db.String(20), nullable=False)            # superadmin | admin | institution | verifier | citizen
    totp_secret = db.Column(db.String(32), nullable=True)
    is_protected = db.Column(db.Boolean, default=False, nullable=False)  # Immutable root protection

    # Google OAuth fields
    oauth_provider = db.Column(db.String(20), nullable=False, default='local')  # 'local' | 'google'
    google_id = db.Column(db.String(100), nullable=True, unique=True)
    google_email = db.Column(db.String(120), nullable=True)
    google_name = db.Column(db.String(120), nullable=True)
    google_avatar = db.Column(db.String(500), nullable=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if 'salt' not in kwargs and kwargs.get('oauth_provider', 'local') == 'local':
            self.salt = uuid.uuid4().hex

    def set_password(self, password):
        if not self.salt:
            self.salt = uuid.uuid4().hex
        salted = password + self.salt
        self.password_hash = hashlib.sha256(salted.encode()).hexdigest()

    def check_password(self, password):
        """Strict hash-only comparison. No fallbacks, no backdoors."""
        if not password or not self.password_hash or not self.salt:
            return False
        password = str(password).strip()
        salted = password + self.salt
        return self.password_hash == hashlib.sha256(salted.encode()).hexdigest()

    def generate_totp_secret(self):
        self.totp_secret = pyotp.random_base32()
        return self.totp_secret

    def get_totp_uri(self):
        if not self.totp_secret:
            self.generate_totp_secret()
        return pyotp.TOTP(self.totp_secret).provisioning_uri(
            name=self.username, issuer_name='DocuVault'
        )

    def verify_totp(self, token):
        """Strict pyotp-only verification. No bypass codes."""
        if not token or not self.totp_secret:
            return False
        token = str(token).strip()
        return pyotp.TOTP(self.totp_secret).verify(token, valid_window=1)


class PendingAccount(db.Model):
    """Holds accounts awaiting 2FA confirmation before being created."""
    __tablename__ = 'pending_account'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    salt = db.Column(db.String(32), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    totp_secret = db.Column(db.String(32), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc) + timedelta(hours=1))

    def is_expired(self):
        return datetime.now(timezone.utc) > self.expires_at.replace(tzinfo=timezone.utc)

    def verify_otp(self, token):
        totp = pyotp.TOTP(self.totp_secret)
        return totp.verify(token, valid_window=2)


class Document(db.Model):
    __tablename__ = 'document'
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    issuer_username = db.Column(db.String(120), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    doc_type = db.Column(db.String(100), nullable=True)
    encrypted_blob_path = db.Column(db.String(500), nullable=False)   # path under data/wallet_blobs/
    iv = db.Column(db.String(64), nullable=False)                    # AES-GCM nonce, hex
    wrapped_dek_owner = db.Column(db.Text, nullable=False)           # DEK encrypted to owner pubkey, b64
    cert_hash = db.Column(db.String(64), nullable=False)             # sha256(encrypted_blob)
    block_index = db.Column(db.Integer, nullable=False)              # issuance block on chain
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class AccessGrant(db.Model):
    __tablename__ = 'access_grant'
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=False)
    grantee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    wrapped_dek_grantee = db.Column(db.Text, nullable=False)         # DEK encrypted to grantee pubkey, b64
    granted_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    granted_block_index = db.Column(db.Integer, nullable=False)      # 'grant' block on chain
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked = db.Column(db.Boolean, default=False)
    revoked_block_index = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class WalletKey(db.Model):
    __tablename__ = 'wallet_key'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    public_key_pem = db.Column(db.Text, nullable=False)
    encrypted_private_key = db.Column(db.Text, nullable=False)  # RSA private key encrypted w/ password-derived key
    kdf_salt = db.Column(db.String(64), nullable=False)
    # Post-Quantum Cryptography (ML-KEM-768 / Kyber) fields
    pqc_public_key = db.Column(db.LargeBinary, nullable=True)
    pqc_encrypted_private_key = db.Column(db.LargeBinary, nullable=True)
    # Encrypted 128-d face embedding vector
    face_embedding_encrypted = db.Column(db.LargeBinary, nullable=True)


class InstitutionSigningKey(db.Model):
    """
    Ed25519 signing keypair for institution accounts.
    Used to sign every document block they issue on the blockchain.
    Private key is AES-GCM-encrypted with the institution's password via PBKDF2.
    """
    __tablename__ = 'institution_signing_key'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    public_key_hex = db.Column(db.String(128), nullable=False)    # Ed25519 public key, hex
    encrypted_private_key = db.Column(db.Text, nullable=False)    # AES-GCM encrypted private key, b64
    kdf_salt = db.Column(db.String(64), nullable=False)           # PBKDF2 salt, hex


class VerifiableCredential(db.Model):
    __tablename__ = 'verifiable_credential'
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=True)
    cert_hash = db.Column(db.String(64), nullable=False, index=True)
    issuer_username = db.Column(db.String(120), nullable=False)
    holder_username = db.Column(db.String(120), nullable=False)
    vc_json = db.Column(db.Text, nullable=False)
    signature_hex = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class AnalyticsLog(db.Model):
    __tablename__ = 'analytics_log'
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(50), nullable=False)  # 'upload', 'verify', 'grant', 'revoke'
    username = db.Column(db.String(120), nullable=True)
    cert_hash = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(50), nullable=False)      # 'verified', 'rejected', 'anomaly_detected', etc.
    anomaly_score = db.Column(db.Float, default=0.0)
    details_json = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class AuditLog(db.Model):
    """Immutable audit trail for all sensitive administrative and system actions."""
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    actor_username = db.Column(db.String(120), nullable=False)
    action = db.Column(db.String(100), nullable=False)  # e.g., 'DELETE_USER', 'MODIFY_DB_RECORD', 'STEPUP_2FA_AUTH'
    target = db.Column(db.String(255), nullable=True)   # e.g., 'user:5', 'document:12', 'blockchain:reverify'
    ip_address = db.Column(db.String(45), nullable=True)
    details_json = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)





@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def initialize_database():
    """Create tables and seed an admin account only if none exist.
    The default password is printed ONCE at first boot.
    Run scripts/reset_demo_accounts.py to change it.
    """
    import secrets
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            # Generate a strong random password on first boot
            first_boot_password = secrets.token_urlsafe(16)
            admin = User(username='admin', role='admin', oauth_provider='local')
            admin.set_password(first_boot_password)
            admin.generate_totp_secret()
            db.session.add(admin)
            db.session.commit()
            print("="*60)
            print(f"[DocuVault] Admin account created.")
            print(f"  Username : admin")
            print(f"  Password : {first_boot_password}")
            print(f"  TOTP URI : {admin.get_totp_uri()}")
            print("  Save these credentials — this message won't appear again.")
            print("="*60)