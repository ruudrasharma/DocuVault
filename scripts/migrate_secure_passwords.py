#!/usr/bin/env python3
"""
scripts/migrate_secure_passwords.py
==================================
Identifies legacy accounts that were using backdoor password fallbacks or
missing salt/hashes, and forces password updates.
"""

import sys
import os
import hashlib
import secrets

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db
from app.database import User

KNOWN_FALLBACKS = [
    'Admin@1234', 'Rudra@1807', 'Ru1807#$', 'admin123', 'admin', 'rudra',
    'IIT@DocuVault1', 'BITS@DocuVault1', 'NIT@DocuVault1', 'instpass', 'Institute@1234',
    'Verify@1234', 'Verify@5678', 'verify123', 'password', '123456'
]

def migrate_passwords():
    with app.app_context():
        users = User.query.filter_by(oauth_provider='local').all()
        print(f"Scanning {len(users)} local user accounts for insecure passwords...")
        
        migrated_count = 0
        for user in users:
            is_insecure = False
            # Check if current hash matches any old fallback password without proper salt
            if not user.salt or not user.password_hash:
                is_insecure = True
            else:
                for fb in KNOWN_FALLBACKS:
                    test_salted = fb + user.salt
                    if user.password_hash == hashlib.sha256(test_salted.encode()).hexdigest():
                        is_insecure = True
                        break

            if is_insecure:
                new_temp_pass = f"DocuVault_{secrets.token_hex(4)}!"
                user.set_password(new_temp_pass)
                if not user.totp_secret:
                    user.generate_totp_secret()
                db.session.commit()
                print(f"[RESET REQUIRED] User: {user.username} -> Assigned temporary password: {new_temp_pass}")
                migrated_count += 1

        print(f"\nMigration complete. {migrated_count} account(s) updated to secure salted hashes.")

if __name__ == '__main__':
    migrate_passwords()
