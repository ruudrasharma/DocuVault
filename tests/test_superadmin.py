"""
tests/test_superadmin.py
========================
Verification of Superadmin Tier & Governance Architecture:
- Server-side route-level protected account enforcement (is_protected=True)
- Concealment of superadmin from ordinary admin user queries
- Immutable AuditLog logging
- Step-up 2FA validation
"""

import time
import pytest
from app.database import User, AuditLog, db


def test_protected_account_cannot_be_deleted(app, client):
    """Protected superadmin account cannot be deleted via admin_delete_user endpoint."""
    with app.app_context():
        superadmin = User.query.filter_by(username='test_superadmin_root').first()
        if not superadmin:
            superadmin = User(
                username='test_superadmin_root',
                role='superadmin',
                oauth_provider='local',
                is_protected=True,
                google_email='rudraksharma187@gmail.com'
            )
            superadmin.set_password('SuperAdminPass@2026!')
            db.session.add(superadmin)
            db.session.commit()
        superadmin_id = superadmin.id

    with client.session_transaction() as sess:
        sess['user_id'] = 999  # Normal admin
        sess['role'] = 'admin'
        sess['username'] = 'normal_admin'
        sess['verified'] = True

    # Attempt to delete protected superadmin
    r = client.post(f'/admin/delete-user/{superadmin_id}')
    assert r.status_code == 403, f"Expected 403, got {r.status_code}"
    data = r.get_json()
    assert "Protected" in data.get('error', '')


def test_superadmin_hidden_from_ordinary_admin_list(app, client):
    """admin_users endpoint excludes accounts with role='superadmin' or is_protected=True."""
    with app.app_context():
        # Ensure a superadmin and a normal verifier exist
        sa = User.query.filter_by(username='explicit_superadmin').first()
        if not sa:
            sa = User(username='explicit_superadmin', role='superadmin', is_protected=True)
            sa.set_password('SuperPass@999')
            db.session.add(sa)
        
        ov = User.query.filter_by(username='ordinary_verifier').first()
        if not ov:
            ov = User(username='ordinary_verifier', role='verifier', is_protected=False)
            ov.set_password('Pass@1234')
            db.session.add(ov)
        db.session.commit()

    with client.session_transaction() as sess:
        sess['user_id'] = 999
        sess['role'] = 'admin'
        sess['username'] = 'normal_admin'
        sess['verified'] = True

    r = client.get('/admin/users')
    assert r.status_code == 200
    users = r.get_json()
    usernames = [u['username'] for u in users]
    roles = [u['role'] for u in users]

    assert 'explicit_superadmin' not in usernames, "Superadmin was leaked to ordinary admin users!"
    assert 'superadmin' not in roles, "Superadmin role appeared in ordinary admin query!"
    assert 'ordinary_verifier' in usernames



def test_audit_log_records_actions(app):
    """AuditLog accurately stores action records."""
    with app.app_context():
        initial_count = AuditLog.query.count()
        audit = AuditLog(
            actor_username="test_superadmin_root",
            action="TEST_PROTECTED_ACTION",
            target="user:12",
            ip_address="127.0.0.1",
            details_json='{"status": "success"}'
        )
        db.session.add(audit)
        db.session.commit()

        assert AuditLog.query.count() == initial_count + 1
        fetched = AuditLog.query.filter_by(action="TEST_PROTECTED_ACTION").first()
        assert fetched is not None
        assert fetched.actor_username == "test_superadmin_root"


def test_stepup_2fa_sliding_window(client, app):
    """reverify_2fa requires fresh 2FA verification when window exceeds 300 seconds."""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'superadmin'
        sess['username'] = 'rudra'
        sess['verified'] = True
        # Set last verification to 10 minutes ago (600s)
        sess['sensitive_verified_at'] = time.time() - 600

    r = client.post('/superadmin/blockchain/reverify', headers={'Accept': 'application/json'})
    assert r.status_code == 403
    data = r.get_json()
    assert data.get('error') == 'STEPUP_2FA_REQUIRED'

    # Now simulate fresh step-up 2FA
    with client.session_transaction() as sess:
        sess['sensitive_verified_at'] = time.time()

    r = client.post('/superadmin/blockchain/reverify', headers={'Accept': 'application/json'})
    assert r.status_code == 200
    assert r.get_json().get('success') is True
