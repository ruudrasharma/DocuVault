"""
tests/test_vc.py
================
Verification of W3C Verifiable Credentials:
- Issue signed VC
- Verify valid VC signature
- Tampered claims detection
- Mismatched issuer signature rejection
"""

import json
import pytest
from app.verifiable_credentials import issue_vc, verify_vc


def test_vc_issue_and_verify_roundtrip():
    """An issued Verifiable Credential verifies successfully with valid signature."""
    claims = {
        "studentName": "Rudra Sharma",
        "rollNumber": "26144112",
        "examination": "CBSE Secondary School Examination",
        "year": "2026",
        "result": "PASS"
    }
    issuer = "cbse_board"
    holder = "rudra"
    cert_hash = "8e2906014cccee0bc4721c626671f0b565678240177b93a87c8eb32f33a3faba"

    vc = issue_vc(claims, issuer, holder, cert_hash)
    assert isinstance(vc, dict)
    assert "proof" in vc
    assert vc["proof"]["type"] == "Ed25519Signature2020"

    is_valid, msg, extracted_claims = verify_vc(vc)
    assert is_valid is True, f"VC verification failed: {msg}"
    assert extracted_claims["studentName"] == "Rudra Sharma"
    assert extracted_claims["rollNumber"] == "26144112"


def test_tampered_vc_claims_rejected():
    """Tampering with claims in a VC must fail cryptographic verification."""
    claims = {"degree": "B.Tech Computer Science", "gpa": "9.5"}
    vc = issue_vc(claims, "iit_bombay", "student123", "a"*64)

    # Malicious modification of grade
    vc["credentialSubject"]["claims"]["gpa"] = "10.0"

    is_valid, msg, _ = verify_vc(vc)
    assert is_valid is False, "Tampered VC claims passed cryptographic verification!"
    assert "failed" in msg.lower() or "signature" in msg.lower()
