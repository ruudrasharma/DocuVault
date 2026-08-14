"""
app/documents.py — Document Encryption-at-Rest & Storage
=========================================================
Handles envelope encryption of document blobs using AES-GCM and SHA-256.
Encrypted files are stored in data/wallet_blobs/.
"""

import os
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .wallet import wrap_dek

# Base upload folder path relative to app root
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'data')
STORAGE_DIR = os.path.join(UPLOAD_FOLDER, 'wallet_blobs')

def ensure_storage_dir():
    """Ensure the wallet_blobs storage directory exists."""
    os.makedirs(STORAGE_DIR, exist_ok=True)

def encrypt_and_store(file_bytes: bytes, owner_public_pem: str) -> dict:
    """
    Encrypt opaque file bytes with a random DEK via AES-GCM.
    Store encrypted blob on disk at STORAGE_DIR/<cert_hash>.enc.
    Wrap DEK for document owner.
    Returns dict: {cert_hash, iv_hex, wrapped_dek_owner, blob_path}
    """
    ensure_storage_dir()
    
    dek = os.urandom(32)
    iv = os.urandom(12)
    
    aesgcm = AESGCM(dek)
    ciphertext = aesgcm.encrypt(iv, file_bytes, None)
    
    cert_hash = hashlib.sha256(ciphertext).hexdigest()
    blob_filename = f"{cert_hash}.enc"
    blob_path = os.path.join(STORAGE_DIR, blob_filename)
    
    with open(blob_path, 'wb') as f:
        f.write(ciphertext)
        
    wrapped_dek_owner = wrap_dek(dek, owner_public_pem)
    
    return {
        'cert_hash': cert_hash,
        'iv_hex': iv.hex(),
        'wrapped_dek_owner': wrapped_dek_owner,
        'blob_path': blob_path,
    }

def decrypt_blob(blob_path: str, iv_hex: str, dek: bytes) -> bytes:
    """
    Decrypt an encrypted blob file from disk using AES-GCM and the DEK.
    Raises ValueError / InvalidTag if file is tampered or decryption fails.
    """
    if not os.path.exists(blob_path):
        raise FileNotFoundError(f"Encrypted document blob not found at {blob_path}")
        
    with open(blob_path, 'rb') as f:
        ciphertext = f.read()
        
    iv = bytes.fromhex(iv_hex)
    aesgcm = AESGCM(dek)
    
    try:
        plaintext = aesgcm.decrypt(iv, ciphertext, None)
        return plaintext
    except Exception as exc:
        raise ValueError("Document decryption failed — file corrupted or tampered.") from exc
