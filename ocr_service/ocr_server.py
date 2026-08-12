#!/usr/bin/env python3
"""
DocuVault OCR Microservice
===========================
Runs on port 5002. Accepts document images/PDFs and returns extracted text
using EasyOCR (primary) with Tesseract as fallback.

Endpoints:
  POST /ocr          — Extract text from uploaded file
  POST /ocr/fields   — Extract structured fields (name, date, etc.)
  GET  /health       — Service health check

Usage (from DocuVault):
  import requests
  r = requests.post('http://localhost:5002/ocr', files={'file': open('doc.jpg','rb')})
  print(r.json())  # -> {'text': '...', 'engine': 'easyocr', 'confidence': 0.94}
"""

import os
import sys
import io
import re
import logging
import tempfile
from pathlib import Path

from flask import Flask, request, jsonify
from PIL import Image

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB

# ── Lazy-load OCR engines ──────────────────────────────────────
_easy_reader = None
_tesseract_ok = False


def get_easy_reader():
    global _easy_reader
    if _easy_reader is None:
        try:
            import easyocr
            logger.info("Loading EasyOCR model (first run downloads ~200MB)…")
            _easy_reader = easyocr.Reader(['en', 'hi'], gpu=False, verbose=False)
            logger.info("EasyOCR ready.")
        except Exception as e:
            logger.warning(f"EasyOCR unavailable: {e}")
    return _easy_reader


def check_tesseract():
    global _tesseract_ok
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        _tesseract_ok = True
    except Exception:
        _tesseract_ok = False
    return _tesseract_ok


# ── File → PIL Image ───────────────────────────────────────────
def file_to_images(file_bytes: bytes, ext: str) -> list:
    """Convert uploaded file bytes to list of PIL Images."""
    ext = ext.lower().lstrip('.')
    images = []
    if ext == 'pdf':
        try:
            from pdf2image import convert_from_bytes
            # 150 DPI is enough for OCR and much faster than 200
            imgs = convert_from_bytes(file_bytes, dpi=150)
            images = imgs[:3]   # cap at first 3 pages — marksheets are 1-2 pages
        except Exception as e:
            raise ValueError(f"PDF conversion failed: {e}")
    elif ext in ('jpg', 'jpeg', 'png', 'bmp', 'tiff', 'tif', 'webp'):
        images = [Image.open(io.BytesIO(file_bytes)).convert('RGB')]
    else:
        raise ValueError(f"Unsupported file type: .{ext}")

    # Resize any image larger than 3000px on longest side (keeps OCR fast)
    MAX_SIDE = 3000
    resized = []
    for img in images:
        w, h = img.size
        if max(w, h) > MAX_SIDE:
            scale = MAX_SIDE / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        resized.append(img)
    return resized


# ── OCR engines ────────────────────────────────────────────────
def ocr_easyocr(images: list) -> tuple[str, float]:
    reader = get_easy_reader()
    if not reader:
        raise RuntimeError("EasyOCR not available")
    all_text = []
    all_conf = []
    for img in images:
        import numpy as np
        arr = np.array(img)
        results = reader.readtext(arr, detail=1, paragraph=False)
        for (_, text, conf) in results:
            all_text.append(text)
            all_conf.append(conf)
    full_text = '\n'.join(all_text)
    avg_conf = sum(all_conf) / len(all_conf) if all_conf else 0.0
    return full_text, round(avg_conf, 4)


def ocr_tesseract(images: list) -> tuple[str, float]:
    import pytesseract
    pages = []
    for img in images:
        data = pytesseract.image_to_data(img, lang='eng+hin',
                                         output_type=pytesseract.Output.DICT)
        words = [w for w, c in zip(data['text'], data['conf'])
                 if w.strip() and int(c) > 0]
        confs = [int(c) for c in data['conf'] if int(c) > 0]
        pages.append(' '.join(words))
    text = '\n'.join(pages)
    avg_conf = sum(confs) / len(confs) / 100 if confs else 0.0
    return text, round(avg_conf, 4)


# ── Field extraction ───────────────────────────────────────────
FIELD_PATTERNS = {
    'name': [
        r'(?:name|student|holder)[:\s]+([A-Z][A-Za-z\s]{2,40})',
        r'(?:to|awarded to|certify that)[:\s]+([A-Z][A-Za-z\s]{2,40})',
    ],
    'roll_no': [
        r'(?:roll\s*no|reg(?:istration)?\s*no|enrol(?:lment)?)[.:\s]+([A-Z0-9/-]{4,20})',
    ],
    'date': [
        r'(?:date|issued?|awarded?)[:\s]+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
        r'(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})',
    ],
    'degree': [
        r'(?:degree|course|programme)[:\s]+([A-Za-z\s\.]{3,60})',
        r'(bachelor|master|doctor|diploma|certificate)\s+(?:of\s+)?[A-Za-z\s]{2,40}',
    ],
    'institute': [
        r'(?:university|institute|college|school)\s+of\s+[A-Za-z\s]{2,60}',
        r'([A-Z][A-Za-z\s]+(?:university|institute|college|school))',
    ],
    'grade': [
        r'(?:grade|cgpa|percentage|marks)[:\s]+([\d\.]+\s*(?:%|\/\d+)?)',
    ],
}


def extract_fields(text: str) -> dict:
    text_lower = text.lower()
    text_lines = text
    found = {}
    for field, patterns in FIELD_PATTERNS.items():
        for pat in patterns:
            m = re.search(pat, text_lines, re.IGNORECASE)
            if m:
                found[field] = m.group(1).strip() if m.lastindex else m.group(0).strip()
                break
    return found


# ── Routes ─────────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health():
    easy_ok = get_easy_reader() is not None
    tess_ok = check_tesseract()
    return jsonify({
        'status': 'ok' if (easy_ok or tess_ok) else 'degraded',
        'engines': {
            'easyocr': easy_ok,
            'tesseract': tess_ok,
        }
    })


@app.route('/ocr', methods=['POST'])
def ocr_extract():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided. Send as multipart/form-data with field "file".'}), 400

    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'Empty filename'}), 400

    # Allow caller to request a specific engine
    engine_pref = request.form.get('engine', 'auto').lower()
    ext = Path(f.filename).suffix.lstrip('.')

    try:
        file_bytes = f.read()
        images = file_to_images(file_bytes, ext)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    text, conf, engine_used = '', 0.0, 'none'

    # Tesseract first when requested or auto — it's much faster on CPU
    if engine_pref in ('tesseract', 'auto'):
        try:
            if check_tesseract():
                text, conf = ocr_tesseract(images)
                engine_used = 'tesseract'
        except Exception as e:
            logger.warning(f"Tesseract failed: {e}")

    # EasyOCR as fallback (or if explicitly requested)
    if (not text and engine_pref == 'auto') or engine_pref == 'easyocr':
        try:
            text, conf = ocr_easyocr(images)
            engine_used = 'easyocr'
        except Exception as e:
            logger.warning(f"EasyOCR failed: {e}")

    if not text:
        return jsonify({'error': 'All OCR engines failed. Check server logs.'}), 500

    return jsonify({
        'text': text,
        'engine': engine_used,
        'confidence': conf,
        'pages': len(images),
        'chars': len(text),
    })


@app.route('/ocr/fields', methods=['POST'])
def ocr_fields():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    f = request.files['file']
    ext = Path(f.filename).suffix.lstrip('.')
    file_bytes = f.read()
    engine_pref = request.form.get('engine', 'auto').lower()

    try:
        images = file_to_images(file_bytes, ext)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    text, conf, engine_used = '', 0.0, 'none'

    # Tesseract first when auto or explicitly requested — 10x faster on CPU
    if engine_pref in ('tesseract', 'auto'):
        try:
            if check_tesseract():
                text, conf = ocr_tesseract(images)
                engine_used = 'tesseract'
        except Exception as e:
            logger.warning(f"Tesseract failed: {e}")

    # EasyOCR fallback
    if (not text and engine_pref == 'auto') or engine_pref == 'easyocr':
        try:
            text, conf = ocr_easyocr(images)
            engine_used = 'easyocr'
        except Exception as e:
            logger.warning(f"EasyOCR failed: {e}")

    if not text:
        return jsonify({'error': 'OCR failed'}), 500

    fields = extract_fields(text)
    return jsonify({
        'text': text,
        'fields': fields,
        'engine': engine_used,
        'confidence': conf,
        'pages': len(images),
    })


if __name__ == '__main__':
    logger.info("Starting DocuVault OCR service on port 5002…")
    logger.info("Warming up EasyOCR (may take a minute on first run)…")
    get_easy_reader()  # Warm up on startup
    app.run(host='127.0.0.1', port=5002, debug=False, threaded=True)
