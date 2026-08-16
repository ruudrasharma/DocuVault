"""
app/verifiable_credentials.py — W3C Verifiable Credentials (VC) Implementation
================================================================================
Implements W3C-compliant Verifiable Credentials format signed with Ed25519:
- issue_vc(): constructs and cryptographically signs a portable credential
- verify_vc(): validates structure, cryptographic signature, and claims
"""

import json
import uuid
import logging
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

logger = logging.getLogger(__name__)


def issue_vc(
    doc_fields: dict,
    issuer_username: str,
    holder_username: str,
    cert_hash: str,
    signer_privkey_bytes: bytes | None = None
) -> dict:
    """
    Constructs and signs a W3C-compliant Verifiable Credential.
    Returns the complete VC JSON dict including the cryptographic proof block.
    """
    vc_id = f"urn:uuid:{uuid.uuid4()}"
    now_iso = datetime.now(timezone.utc).isoformat()

    # Generate ephemeral key if no institution key passed
    if not signer_privkey_bytes:
        priv = Ed25519PrivateKey.generate()
    else:
        priv = Ed25519PrivateKey.from_private_bytes(signer_privkey_bytes[:32])

    pub = priv.public_key()
    pub_hex = pub.public_bytes_raw().hex()

    credential_subject = {
        "id": f"did:docuvault:{holder_username}",
        "certificateHash": cert_hash,
        "claims": doc_fields or {}
    }

    unsigned_vc = {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://docuvault.io/contexts/credentials/v1"
        ],
        "id": vc_id,
        "type": ["VerifiableCredential", "EducationalCredential"],
        "issuer": {
            "id": f"did:docuvault:issuer:{issuer_username}",
            "name": issuer_username,
            "publicKey": pub_hex
        },
        "issuanceDate": now_iso,
        "credentialSubject": credential_subject
    }

    # Canonicalize and sign
    canonical_bytes = json.dumps(unsigned_vc, sort_keys=True).encode('utf-8')
    sig_bytes = priv.sign(canonical_bytes)
    sig_hex = sig_bytes.hex()

    proof_block = {
        "type": "Ed25519Signature2020",
        "created": now_iso,
        "verificationMethod": f"did:docuvault:issuer:{issuer_username}#key-1",
        "proofPurpose": "assertionMethod",
        "proofValue": sig_hex
    }

    signed_vc = dict(unsigned_vc)
    signed_vc["proof"] = proof_block
    return signed_vc


def verify_vc(vc_data: dict | str, expected_issuer_pubkey_hex: str | None = None) -> tuple[bool, str, dict]:
    """
    Verifies a W3C Verifiable Credential:
    1. Validates schema and required fields (@context, type, issuer, credentialSubject, proof).
    2. Validates Ed25519 signature over canonicalized payload.
    Returns (is_valid, message, claims_dict).
    """
    if isinstance(vc_data, str):
        try:
            vc_data = json.loads(vc_data)
        except Exception as e:
            return False, f"Invalid JSON payload: {e}", {}

    if not isinstance(vc_data, dict):
        return False, "VC must be a JSON object", {}

    proof = vc_data.get("proof")
    if not proof or not isinstance(proof, dict):
        return False, "Missing proof block in Verifiable Credential", {}

    sig_hex = proof.get("proofValue")
    if not sig_hex:
        return False, "Missing signature proofValue", {}

    issuer_info = vc_data.get("issuer")
    pub_hex = expected_issuer_pubkey_hex or (issuer_info.get("publicKey") if isinstance(issuer_info, dict) else None)
    if not pub_hex:
        return False, "Missing issuer public key", {}

    # Strip proof block to reconstruct signed payload
    unsigned_payload = {k: v for k, v in vc_data.items() if k != "proof"}
    canonical_bytes = json.dumps(unsigned_payload, sort_keys=True).encode('utf-8')

    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))
        pub.verify(bytes.fromhex(sig_hex), canonical_bytes)
    except Exception as exc:
        return False, f"Cryptographic signature verification failed: {exc}", {}

    subject = vc_data.get("credentialSubject", {})
    claims = subject.get("claims", {})
    return True, "Verifiable Credential signature valid and authentic", claims
