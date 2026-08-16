#!/usr/bin/env python3
"""
scripts/seed_superadmin.py
==========================
Provisions or updates the root Superadmin account with server-side protection.
- Sets role='superadmin' and is_protected=True
- Binds google_email for direct OAuth resolution
- Generates TOTP secret
- Uses env vars (SUPERADMIN_USER, SUPERADMIN_PASS, SUPERADMIN_EMAIL) or interactive prompt
"""

import sys
import os
import getpass
import secrets

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db
from app.database import User, AuditLog


def seed_superadmin():
    username = os.environ.get('SUPERADMIN_USER', 'rudra').strip()
    email = os.environ.get('SUPERADMIN_EMAIL', 'rudraksharma187@gmail.com').strip()
    password = os.environ.get('SUPERADMIN_PASS')

    if not password:
        if sys.stdin.isatty():
            password = getpass.getpass(f"Enter password for superadmin '{username}': ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                print("Error: Passwords do not match.")
                sys.exit(1)
        else:
            password = f"SuperAdmin_{secrets.token_urlsafe(12)}!"

    with app.app_context():
        db.create_all()
        user = User.query.filter((User.username == username) | (User.google_email == email)).first()

        if not user:
            user = User(
                username=username,
                role='superadmin',
                oauth_provider='local',
                is_protected=True,
                google_email=email,
                google_name='Rudra Sharma (Superadmin)'
            )
            db.session.add(user)
            action_desc = "CREATED"
        else:
            user.username = username
            user.role = 'superadmin'
            user.is_protected = True
            user.google_email = email
            user.google_name = 'Rudra Sharma (Superadmin)'
            action_desc = "UPGRADED"

        user.set_password(password)
        if not user.totp_secret:
            user.generate_totp_secret()

        # Record in AuditLog
        audit = AuditLog(
            actor_username="SYSTEM_CLI",
            action="SEED_SUPERADMIN",
            target=f"user:{user.username}",
            ip_address="127.0.0.1",
            details_json=f'{{"role": "superadmin", "is_protected": true, "google_email": "{email}"}}'
        )
        db.session.add(audit)
        db.session.commit()

        print("=" * 68)
        print(f"  [DocuVault] Superadmin Account {action_desc} Successfully")
        print("=" * 68)
        print(f"  Username     : {user.username}")
        print(f"  Role         : {user.role}")
        print(f"  Protected    : {user.is_protected}")
        print(f"  Google Email : {user.google_email}")
        print(f"  Password     : {'*' * len(password)} (saved securely)")
        print(f"  TOTP Secret  : {user.totp_secret}")
        print(f"  TOTP URI     : {user.get_totp_uri()}")
        print("=" * 68)
        print("Superadmin is protected at route-level from deletion and tampering.")


if __name__ == '__main__':
    seed_superadmin()
