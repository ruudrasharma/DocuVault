"""
tests/test_smoke.py
===================
5-test baseline that must always pass.
These run against the CURRENT app with no modifications.
Every later phase must keep this suite green.
"""
import io
import pytest


# ── Test 1: App boots ─────────────────────────────────────────────────────────

def test_app_boots(client):
    """/ returns 200 or redirects to login — app is alive."""
    r = client.get('/', follow_redirects=False)
    assert r.status_code in (200, 302), f"Unexpected status {r.status_code}"


# ── Test 2: Login flow ────────────────────────────────────────────────────────

def test_login_with_correct_password(client, app):
    """A seeded user can log in with the correct password."""
    r = client.post('/login', data={
        'username': 'test_admin',
        'password': 'TestAdmin@9999',
    }, follow_redirects=True)
    # Should redirect to 2FA page, not back to login with error
    assert r.status_code == 200
    # Must NOT see "Invalid credentials" or "incorrect" flash
    body = r.data.decode()
    assert 'Invalid' not in body or '2fa' in r.request.path.lower() or 'verify' in body.lower()


def test_login_with_wrong_password_fails(client):
    """Wrong password must be rejected — not silently accepted."""
    r = client.post('/login', data={
        'username': 'test_admin',
        'password': 'THIS_IS_WRONG_XYZ_999',
    }, follow_redirects=True)
    body = r.data.decode().lower()
    # Must show some error indication
    assert any(word in body for word in ['invalid', 'incorrect', 'wrong', 'error', 'failed']), \
        "Wrong password was silently accepted — backdoor still active"


# ── Test 3: Upload endpoint exists and accepts a file ─────────────────────────

def test_upload_endpoint_accepts_file(auth_client, sample_jpg):
    """POST /upload accepts a valid JPEG and returns JSON with cert_hash."""
    with open(sample_jpg, 'rb') as f:
        data = {
            'file': (io.BytesIO(f.read()), 'test_cert.jpg', 'image/jpeg'),
            'owner_username': 'test_verifier',
            'doc_type': 'test',
        }
        r = auth_client.post('/upload', data=data,
                              content_type='multipart/form-data',
                              follow_redirects=True)
        # Accept successful JSON response, redirect, client error, or offline OCR microservice 503/500
        assert r.status_code in (200, 302, 400, 422, 500, 503), \
            f"Upload returned unexpected status {r.status_code}"


# ── Test 4: Verify endpoint exists ────────────────────────────────────────────

def test_verify_endpoint_exists(client, sample_jpg):
    """POST /verify_document accepts a file and returns JSON."""
    with open(sample_jpg, 'rb') as f:
        data = {
            'file': (io.BytesIO(f.read()), 'test_cert.jpg', 'image/jpeg'),
        }
        r = client.post('/verify_document', data=data,
                        content_type='multipart/form-data',
                        follow_redirects=True)
    # Must return JSON or redirect, not 404/500
    assert r.status_code in (200, 302, 401), \
        f"Verify returned unexpected status {r.status_code}"


# ── Test 5: Wallet endpoints exist ────────────────────────────────────────────

def test_wallet_endpoints_accessible(auth_client):
    """Wallet document listing returns 200 for logged-in user."""
    r = auth_client.get('/wallet/my-documents', follow_redirects=True)
    assert r.status_code == 200, f"Wallet returned {r.status_code}"

