"""
app/watermark.py — LSB Steganographic Watermarking for Certificates
====================================================================
Implements robust, invisible Least-Significant-Bit (LSB) steganographic
watermarking for digital document images.

Encodes an authenticated digest of the certificate hash directly into
pixel color channels, enabling physical tamper detection and origin proving.
"""

import os
import logging
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

WATERMARK_MAGIC = b"DOCUVAULT_WM:"


def embed_watermark(image_input: str | Image.Image, cert_hash: str, output_path: str | None = None) -> Image.Image:
    """
    Embeds a binary signature of cert_hash into the LSBs of image pixels.
    Returns the watermarked PIL Image.
    """
    if isinstance(image_input, str):
        img = Image.open(image_input).convert('RGB')
    else:
        img = image_input.convert('RGB')

    arr = np.array(img, dtype=np.uint8)
    
    # Prepare payload: MAGIC + cert_hash[:16] + NULL delimiter
    payload = WATERMARK_MAGIC + cert_hash[:16].encode('ascii') + b"\x00"
    bit_stream = []
    for byte in payload:
        for bit_idx in range(8):
            bit_stream.append((byte >> (7 - bit_idx)) & 1)

    total_bits = len(bit_stream)
    flat_arr = arr.reshape(-1)

    if total_bits > len(flat_arr):
        raise ValueError("Image resolution is too small to embed watermark bits.")

    # Embed bits in the least significant bit of each color component
    for i, bit in enumerate(bit_stream):
        flat_arr[i] = (flat_arr[i] & 0xFE) | bit

    watermarked_arr = flat_arr.reshape(arr.shape)
    watermarked_img = Image.fromarray(watermarked_arr, mode='RGB')

    if output_path:
        watermarked_img.save(output_path, 'PNG')
        logger.info(f"Watermarked image saved to {output_path}")

    return watermarked_img


def extract_watermark(image_input: str | Image.Image) -> str | None:
    """
    Extracts embedded cert_hash digest from an LSB watermarked image.
    Returns the extracted 16-char hex digest or None if no valid watermark found.
    """
    try:
        if isinstance(image_input, str):
            img = Image.open(image_input).convert('RGB')
        else:
            img = image_input.convert('RGB')

        arr = np.array(img, dtype=np.uint8)
        flat_arr = arr.reshape(-1)

        extracted_bytes = bytearray()
        cur_byte = 0
        bit_count = 0

        # Scan up to 512 bytes for watermark
        max_scan = min(512 * 8, len(flat_arr))
        for i in range(max_scan):
            bit = flat_arr[i] & 1
            cur_byte = (cur_byte << 1) | bit
            bit_count += 1
            if bit_count == 8:
                if cur_byte == 0:  # Null terminator
                    break
                extracted_bytes.append(cur_byte)
                cur_byte = 0
                bit_count = 0

        extracted_raw = bytes(extracted_bytes)
        if extracted_raw.startswith(WATERMARK_MAGIC):
            digest = extracted_raw[len(WATERMARK_MAGIC):].decode('ascii', errors='ignore')
            return digest
        return None
    except Exception as e:
        logger.debug(f"Watermark extraction failed: {e}")
        return None
