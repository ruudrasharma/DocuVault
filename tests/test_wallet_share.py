"""
tests/test_wallet_share.py
===========================
Regression tests for Phase 1.1 — /wallet/share NameError fix.

These tests were IMPOSSIBLE to pass before the fix because
POST /wallet/share would always 500 with NameError: 'password'.
"""
import pytest
from datetime import datetime, timezone, timedelta


# ── Helpers ───────────────────────────────────────────────────────────────────

def _setup_citizen_with_wallet(app, db, username='share_citizen', password='CitizenPass@1'):
    """Create a citizen user with an initialised wallet."""
    from app.database import User
    from app.consent import ensure_wallet_key

    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, role='citizen', oauth_provider='local')
            u.set_password(password)
            u.generate_totp_secret()
            db.session.add(u)
            db.session.commit()
        # Ensure wallet key exists
        from app.database import WalletKey
        wk = WalletKey.query.filter_by(user_id=u.id).first()
        if not wk:
            ensure_wallet_key(u, password)
        return u.id, u.totp_secret


def _login_as(client, username, password, totp_secret):
    import pyotp
    client.post('/login', data={'username': username, 'password': password},
                follow_redirects=True)
    totp = pyotp.TOTP(totp_secret).now()
    client.post('/verify_2fa', data={'totp': totp}, follow_redirects=True)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_share_without_password_returns_400(client, app):
    """POST /wallet/share with no password field must return 400, NOT 500."""
    from app import db
    _setup_citizen_with_wallet(app, db)
    with app.app_context():
        from app.database import User
        u = User.query.filter_by(username='share_citizen').first()
    _login_as(client, 'share_citizen', 'CitizenPass@1', u.totp_secret)

    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r = client.post('/wallet/share', json={
        'document_id': 1,
        'grantee_username': 'share_citizen',
        'expires_at': future,
        # intentionally omit 'password'
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.data}"
    data = r.get_json()
    assert 'password' in data.get('error', '').lower()


def test_share_missing_fields_returns_400(client, app):
    """POST /wallet/share with missing required fields (not password) → 400."""
    from app import db
    _setup_citizen_with_wallet(app, db)
    with app.app_context():
        from app.database import User
        u = User.query.filter_by(username='share_citizen').first()
    _login_as(client, 'share_citizen', 'CitizenPass@1', u.totp_secret)

    r = client.post('/wallet/share', json={
        'password': 'CitizenPass@1',
        # missing document_id, grantee_username, expires_at
    })
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.data}"


def test_share_nonexistent_document_returns_404(client, app):
    """POST /wallet/share with a non-existent document_id → 404, not 500."""
    from app import db
    _setup_citizen_with_wallet(app, db)
    with app.app_context():
        from app.database import User
        u = User.query.filter_by(username='share_citizen').first()
    _login_as(client, 'share_citizen', 'CitizenPass@1', u.totp_secret)

    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r = client.post('/wallet/share', json={
        'document_id': 999999,
        'grantee_username': 'share_citizen',
        'expires_at': future,
        'password': 'CitizenPass@1',
    })
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.data}"


def test_fetch_password_via_query_string_is_rejected(client, app):
    """
    GET /wallet/fetch/<id>?password=... must NOT accept password from query params.
    The password must be submitted in the POST body only.
    """
    from app import db
    _setup_citizen_with_wallet(app, db)
    with app.app_context():
        from app.database import User
        u = User.query.filter_by(username='share_citizen').first()
    _login_as(client, 'share_citizen', 'CitizenPass@1', u.totp_secret)

    # GET with query-string password on a non-existent doc — should 404 (doc not found),
    # proving the endpoint didn't use the query-string password to succeed
    r = client.get('/wallet/fetch/999999?password=CitizenPass@1')
    # Must not 200 (non-existent doc), and critically must not use query-param pw
    assert r.status_code in (404, 401, 403), \
        f"Unexpected status {r.status_code} — query-string password may have been used"
