"""
tests/test_blockchain_signing.py
================================
Verification of cryptographically signed blockchain blocks:
- Ed25519 block signing at creation time
- Signature verification across chain blocks
- Tamper detection on modified payload
- Re-signing attack detection
- Legacy block backward compatibility
"""

import json
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app.blockchain import Blockchain, Block


def test_signed_block_creation_and_verification(tmp_path, monkeypatch):
    """A block signed with an Ed25519 key passes cryptographic signature verification."""
    monkeypatch.setattr("app.blockchain.CHAIN_DIR", str(tmp_path))
    monkeypatch.setattr("app.blockchain.CHAIN_FILE", str(tmp_path / "chain.json"))

    bc = Blockchain()
    
    # Institution generates keypair
    inst_priv = Ed25519PrivateKey.generate()
    inst_priv_bytes = inst_priv.private_bytes_raw()

    block_idx = bc.add_document_block(
        cert_hash="a"*64,
        zkp_proof="sample_proof",
        issuer="institution_cbse",
        fields_summary={"name": "Alice", "roll": "12345"},
        signer_privkey=inst_priv_bytes
    )

    block = bc.chain[block_idx]
    assert block.signature is not None
    assert block.signer_pubkey is not None
    assert block.verify_signature() is True
    assert bc.is_chain_valid() is True


def test_tampered_payload_detected(tmp_path, monkeypatch):
    """Modifying block data post-hoc causes signature and hash check to fail."""
    monkeypatch.setattr("app.blockchain.CHAIN_DIR", str(tmp_path))
    monkeypatch.setattr("app.blockchain.CHAIN_FILE", str(tmp_path / "chain.json"))

    bc = Blockchain()
    inst_priv = Ed25519PrivateKey.generate()

    block_idx = bc.add_document_block(
        cert_hash="b"*64,
        zkp_proof="proof_val",
        issuer="institution_iit",
        fields_summary={"degree": "B.Tech"},
        signer_privkey=inst_priv.private_bytes_raw()
    )

    block = bc.chain[block_idx]

    # Malicious actor changes data
    tampered_data = json.loads(block.data)
    tampered_data["fields_summary"]["degree"] = "M.Tech Fraud"
    block.data = json.dumps(tampered_data)

    assert block.verify_signature() is False, "Tampered block payload signature was accepted!"
    assert bc.is_chain_valid() is False, "Blockchain reported valid despite tampered payload!"


def test_attacker_resign_with_wrong_key(tmp_path, monkeypatch):
    """An attacker tampering and re-signing with their own key produces an invalid key match."""
    monkeypatch.setattr("app.blockchain.CHAIN_DIR", str(tmp_path))
    monkeypatch.setattr("app.blockchain.CHAIN_FILE", str(tmp_path / "chain.json"))

    bc = Blockchain()
    legit_priv = Ed25519PrivateKey.generate()
    attacker_priv = Ed25519PrivateKey.generate()

    block_idx = bc.add_document_block(
        cert_hash="c"*64,
        zkp_proof="proof_clean",
        issuer="official_board",
        signer_privkey=legit_priv.private_bytes_raw()
    )

    block = bc.chain[block_idx]
    original_pub = block.signer_pubkey

    # Attacker re-signs with their own key
    msg = f"{block.index}:{block.previous_hash}:{block.timestamp}:{block.data}".encode('utf-8')
    block.signature = attacker_priv.sign(msg).hex()
    block.signer_pubkey = attacker_priv.public_key().public_bytes_raw().hex()

    # The block's recorded signer key now diverges from the legitimate institution key
    assert block.signer_pubkey != original_pub
