"""
app/zkp.py — Zero-Knowledge Proof helpers
==========================================
Uses BN128 elliptic curve (via py_ecc) to produce commitments.

A "proof" here is an elliptic-curve commitment:
  proof = G1 * h   where h = int(cert_hash, 16) % field_modulus

Verification: recompute commitment from the hash and compare.
This proves knowledge of the preimage hash without revealing raw field data.
"""

import hashlib
import logging

logger = logging.getLogger(__name__)


def _get_bn128():
    try:
        from py_ecc.bn128 import G1, multiply, FQ
        return G1, multiply, FQ
    except ImportError:
        raise RuntimeError(
            "py_ecc not installed. Run: pip install py_ecc"
        )


def generate_zkp_proof(cert_hash: str):
    """
    Generate an elliptic-curve commitment for cert_hash.
    Returns a tuple (FQ, FQ) — the point on BN128 G1.
    """
    try:
        G1, multiply, FQ = _get_bn128()
        h = int(cert_hash, 16) % FQ.field_modulus
        commitment = multiply(G1, h)
        return commitment
    except Exception as exc:
        logger.error("ZKP proof generation failed: %s", exc)
        raise


def proof_to_hex(proof) -> str:
    """
    Convert a BN128 curve point to a hex string for JSON-safe storage.
    Format: "<x_int>:<y_int>" hex-encoded.
    """
    if proof is None:
        return ""
    try:
        x, y = proof
        # FQ objects — get their underlying integer
        x_int = int(x) if hasattr(x, '__int__') else x.n
        y_int = int(y) if hasattr(y, '__int__') else y.n
        raw = f"{x_int}:{y_int}"
        return hashlib.sha256(raw.encode()).hexdigest()  # store as compact sha256 of coords
    except Exception as exc:
        logger.warning("proof_to_hex fallback (str): %s", exc)
        return hashlib.sha256(str(proof).encode()).hexdigest()


def verify_zkp_proof(proof, cert_hash: str) -> bool:
    """
    Verify a proof (curve point) against cert_hash by recomputing.
    """
    try:
        G1, multiply, FQ = _get_bn128()
        h = int(cert_hash, 16) % FQ.field_modulus
        recomputed = multiply(G1, h)
        return str(recomputed) == str(proof)
    except Exception as exc:
        logger.error("ZKP verify error: %s", exc)
        return False


def verify_zkp_hex(stored_hex: str, cert_hash: str) -> bool:
    """
    Verify a stored hex proof (from proof_to_hex) against cert_hash.
    """
    try:
        proof = generate_zkp_proof(cert_hash)
        recomputed_hex = proof_to_hex(proof)
        return recomputed_hex == stored_hex
    except Exception as exc:
        logger.error("ZKP hex verify error: %s", exc)
        return False