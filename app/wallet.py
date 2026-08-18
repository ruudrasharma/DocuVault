"""
app/wallet.py — Citizen Wallet Cryptographic Key Management
============================================================
Handles RSA keypair generation, password-derived encryption of private keys,
and DEK (Data Encryption Key) envelope wrapping/unwrapping.
"""

import os
import base64
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PBKDF2_ITERATIONS = 200_000

def generate_keypair() -> tuple[str, str]:
    """Generate RSA-2048 keypair, return (public_pem_str, private_pem_str)."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')

    return public_pem, private_pem

def derive_key_from_password(password: str, salt: bytes) -> bytes:
    """Derive 32-byte key from password using PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode('utf-8'))

def encrypt_private_key(private_pem: str, password: str) -> tuple[str, str]:
    """
    Encrypt private key PEM with a password-derived key using AES-GCM.
    Returns (ciphertext_b64, salt_hex).
    """
    salt = os.urandom(16)
    key = derive_key_from_password(password, salt)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, private_pem.encode('utf-8'), None)
    
    # Store nonce + ciphertext together
    payload = nonce + ciphertext
    return base64.b64encode(payload).decode('utf-8'), salt.hex()

def decrypt_private_key(ciphertext_b64: str, salt_hex: str, password: str) -> str:
    """
    Decrypt private key PEM using password and salt.
    Raises ValueError if password is wrong or decryption fails.
    """
    try:
        salt = bytes.fromhex(salt_hex)
        payload = base64.b64decode(ciphertext_b64.encode('utf-8'))
        nonce = payload[:12]
        ciphertext = payload[12:]
        
        key = derive_key_from_password(password, salt)
        aesgcm = AESGCM(key)
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        return decrypted_bytes.decode('utf-8')
    except Exception as exc:
        raise ValueError("Invalid password or corrupted key storage.") from exc

def encrypt_bytes(data_bytes: bytes, password: str, salt: bytes) -> bytes:
    """Encrypt raw bytes using a password-derived key and AES-GCM. Returns nonce + ciphertext."""
    key = derive_key_from_password(password, salt)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data_bytes, None)
    return nonce + ciphertext

def decrypt_bytes(payload: bytes, password: str, salt: bytes) -> bytes:
    """Decrypt payload (nonce + ciphertext) using a password-derived key."""
    key = derive_key_from_password(password, salt)
    aesgcm = AESGCM(key)
    nonce = payload[:12]
    ciphertext = payload[12:]
    return aesgcm.decrypt(nonce, ciphertext, None)

def wrap_dek(dek: bytes, public_pem: str) -> str:
    """Wrap a DEK (Data Encryption Key) using recipient's public key (RSA-OAEP). Returns b64."""
    public_key = serialization.load_pem_public_key(public_pem.encode('utf-8'))
    wrapped = public_key.encrypt(
        dek,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return base64.b64encode(wrapped).decode('utf-8')

def unwrap_dek(wrapped_b64: str, private_pem: str) -> bytes:
    """Unwrap a wrapped DEK using private key (RSA-OAEP). Returns raw dek bytes."""
    private_key = serialization.load_pem_private_key(private_pem.encode('utf-8'), password=None)
    wrapped = base64.b64decode(wrapped_b64.encode('utf-8'))
    dek = private_key.decrypt(
        wrapped,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    return dek


# ── Phase 5: Hybrid PQC + RSA DEK wrapping ────────────────────────────────────
# Format: 'v2:<pqc_ct_b64>:<nonce_b64>:<pqc_wrapped_rsa_ct_b64>'
# Security: both PQC (ML-KEM-768 or X25519) AND RSA must be broken to recover the DEK.

_V2_PREFIX = 'v2:'

def hybrid_wrap_dek(dek: bytes, rsa_public_pem: str, pqc_public_key_bytes: bytes) -> str:
    """
    Hybrid-wrap a DEK with RSA-OAEP + PQC (ML-KEM-768 / X25519 fallback).
    Returns a versioned 'v2:...' string.

    Layer 1 (RSA-OAEP): wraps the DEK — classical protection.
    Layer 2 (PQC AES-GCM): additionally encrypts the RSA-wrapped blob using
    the PQC shared secret, so an attacker must break BOTH to recover the DEK.
    """
    from .pqc import pqc_encapsulate
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    # Layer 1: RSA-OAEP wrap the DEK
    rsa_wrapped_b64 = wrap_dek(dek, rsa_public_pem)
    rsa_wrapped_bytes = base64.b64decode(rsa_wrapped_b64)

    # Layer 2: PQC encapsulate to get a shared secret, then AES-GCM encrypt the RSA-wrapped blob
    pqc_ciphertext, pqc_shared_secret = pqc_encapsulate(pqc_public_key_bytes)
    nonce = os.urandom(12)
    aesgcm = AESGCM(pqc_shared_secret[:32])
    pqc_encrypted_rsa_wrapped = aesgcm.encrypt(nonce, rsa_wrapped_bytes, None)

    # Serialise: v2:<pqc_ct>:<nonce>:<pqc_encrypted_rsa_wrapped>
    return (
        _V2_PREFIX
        + base64.b64encode(pqc_ciphertext).decode()
        + ':'
        + base64.b64encode(nonce).decode()
        + ':'
        + base64.b64encode(pqc_encrypted_rsa_wrapped).decode()
    )


def hybrid_unwrap_dek(wrapped_str: str, rsa_private_pem: str, pqc_private_key_bytes: bytes) -> bytes:
    """
    Unwrap a hybrid-wrapped DEK. Handles both v2: (hybrid) and legacy RSA-only formats.

    v2 format: peel PQC AES-GCM layer first, then RSA-OAEP layer.
    Legacy (no v2: prefix): fall back to plain unwrap_dek() for backwards compat.
    """
    from .pqc import pqc_decapsulate
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not wrapped_str.startswith(_V2_PREFIX):
        # Legacy RSA-only wrapped DEK — backwards compatible
        return unwrap_dek(wrapped_str, rsa_private_pem)

    parts = wrapped_str[len(_V2_PREFIX):].split(':')
    if len(parts) != 3:
        raise ValueError("Malformed v2 hybrid-wrapped DEK.")

    pqc_ciphertext = base64.b64decode(parts[0])
    nonce = base64.b64decode(parts[1])
    pqc_encrypted_rsa_wrapped = base64.b64decode(parts[2])

    # Recover PQC shared secret
    pqc_shared_secret = pqc_decapsulate(pqc_private_key_bytes, pqc_ciphertext)

    # Decrypt the RSA-wrapped blob
    aesgcm = AESGCM(pqc_shared_secret[:32])
    rsa_wrapped_bytes = aesgcm.decrypt(nonce, pqc_encrypted_rsa_wrapped, None)
    rsa_wrapped_b64 = base64.b64encode(rsa_wrapped_bytes).decode()

    # Unwrap RSA layer to recover DEK
    return unwrap_dek(rsa_wrapped_b64, rsa_private_pem)
