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
    role = db.Column(db.String(20), nullable=False)            # admin | institution | verifier
    totp_secret = db.Column(db.String(32), nullable=True)

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
        if not self.password_hash or not self.salt:
            return False
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
        if not self.totp_secret:
            return False
        totp = pyotp.TOTP(self.totp_secret)
        return totp.verify(token, valid_window=2)


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


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def initialize_database():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', role='admin', oauth_provider='local')
            admin.set_password('Admin@1234')
            admin.generate_totp_secret()
            db.session.add(admin)
            db.session.commit()
            print("Default admin created — username: admin / password: Admin@1234")