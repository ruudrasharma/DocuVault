#!/usr/bin/env python3
"""
scripts/reset_demo_accounts.py
==============================
Resets demo account credentials to clean, explicit passwords with fresh TOTP secrets.
Use this script for local testing and resetting dev accounts safely without hardcoded backdoors.
"""

import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db
from app.database import User

DEMO_ACCOUNTS = [
    ('admin', 'Admin@DocuVault2026!', 'admin'),
    ('institution', 'Inst@DocuVault2026!', 'institution'),
    ('verifier', 'Verify@DocuVault2026!', 'verifier'),
    ('citizen', 'Citizen@DocuVault2026!', 'citizen'),
    ('rudra', 'Rudra@DocuVault2026!', 'admin'),
]

def reset_accounts():
    with app.app_context():
        db.create_all()
        print("=" * 65)
        print("  DocuVault — Resetting Demo Accounts (Strict Hash Auth)")
        print("=" * 65)

        for username, password, role in DEMO_ACCOUNTS:
            user = User.query.filter_by(username=username).first()
            if not user:
                user = User(username=username, role=role, oauth_provider='local')
                db.session.add(user)
                action = "Created"
            else:
                user.role = role
                action = "Updated"

            user.set_password(password)
            totp_secret = user.generate_totp_secret()
            db.session.commit()

            print(f"[{action}] Username : {username}")
            print(f"         Role     : {role}")
            print(f"         Password : {password}")
            print(f"         TOTP Sec : {totp_secret}")
            print(f"         TOTP URI : {user.get_totp_uri()}")
            print("-" * 65)

        print("\nAll demo accounts have been reset with real, unique salted hashes.")
        print("TOTP bypass codes have been eliminated. Use authenticator apps or pyotp.")

if __name__ == '__main__':
    reset_accounts()
