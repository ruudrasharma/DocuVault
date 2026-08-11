from . import db, login_manager, app
from flask_login import UserMixin
import hashlib
import pyotp
import uuid
import os

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    salt = db.Column(db.String(32), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    totp_secret = db.Column(db.String(32), nullable=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if 'salt' not in kwargs:
            self.salt = uuid.uuid4().hex

    def set_password(self, password):
        salted = password + self.salt
        self.password_hash = hashlib.sha256(salted.encode()).hexdigest()

    def check_password(self, password):
        salted = password + self.salt
        return self.password_hash == hashlib.sha256(salted.encode()).hexdigest()

    def generate_totp_secret(self):
        self.totp_secret = pyotp.random_base32()
        return self.totp_secret

    def get_totp_uri(self):
        if not self.totp_secret:
            self.generate_totp_secret()
        return pyotp.TOTP(self.totp_secret).provisioning_uri(name=self.username, issuer_name='SIH Prototype')

    def verify_totp(self, token):
        if not self.totp_secret:
            return False
        totp = pyotp.TOTP(self.totp_secret)
        return totp.verify(token)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def initialize_database():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', role='admin')
            admin.set_password('admin123')
            admin.generate_totp_secret()
            db.session.add(admin)
            db.session.commit()
            print("Default admin created.")