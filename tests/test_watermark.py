"""
tests/test_watermark.py
======================
Verification of LSB steganographic watermarking:
- Watermark embedding in image pixels
- Digest extraction from watermarked image
- Unwatermarked image detection (no false positive)
"""

import pytest
import numpy as np
from PIL import Image
from app.watermark import embed_watermark, extract_watermark


def test_watermark_embed_and_extract(tmp_path):
    """LSB embedded digest is accurately extracted from the image."""
    img = Image.new('RGB', (200, 200), color=(180, 200, 220))
    cert_hash = "8e2906014cccee0bc4721c626671f0b565678240177b93a87c8eb32f33a3faba"

    out_file = str(tmp_path / "watermarked_cert.png")
    watermarked = embed_watermark(img, cert_hash, output_path=out_file)

    extracted_digest = extract_watermark(out_file)
    assert extracted_digest == cert_hash[:16], f"Extracted digest {extracted_digest} did not match {cert_hash[:16]}"


def test_unwatermarked_image_returns_none():
    """An unwatermarked image does not produce a false positive watermark."""
    img = Image.new('RGB', (100, 100), color=(255, 255, 255))
    extracted = extract_watermark(img)
    assert extracted is None
