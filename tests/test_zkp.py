"""
tests/test_zkp.py
=================
Verification of real Non-Interactive Zero-Knowledge Proofs (Schnorr NIZK on BN128):
- Pedersen Commitment generation and consistency
- Completeness: Valid proofs verify successfully
- Soundness: Forged/tampered proofs are rejected
- Zero-knowledge property: Neither secret value nor blinding factor is revealed
"""

import secrets
import pytest
from app.zkp import (
    pedersen_commit,
    schnorr_prove,
    schnorr_verify,
    point_to_str,
    CURVE_ORDER,
)


def test_pedersen_commitment_properties():
    """Pedersen commitments are hiding and binding."""
    val = 12345678901234567890
    blinding1 = secrets.randbelow(CURVE_ORDER - 1) + 1
    blinding2 = secrets.randbelow(CURVE_ORDER - 1) + 1

    c1 = pedersen_commit(val, blinding1)
    c2 = pedersen_commit(val, blinding2)

    # Same value with different blinding produces different commitments (Hiding)
    assert point_to_str(c1) != point_to_str(c2)

    # Same value and same blinding produces identical commitment (Binding)
    c1_repeat = pedersen_commit(val, blinding1)
    assert point_to_str(c1) == point_to_str(c1_repeat)


def test_schnorr_nizk_completeness():
    """A validly generated Fiat-Shamir Schnorr proof always verifies (Completeness)."""
    secret_value = int("8e2906014cccee0bc4721c626671f0b565678240177b93a87c8eb32f33a3faba", 16)
    blinding = secrets.randbelow(CURVE_ORDER - 1) + 1

    proof = schnorr_prove(secret_value, blinding)
    assert isinstance(proof, dict)
    assert 'commitment' in proof
    assert 'e' in proof
    assert 'z1' in proof
    assert 'z2' in proof

    # Verify proof
    is_valid = schnorr_verify(proof)
    assert is_valid is True, "Valid Schnorr NIZK proof failed verification!"


def test_schnorr_nizk_soundness_rejection():
    """A forged or tampered Schnorr proof must fail verification (Soundness)."""
    secret_value = 9876543210
    blinding = secrets.randbelow(CURVE_ORDER - 1) + 1

    proof = schnorr_prove(secret_value, blinding)

    # Tamper with challenge e
    tampered_proof = dict(proof)
    tampered_proof['e'] = str((int(tampered_proof['e']) + 1) % CURVE_ORDER)
    assert schnorr_verify(tampered_proof) is False, "Tampered challenge was accepted!"

    # Tamper with response z1
    tampered_z1 = dict(proof)
    tampered_z1['z1'] = str((int(tampered_z1['z1']) + 42) % CURVE_ORDER)
    assert schnorr_verify(tampered_z1) is False, "Tampered response z1 was accepted!"


def test_zero_knowledge_privacy():
    """Assert secret value and blinding factor are not present anywhere in proof output."""
    raw_hash_hex = "8e2906014cccee0bc4721c626671f0b565678240177b93a87c8eb32f33a3faba"
    secret_value = int(raw_hash_hex, 16)
    blinding = 1337429999123456

    proof = schnorr_prove(secret_value, blinding)

    # Convert all proof values to strings for inspection
    proof_strings = [str(v) for v in proof.values()] + list(proof.keys())
    proof_dump = " ".join(proof_strings)

    assert str(secret_value) not in proof_dump
    assert str(blinding) not in proof_dump
    assert raw_hash_hex not in proof_dump
