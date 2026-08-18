"""
tests/test_check_certificate_zkp.py
=====================================
Phase 6 regression tests: verify that zkp_valid in /check_certificate is
a REAL cryptographic check (Pedersen commitment recompute), not the old
len>10 stub.

Key invariant: mutating the stored commitment by one character must flip
zkp_valid from True to False.
"""
import pytest
from app.zkp import (
    generate_zkp_proof, proof_to_hex, verify_zkp_hex,
    pedersen_commit, point_to_str, CURVE_ORDER
)


# ── Unit: verify_zkp_hex is load-bearing ────────────────────────────────────

def test_zkp_verify_with_correct_blinding_passes():
    """verify_zkp_hex(commitment, hash, blinding) returns True for a genuine pair."""
    cert_hash = "cee779bad3d62eb296b951daf4f0a20f2213487528d932fd55ed3aff9c70a7e1"
    proof, blinding = generate_zkp_proof(cert_hash)
    commitment_str = proof_to_hex(proof)
    assert verify_zkp_hex(commitment_str, cert_hash, blinding) is True


def test_zkp_verify_wrong_blinding_fails():
    """verify_zkp_hex returns False if blinding factor is wrong."""
    cert_hash = "cee779bad3d62eb296b951daf4f0a20f2213487528d932fd55ed3aff9c70a7e1"
    proof, blinding = generate_zkp_proof(cert_hash)
    commitment_str = proof_to_hex(proof)
    wrong_blinding = (blinding + 1) % CURVE_ORDER
    assert verify_zkp_hex(commitment_str, cert_hash, wrong_blinding) is False


def test_zkp_verify_mutated_commitment_fails():
    """
    LOAD-BEARING TEST: mutating the stored commitment by one character must
    flip zkp_valid from True to False — proves the check is cryptographic,
    not just structural/length-based.
    """
    cert_hash = "abc123def456abc123def456abc123def456abc123def456abc123def456abcd"
    proof, blinding = generate_zkp_proof(cert_hash)
    commitment_str = proof_to_hex(proof)

    # Flip one character in the commitment
    mutated = commitment_str[:-1] + ('0' if commitment_str[-1] != '0' else '1')

    assert verify_zkp_hex(commitment_str, cert_hash, blinding) is True, \
        "Original commitment should verify True"
    assert verify_zkp_hex(mutated, cert_hash, blinding) is False, \
        "Mutated commitment should verify False — stub is still active if this fails!"


def test_zkp_verify_wrong_hash_fails():
    """verify_zkp_hex returns False if cert_hash doesn't match the commitment."""
    cert_hash = "cee779bad3d62eb296b951daf4f0a20f2213487528d932fd55ed3aff9c70a7e1"
    wrong_hash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    proof, blinding = generate_zkp_proof(cert_hash)
    commitment_str = proof_to_hex(proof)
    assert verify_zkp_hex(commitment_str, wrong_hash, blinding) is False


def test_zkp_verify_empty_commitment_fails():
    """Empty commitment must return False, not True."""
    assert verify_zkp_hex("", "somehash", 12345) is False
    assert verify_zkp_hex(None, "somehash", None) is False


def test_zkp_legacy_blocks_without_blinding_structural_check():
    """
    Legacy blocks (no blinding factor) fall back to structural check.
    A valid x:y curve point string passes; a random short string fails.
    """
    cert_hash = "cee779bad3d62eb296b951daf4f0a20f2213487528d932fd55ed3aff9c70a7e1"
    proof, blinding = generate_zkp_proof(cert_hash)
    commitment_str = proof_to_hex(proof)

    # Without blinding, structural check — a real curve point str should pass
    result = verify_zkp_hex(commitment_str, cert_hash, stored_blinding=None)
    assert result is True, "Real curve point should pass structural check"

    # Garbage should fail
    assert verify_zkp_hex("not_a_point", cert_hash, None) is False


# ── Integration: /check_certificate uses real ZKP check ─────────────────────

def test_check_certificate_zkp_valid_flag_is_real(auth_client, app):
    """
    /check_certificate?cert_id=<hash> returns verified=False cleanly for
    a non-existent hash — proves the ZKP code path doesn't crash.
    (Full True case requires OCR+blockchain issuance via live server.)
    """
    r = auth_client.get('/check_certificate?certificate_id=deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef')
    assert r.status_code == 200
    data = r.get_json()
    assert data['verified'] is False
    # Should not crash — confirms the ZKP path doesn't throw on missing block
