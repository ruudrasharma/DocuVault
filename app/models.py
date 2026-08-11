
from . import db, login_manager, app
from flask_login import UserMixin
from datetime import datetime, timezone
import hashlib
import pyotp
import uuid
import os
import json

key = Fernet.generate_key()
cipher_suite = Fernet(key)

def encrypt_data(data):
    return base64.b64encode(cipher_suite.encrypt(str(data).encode())).decode()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    totp_secret = db.Column(db.String(16), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

class CertificateRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hash_value = db.Column(db.String(64), nullable=False)
    institution = db.Column(db.String(100), nullable=False)
    is_valid = db.Column(db.Boolean, default=True)
    encrypted_metadata = db.Column(db.Text, nullable=True)

class VerifiableCredential(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(50), nullable=False, unique=True)
    hash_value = db.Column(db.String(64), nullable=False)
    vc_data = db.Column(db.Text, nullable=False)
    signature = db.Column(db.LargeBinary, nullable=False)

class AnalyticsLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    anomaly_score = db.Column(db.Float)
    institution = db.Column(db.String(100))
    outcome = db.Column(db.String(20))
