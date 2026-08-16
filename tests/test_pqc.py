"""
tests/test_pqc.py
=================
Tests for Post-Quantum Cryptography (ML-KEM-768 / Kyber768) module:
- Keypair generation
- Encapsulation & decapsulation shared-secret agreement
- Tamper detection / ciphertext corruption resistance
- NIST Hybrid secret combination
- Backward compatible wrappers
"""

import pytest
from app.pqc import (
    pqc_generate_keypair,
    pqc_encapsulate,
    pqc_decapsulate,
    hybrid_combine_secrets,
    pqc_encrypt,
    pqc_decrypt,
    is_pqc_available,
)


def test_pqc_keypair_generation():
    """Keypair generation produces non-empty public and private keys."""
    pub, priv = pqc_generate_keypair()
    assert isinstance(pub, bytes) and len(pub) > 0
    assert isinstance(priv, bytes) and len(priv) > 0
    assert pub != priv


def test_pqc_encapsulate_decapsulate_roundtrip():
    """Encapsulation against a public key decapsulates to the identical shared secret."""
    pub, priv = pqc_generate_keypair()
    ciphertext, sender_secret = pqc_encapsulate(pub)
    
    assert isinstance(ciphertext, bytes) and len(ciphertext) > 0
    assert isinstance(sender_secret, bytes) and len(sender_secret) == 32
    
    receiver_secret = pqc_decapsulate(priv, ciphertext)
    assert receiver_secret == sender_secret, "Decapsulated shared secret did not match encapsulated secret!"


def test_pqc_ciphertext_tampering_fails():
    """Tampering with a ciphertext byte must NOT produce the same shared secret."""
    pub, priv = pqc_generate_keypair()
    ciphertext, sender_secret = pqc_encapsulate(pub)
    
    # Flip the last byte of ciphertext
    tampered = bytearray(ciphertext)
    tampered[-1] ^= 0xFF
    tampered_ct = bytes(tampered)
    
    receiver_secret = pqc_decapsulate(priv, tampered_ct)
    assert receiver_secret != sender_secret, "Tampered ciphertext unexpectedly produced the original shared secret!"


def test_hybrid_combine_secrets():
    """Hybrid secret combination via HKDF produces a 32-byte AES DEK."""
    rsa_secret = b"classical-rsa-secret-key-32bytes"
    pqc_secret = b"quantum-resistant-secret-32bytes"
    
    combined_dek = hybrid_combine_secrets(rsa_secret, pqc_secret)
    assert isinstance(combined_dek, bytes) and len(combined_dek) == 32
    
    # Different inputs produce different outputs
    different_pqc = b"different-quantum-secret-32bytes"
    different_dek = hybrid_combine_secrets(rsa_secret, different_pqc)
    assert combined_dek != different_dek


def test_pqc_encrypt_decrypt_roundtrip():
    """End-to-end encryption and decryption of string payload."""
    message = "DocuVault Quantum Safe Confidential Record 2026"
    encrypted, key = pqc_encrypt(message)
    decrypted = pqc_decrypt(encrypted, key)
    assert decrypted == message
