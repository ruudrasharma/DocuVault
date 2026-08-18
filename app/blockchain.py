"""
app/blockchain.py — DocuVault Blockchain
=========================================
A persistent, file-backed blockchain.

Each document block stores:
  {
    "cert_hash":      "<sha256 hex>",
    "zkp_proof":      "<hex>",
    "issuer":         "<username>",
    "issued_at":      <unix timestamp>,
    "fields_summary": { name, degree, ... }   # from OCR, non-empty only
  }

The raw block.data field is the JSON-serialised dict above.
Legacy string blocks (just a bare hash string) are still readable.
"""

import hashlib
import json
import logging
import os
from time import time

logger = logging.getLogger(__name__)

CHAIN_DIR  = os.environ.get("BLOCKCHAIN_DATA_DIR", "blockchain_data")
CHAIN_FILE = os.path.join(CHAIN_DIR, "chain.json")


class Block:
    __slots__ = ("index", "previous_hash", "timestamp", "data", "hash", "signature", "signer_pubkey")

    def __init__(self, index, previous_hash, timestamp, data, hash_val, signature=None, signer_pubkey=None):
        self.index         = index
        self.previous_hash = previous_hash
        self.timestamp     = timestamp
        self.data          = data          # str (JSON or bare hash)
        self.hash          = hash_val
        self.signature     = signature     # hex-encoded Ed25519 signature
        self.signer_pubkey = signer_pubkey # hex-encoded Ed25519 public key

    def to_dict(self):
        d = {
            "index":         self.index,
            "previous_hash": self.previous_hash,
            "timestamp":     self.timestamp,
            "data":          self.data,
            "hash":          self.hash,
        }
        if self.signature:
            d["signature"] = self.signature
        if self.signer_pubkey:
            d["signer_pubkey"] = self.signer_pubkey
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(
            d["index"],
            d["previous_hash"],
            d["timestamp"],
            d["data"],
            d["hash"],
            d.get("signature"),
            d.get("signer_pubkey")
        )

    def verify_signature(self) -> bool:
        """Verifies the block's Ed25519 signature if present."""
        if not self.signature or not self.signer_pubkey:
            return True  # Legacy / unsigned block
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            pub_bytes = bytes.fromhex(self.signer_pubkey)
            sig_bytes = bytes.fromhex(self.signature)
            pub = Ed25519PublicKey.from_public_bytes(pub_bytes)
            msg = f"{self.index}:{self.previous_hash}:{self.timestamp}:{self.data}".encode('utf-8')
            pub.verify(sig_bytes, msg)
            return True
        except Exception:
            return False

    # ── Parse data field ──────────────────────────────────────
    @property
    def parsed_data(self) -> dict | None:
        """Returns data as dict if JSON, else None (legacy bare-hash blocks)."""
        if isinstance(self.data, dict):
            return self.data
        try:
            return json.loads(self.data)
        except (json.JSONDecodeError, TypeError):
            return None

    @property
    def cert_hash(self) -> str | None:
        pd = self.parsed_data
        if pd:
            return pd.get("cert_hash")
        # Legacy: the whole data field IS the hash
        if isinstance(self.data, str) and len(self.data) == 64:
            return self.data
        return None


class Blockchain:
    def __init__(self):
        os.makedirs(CHAIN_DIR, exist_ok=True)
        self.chain: list[Block] = []
        self._load()

    # ── Persistence ───────────────────────────────────────────
    def _load(self):
        try:
            with open(CHAIN_FILE, "r") as f:
                raw = json.load(f)
            self.chain = [Block.from_dict(b) for b in raw]
            if not self.chain:
                self._genesis()
        except (FileNotFoundError, json.JSONDecodeError):
            self._genesis()
        logger.info("Blockchain loaded: %d blocks", len(self.chain))

    def _save(self):
        try:
            with open(CHAIN_FILE, "w") as f:
                json.dump([b.to_dict() for b in self.chain], f, indent=2)
        except Exception as exc:
            logger.error("Blockchain save error: %s", exc)

    def _genesis(self):
        ts = 0.0
        data = "GENESIS"
        h = self._hash(0, "0", ts, data)
        self.chain = [Block(0, "0", ts, data, h)]
        self._save()

    # ── Hashing ───────────────────────────────────────────────
    @staticmethod
    def _hash(index, previous_hash, timestamp, data) -> str:
        data_str = json.dumps(data, sort_keys=True) if isinstance(data, dict) else str(data)
        raw = f"{index}{previous_hash}{timestamp}{data_str}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # ── Write ─────────────────────────────────────────────────
    def _add_raw(self, data, signer_privkey_bytes: bytes | None = None) -> int:
        """Internal: add any data to chain, sign if privkey provided, return new block index."""
        prev = self.chain[-1]
        idx  = prev.index + 1
        ts   = time()
        h    = self._hash(idx, prev.hash, ts, data)
        sig_hex = None
        pub_hex = None

        if signer_privkey_bytes:
            try:
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
                priv = Ed25519PrivateKey.from_private_bytes(signer_privkey_bytes[:32])
                pub = priv.public_key()
                pub_hex = pub.public_bytes_raw().hex()
                msg = f"{idx}:{prev.hash}:{ts}:{data}".encode('utf-8')
                sig_hex = priv.sign(msg).hex()
            except Exception as e:
                logger.error(f"Failed to sign block #{idx}: {e}")

        block = Block(idx, prev.hash, ts, data, h, signature=sig_hex, signer_pubkey=pub_hex)
        self.chain.append(block)
        self._save()
        logger.info("Block #%d added (hash=%s…, signed=%s)", idx, h[:12], bool(sig_hex))
        return idx

    def add_document_block(
        self,
        cert_hash: str,
        zkp_proof: str,
        issuer: str,
        fields_summary: dict | None = None,
        signer_privkey: bytes | None = None,
        zkp_blinding: str | None = None,
    ) -> int:
        """
        Add a document record block, cryptographically signed with institution key.
        Returns the new block index.
        zkp_blinding: the Pedersen blinding factor (as string int) stored alongside
        the commitment so verify_zkp_hex can do a real cryptographic check later.
        This is intentionally public for institution-issued documents — the hash
        is already public at this layer, so opening the commitment reveals nothing extra.
        """
        payload = {
            "cert_hash":      cert_hash,
            "zkp_proof":      zkp_proof,
            "issuer":         issuer,
            "issued_at":      time(),
            "fields_summary": fields_summary or {},
        }
        if zkp_blinding is not None:
            payload["zkp_blinding"] = zkp_blinding
        return self._add_raw(json.dumps(payload, sort_keys=True), signer_privkey_bytes=signer_privkey)

    def add_wallet_issue_block(self, cert_hash: str, owner_username: str, issuer_username: str, signer_privkey: bytes | None = None) -> int:
        payload = {"type": "wallet_issue", "cert_hash": cert_hash,
                   "owner": owner_username, "issuer": issuer_username, "ts": time()}
        return self._add_raw(json.dumps(payload, sort_keys=True), signer_privkey_bytes=signer_privkey)

    def add_grant_block(self, cert_hash: str, owner_username: str, grantee_username: str, expires_at_ts: float, signer_privkey: bytes | None = None) -> int:
        payload = {"type": "grant", "cert_hash": cert_hash, "owner": owner_username,
                   "grantee": grantee_username, "expires_at": expires_at_ts, "ts": time()}
        return self._add_raw(json.dumps(payload, sort_keys=True), signer_privkey_bytes=signer_privkey)

    def add_revoke_block(self, cert_hash: str, owner_username: str, grantee_username: str, signer_privkey: bytes | None = None) -> int:
        payload = {"type": "revoke", "cert_hash": cert_hash, "owner": owner_username,
                   "grantee": grantee_username, "ts": time()}
        return self._add_raw(json.dumps(payload, sort_keys=True), signer_privkey_bytes=signer_privkey)

    def get_events_for_hash(self, cert_hash: str) -> list[dict]:
        """All grant/revoke/issue events for this doc, in chain order — this IS the access-control read path."""
        out = []
        for block in self.chain[1:]:
            pd = block.parsed_data
            if pd and pd.get("cert_hash") == cert_hash and pd.get("type") in ("wallet_issue", "grant", "revoke"):
                out.append({
                    **pd,
                    "_block_index": block.index,
                    "_is_signed": bool(block.signature),
                    "_sig_valid": block.verify_signature()
                })
        return out

    # Legacy: old callers that pass a bare hash string
    def add_block(self, data):
        return self._add_raw(data)

    # ── Read ──────────────────────────────────────────────────
    def find_block_by_hash(self, cert_hash: str) -> dict | None:
        """
        Return the parsed block data dict for the document with this hash.
        Returns None if not found.
        """
        for block in self.chain:
            if block.cert_hash == cert_hash:
                pd = block.parsed_data
                if pd:
                    return {
                        **pd,
                        "_block_index": block.index,
                        "_block_hash": block.hash,
                        "_is_signed": bool(block.signature),
                        "_sig_valid": block.verify_signature(),
                    }
                # Legacy bare-hash block
                return {
                    "cert_hash":      cert_hash,
                    "zkp_proof":      "",
                    "issuer":         "unknown",
                    "issued_at":      block.timestamp,
                    "fields_summary": {},
                    "_block_index":   block.index,
                    "_block_hash":    block.hash,
                    "_is_signed":     False,
                    "_sig_valid":     True,
                }
        return None

    def is_valid_hash(self, cert_hash: str) -> bool:
        return self.find_block_by_hash(cert_hash) is not None

    def get_all_document_blocks(self) -> list[dict]:
        """Return all non-genesis document blocks as list of dicts."""
        results = []
        for block in self.chain[1:]:  # skip genesis
            pd = block.parsed_data
            if pd and "cert_hash" in pd:
                if pd.get("type") in ("wallet_issue", "grant", "revoke"):
                    continue
                results.append({
                    **pd,
                    "_block_index": block.index,
                    "_block_hash":  block.hash,
                    "_timestamp":   block.timestamp,
                    "_is_signed":   bool(block.signature),
                    "_sig_valid":   block.verify_signature(),
                })
            elif block.cert_hash:
                # Legacy bare-hash block
                results.append({
                    "cert_hash":      block.cert_hash,
                    "zkp_proof":      "",
                    "issuer":         "legacy",
                    "issued_at":      block.timestamp,
                    "fields_summary": {},
                    "_block_index":   block.index,
                    "_block_hash":    block.hash,
                    "_timestamp":     block.timestamp,
                    "_is_signed":     False,
                    "_sig_valid":     True,
                })
        return list(reversed(results))  # newest first

    # ── Chain integrity ───────────────────────────────────────
    def is_chain_valid(self) -> bool:
        for i in range(1, len(self.chain)):
            cur  = self.chain[i]
            prev = self.chain[i - 1]
            if cur.previous_hash != prev.hash:
                return False
            expected = self._hash(cur.index, cur.previous_hash, cur.timestamp, cur.data)
            if cur.hash != expected:
                return False
            if not cur.verify_signature():
                logger.warning(f"Block #{cur.index} cryptographic signature verification failed!")
                return False
        return True

    def stats(self) -> dict:
        doc_blocks = [b for b in self.chain[1:] if b.cert_hash]
        signed_blocks = [b for b in self.chain[1:] if b.signature]
        return {
            "total_blocks":     len(self.chain),
            "document_blocks":  len(doc_blocks),
            "signed_blocks":    len(signed_blocks),
            "chain_valid":      self.is_chain_valid(),
            "latest_hash":      self.chain[-1].hash if self.chain else None,
        }


blockchain = Blockchain()

