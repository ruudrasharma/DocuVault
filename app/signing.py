"""
app/signing.py — Ed25519 Institution Document Signing
======================================================
Manages Ed25519 signing keypairs for institution accounts:
- ensure_signing_key(): provision at account creation or first upload
- get_signing_privkey(): decrypt and return private key bytes for signing
- Used by /upload to sign every blockchain block the institution issues

Security model (Option B — session-cached decryption):
  The signing private key is decrypted once per upload using the institution's
  login password. It is NOT cached between requests — each signing operation
  requires the password. The trade-off: more friction per upload, but the
  decrypted key never persists in memory past the request lifecycle.

  To enable password-free repeated signing within a session, uncomment the
  session caching block and document the security implications.
"""

import os
import base64
import logging

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import db
from .database import User, InstitutionSigningKey

logger = logging.getLogger(__name__)

PBKDF2_ITERATIONS = 200_000


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode('utf-8'))


def ensure_signing_key(user: User, password: str) -> InstitutionSigningKey:
    """
    Provision an Ed25519 signing keypair for an institution account.
    If one already exists, returns it unchanged.
    Private key is AES-GCM encrypted with PBKDF2(password).
    """
    sk = InstitutionSigningKey.query.filter_by(user_id=user.id).first()
    if sk:
        return sk

    if not password:
        raise ValueError("Password is required to create a signing key.")

    # Generate keypair
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()

    pub_bytes = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Encrypt private key
    salt = os.urandom(16)
    aes_key = _derive_key(password, salt)
    aesgcm = AESGCM(aes_key)
    nonce = os.urandom(12)
    encrypted = aesgcm.encrypt(nonce, priv_bytes, None)
    enc_b64 = base64.b64encode(nonce + encrypted).decode('utf-8')

    sk = InstitutionSigningKey(
        user_id=user.id,
        public_key_hex=pub_bytes.hex(),
        encrypted_private_key=enc_b64,
        kdf_salt=salt.hex(),
    )
    db.session.add(sk)
    db.session.commit()
    logger.info(f"Provisioned Ed25519 signing key for institution: {user.username}")
    return sk


def get_signing_privkey(user: User, password: str) -> bytes:
    """
    Decrypt and return the Ed25519 private key bytes for the institution.
    Raises ValueError on wrong password or missing key.
    """
    sk = InstitutionSigningKey.query.filter_by(user_id=user.id).first()
    if not sk:
        raise ValueError(
            f"No signing key for '{user.username}'. "
            "It will be generated on next upload."
        )

    try:
        salt = bytes.fromhex(sk.kdf_salt)
        aes_key = _derive_key(password, salt)
        payload = base64.b64decode(sk.encrypted_private_key)
        nonce, ciphertext = payload[:12], payload[12:]
        aesgcm = AESGCM(aes_key)
        priv_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        return priv_bytes
    except Exception as exc:
        raise ValueError("Incorrect password or corrupted signing key.") from exc
