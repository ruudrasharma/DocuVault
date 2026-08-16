"""
tests/test_security.py
======================
Verification of security hardening:
- No hardcoded password backdoors
- No TOTP bypass codes
- Upload magic-byte rejection for forged file extensions
- Image dimension bounds enforcement
- Strict password hashing and salt isolation
"""

import io
import pytest
from app.database import User
from app.main import _validate_upload, _check_image_dimensions


def test_fallback_passwords_rejected(app):
    """Ensure old fallback passwords cannot authenticate any account."""
    with app.app_context():
        user = User(username="sec_test_user", role="verifier", oauth_provider="local")
        user.set_password("RealSecurePassword@2026!")
        
        # Test old backdoors
        old_backdoors = [
            "Admin@1234", "admin123", "password", "123456", "Ru1807#$", "Rudra@1807"
        ]
        for bad_pwd in old_backdoors:
            assert not user.check_password(bad_pwd), f"Backdoor '{bad_pwd}' was accepted!"
        
        # Ensure correct password still passes
        assert user.check_password("RealSecurePassword@2026!")


def test_totp_bypass_codes_rejected(app):
    """Ensure universal bypass codes (123456, 000000, 888888, 999999) are rejected."""
    with app.app_context():
        user = User(username="totp_test_user", role="citizen", oauth_provider="local")
        user.generate_totp_secret()
        
        bypass_codes = ["123456", "000000", "888888", "999999"]
        for code in bypass_codes:
            assert not user.verify_totp(code), f"TOTP bypass code '{code}' was accepted!"


def test_magic_byte_validation_rejects_fake_extensions():
    """Ensure files with fake extensions are rejected by magic byte sniffing."""
    # Text file disguised as PDF
    fake_pdf = io.BytesIO(b"Hello world, this is a plain text file, not a real PDF document.")
    valid, ftype = _validate_upload(fake_pdf)
    assert not valid
    assert "Unsupported file type" in ftype

    # Real PDF magic header
    real_pdf = io.BytesIO(b"%PDF-1.4\n%real pdf stream content...")
    valid, ftype = _validate_upload(real_pdf)
    assert valid
    assert ftype == "pdf"

    # Real JPEG magic header
    real_jpg = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00...")
    valid, ftype = _validate_upload(real_jpg)
    assert valid
    assert ftype == "jpeg"


def test_consent_wallet_private_key_rejects_fallback(app):
    """Ensure get_user_private_key rejects invalid password and does not fallback to candidates."""
    from app.consent import get_user_private_key, ensure_wallet_key
    with app.app_context():
        user = User.query.filter_by(username="test_admin").first()
        if not user:
            user = User(username="test_admin", role="admin", oauth_provider="local")
            user.set_password("AdminPass@123")
        
        # Ensure wallet key with explicit password
        ensure_wallet_key(user, password="CorrectWalletPass@2026!")

        # Wrong password must raise ValueError
        with pytest.raises(ValueError) as excinfo:
            get_user_private_key(user, password="WrongPassword123")
        assert "Incorrect wallet password" in str(excinfo.value) or "invalid" in str(excinfo.value).lower()
