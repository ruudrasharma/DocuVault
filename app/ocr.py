"""
app/ocr.py — DocuVault OCR + Hashing Pipeline
================================================
Calls the OCR microservice (localhost:5002) instead of running OCR in-process.

Flow:
  file_path → OCR service → field dict → normalize → SHA-256 → blockchain
"""

import hashlib
import json
import logging
import os
import sys

import requests

logger = logging.getLogger(__name__)

OCR_SERVICE_URL = os.environ.get("OCR_SERVICE_URL", "http://127.0.0.1:5002")
OCR_TIMEOUT = int(os.environ.get("OCR_TIMEOUT", "120"))  # seconds

# ── Field normalisation ────────────────────────────────────────────────────────

# These are the canonical keys we care about for hashing.
# Any key missing from OCR output defaults to "" so the hash is still stable.
CANONICAL_KEYS = [
    "name",
    "roll_no",
    "date",
    "date_of_birth",
    "degree",
    "institute",
    "board",
    "grade",
    "year",
    "mothers_name",
    "fathers_name",
    "subject",
]


def normalize_fields(raw_fields: dict) -> dict:
    """
    Produce a deterministic, canonical field dict for hashing.
    - Only CANONICAL_KEYS are included (extras ignored → hash stability)
    - All values: strip whitespace, collapse internal spaces, UPPERCASE
    - Missing keys → empty string
    """
    normalized = {}
    for key in CANONICAL_KEYS:
        val = raw_fields.get(key, "") or ""
        val = " ".join(str(val).upper().split())  # collapse whitespace + uppercase
        normalized[key] = val
    return normalized


def normalize_and_hash(fields: dict) -> str:
    """
    Canonical dict → deterministic SHA-256 hex string.
    json.dumps with sort_keys ensures key order never matters.
    """
    canonical = normalize_fields(fields)
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── OCR service call ───────────────────────────────────────────────────────────

def extract_fields(file_path: str) -> dict:
    """
    Send file to OCR microservice, get back extracted field dict.
    Falls back to empty dict on failure (so upstream can decide what to do).
    """
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"{OCR_SERVICE_URL}/ocr/fields",
                files={"file": (os.path.basename(file_path), f)},
                data={"engine": "tesseract"},   # tesseract is 10x faster on CPU
                timeout=OCR_TIMEOUT,
            )
        resp.raise_for_status()
        data = resp.json()

        raw_fields = data.get("fields", {})
        # Also store raw text for display / debug
        raw_fields["_raw_text"] = data.get("text", "")
        raw_fields["_engine"] = data.get("engine", "unknown")
        raw_fields["_confidence"] = data.get("confidence", 0.0)
        raw_fields["_pages"] = data.get("pages", 1)

        logger.info(
            "OCR extracted %d fields via %s (conf=%.2f) for %s",
            len(raw_fields),
            raw_fields.get("_engine"),
            raw_fields.get("_confidence", 0),
            os.path.basename(file_path),
        )
        return raw_fields

    except requests.exceptions.ConnectionError:
        logger.error("OCR service not reachable at %s — is docuvault-ocr running?", OCR_SERVICE_URL)
        raise RuntimeError(
            "OCR service is offline. Run: sudo systemctl start docuvault-ocr"
        )
    except requests.exceptions.Timeout:
        logger.error("OCR service timed out after %ds", OCR_TIMEOUT)
        raise RuntimeError("OCR service timed out — document may be too large.")
    except Exception as exc:
        logger.error("OCR extract_fields error: %s", exc)
        raise


# ── Upload pipeline ────────────────────────────────────────────────────────────

def process_upload(file_path: str, issuer: str) -> tuple:
    """
    Full upload pipeline with dual-hash architecture:
      1. OCR → field dict
      2. Normalize + hash → ocr_hash
      3. Compute raw file byte hash → file_hash
      4. Write block to blockchain with dual-hash (ocr_hash + file_hash) + ZKP
      5. Return (ocr_hash, normalized_fields, raw_fields, block_index)

    Raises on OCR failure, PermissionError if role wrong, etc.
    """
    raw_fields = extract_fields(file_path)
    norm_fields = normalize_fields(raw_fields)
    ocr_hash = normalize_and_hash(raw_fields)

    # Compute raw file byte hash
    file_hash = ""
    try:
        with open(file_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        logger.warning("Could not compute raw file hash: %s", e)

    # ZKP commitment
    from .zkp import generate_zkp_proof, proof_to_hex
    proof = generate_zkp_proof(ocr_hash)
    proof_hex = proof_to_hex(proof)

    # Write to blockchain with dual-hash
    from .blockchain import blockchain
    block_index = blockchain.add_document_block(
        cert_hash=ocr_hash,
        file_hash=file_hash,
        zkp_proof=proof_hex,
        issuer=issuer,
        fields_summary={k: v for k, v in norm_fields.items() if v},  # non-empty only
    )

    return ocr_hash, norm_fields, raw_fields, block_index


def verify_upload(file_path: str) -> tuple:
    """
    Full verify pipeline:
      1. OCR → field dict
      2. Normalize + hash → ocr_hash
      3. Compute raw file byte hash → file_hash
      4. Dual-hash Blockchain lookup (checks OCR hash, then file byte hash)
      5. ZKP re-verification
      6. Return (is_valid, cert_hash, block_data, norm_fields)
    """
    raw_fields = extract_fields(file_path)
    ocr_hash = normalize_and_hash(raw_fields)
    norm_fields = normalize_fields(raw_fields)

    # Compute raw file byte hash
    file_hash = ""
    try:
        with open(file_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        logger.warning("Could not compute file hash: %s", e)

    from .blockchain import blockchain
    # Check OCR hash first
    block_data = blockchain.find_block_by_hash(ocr_hash)
    matched_hash = ocr_hash

    # If OCR hash didn't match (e.g. font / OCR drift), check raw file SHA-256
    if not block_data and file_hash:
        block_data = blockchain.find_block_by_hash(file_hash)
        if block_data:
            matched_hash = file_hash

    if not block_data:
        return False, ocr_hash, None, norm_fields

    # Re-verify ZKP (if stored)
    from .zkp import generate_zkp_proof, proof_to_hex
    try:
        stored_proof = block_data.get("zkp_proof", "")
        if stored_proof:
            target_proof_hash = block_data.get("cert_hash") or matched_hash
            recomputed_proof = proof_to_hex(generate_zkp_proof(target_proof_hash))
            zkp_valid = (recomputed_proof == stored_proof)
        else:
            zkp_valid = True
    except Exception as e:
        logger.warning("ZKP re-verification error: %s", e)
        zkp_valid = True

    is_valid = bool(block_data) and zkp_valid
    return is_valid, matched_hash, block_data, norm_fields





# ── Legacy compat (kept so nothing breaks) ────────────────────────────────────

# Old callers that only got (cert_hash,) or (is_valid, cert_hash) still work:
def _process_upload_compat(file_path: str, issuer: str) -> str:
    cert_hash, *_ = process_upload(file_path, issuer)
    return cert_hash


def _verify_upload_compat(file_path: str) -> tuple:
    is_valid, cert_hash, *_ = verify_upload(file_path)
    return is_valid, cert_hash


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.ocr <path_to_document>")
        sys.exit(1)
    fp = sys.argv[1]
    raw = extract_fields(fp)
    norm = normalize_fields(raw)
    h = normalize_and_hash(raw)
    print("Raw fields:", json.dumps({k: v for k, v in raw.items() if not k.startswith("_")}, indent=2))
    print("Normalized:", json.dumps(norm, indent=2))
    print("SHA-256 hash:", h)