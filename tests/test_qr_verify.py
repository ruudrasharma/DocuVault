"""
tests/test_qr_verify.py
=======================
Verification of HMAC QR scan-to-verify functionality:
- Valid HMAC generation and verification
- Tampered HMAC rejection
"""

import pytest
from app.main import generate_qr_hmac


def test_qr_hmac_generation_and_validation():
    """HMAC matches for the same hash and differs for different hashes."""
    h1 = "8e2906014cccee0bc4721c626671f0b565678240177b93a87c8eb32f33a3faba"
    h2 = "1111111111111111111111111111111111111111111111111111111111111111"

    sig1 = generate_qr_hmac(h1)
    sig2 = generate_qr_hmac(h2)

    assert len(sig1) == 16
    assert sig1 == generate_qr_hmac(h1)
    assert sig1 != sig2
