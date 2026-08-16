"""
tests/conftest.py
=================
Provides Flask test client + isolated SQLite + isolated blockchain file
for every test session. Tests never touch production data.
"""
import os
import json
import tempfile
import pytest

# Point at a temp blockchain file BEFORE the app is imported
_tmp_chain_file = tempfile.NamedTemporaryFile(suffix='.json', delete=False)
_tmp_chain_file.write(b'[]')
_tmp_chain_file.close()

os.environ.setdefault('BLOCKCHAIN_FILE', _tmp_chain_file.name)
os.environ.setdefault('SECRET_KEY', 'test-secret-key-not-for-production')
os.environ.setdefault('APP_ENV', 'testing')


@pytest.fixture(scope='session')
def app():
    """Create application with temporary SQLite database."""
    _db_fd, _db_path = tempfile.mkstemp(suffix='.db')

    from app import app as flask_app, db

    flask_app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{_db_path}',
        'WTF_CSRF_ENABLED': False,           # disable CSRF for test POST calls
        'LOGIN_DISABLED': False,
        'SERVER_NAME': None,
    })

    with flask_app.app_context():
        db.create_all()
        _seed_test_users(db)

    yield flask_app

    # Teardown
    os.close(_db_fd)
    os.unlink(_db_path)
    os.unlink(_tmp_chain_file.name)


def _seed_test_users(db):
    """Create minimal users needed for smoke tests."""
    from app.database import User, initialize_database
    if not User.query.filter_by(username='test_admin').first():
        u = User(username='test_admin', role='admin', oauth_provider='local')
        u.set_password('TestAdmin@9999')
        u.generate_totp_secret()
        db.session.add(u)

    if not User.query.filter_by(username='test_institution').first():
        u = User(username='test_institution', role='institution', oauth_provider='local')
        u.set_password('TestInst@9999')
        u.generate_totp_secret()
        db.session.add(u)

    if not User.query.filter_by(username='test_verifier').first():
        u = User(username='test_verifier', role='verifier', oauth_provider='local')
        u.set_password('TestVerify@9999')
        u.generate_totp_secret()
        db.session.add(u)

    db.session.commit()


@pytest.fixture
def client(app):
    """Return a Flask test client."""
    return app.test_client()


@pytest.fixture
def auth_client(client, app):
    """Return a test client already logged in as test_admin (past login + 2FA)."""
    with app.app_context():
        from app.database import User
        user = User.query.filter_by(username='test_admin').first()
        secret = user.totp_secret
        import pyotp
        totp_code = pyotp.TOTP(secret).now()

    # Step 1: login
    client.post('/auth/login', data={
        'username': 'test_admin',
        'password': 'TestAdmin@9999',
    }, follow_redirects=True)

    # Step 2: 2FA
    client.post('/auth/verify_2fa', data={'code': totp_code}, follow_redirects=True)

    return client


@pytest.fixture
def inst_client(client, app):
    """Return a test client logged in as test_institution."""
    with app.app_context():
        from app.database import User
        user = User.query.filter_by(username='test_institution').first()
        secret = user.totp_secret
        import pyotp
        totp_code = pyotp.TOTP(secret).now()

    client.post('/auth/login', data={
        'username': 'test_institution',
        'password': 'TestInst@9999',
    }, follow_redirects=True)
    client.post('/auth/verify_2fa', data={'code': totp_code}, follow_redirects=True)
    return client


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a minimal valid PDF for upload tests."""
    pdf_path = tmp_path / 'test_cert.pdf'
    # Minimal valid PDF header
    pdf_path.write_bytes(
        b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n'
        b'2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n'
        b'3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n'
        b'xref\n0 4\n0000000000 65535 f\n'
        b'trailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF'
    )
    return pdf_path


@pytest.fixture
def sample_jpg(tmp_path):
    """Create a minimal valid JPEG for upload tests."""
    try:
        from PIL import Image
        img_path = tmp_path / 'test_cert.jpg'
        img = Image.new('RGB', (100, 100), color=(200, 200, 200))
        img.save(str(img_path), 'JPEG')
        return img_path
    except ImportError:
        # Fallback: minimal JPEG magic bytes
        jpg_path = tmp_path / 'test_cert.jpg'
        jpg_path.write_bytes(bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b'\x00' * 100 + bytes([0xFF, 0xD9]))
        return jpg_path
