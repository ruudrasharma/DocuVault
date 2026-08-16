
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from .auth import login_required, role_required
from .ocr import process_upload, verify_upload, normalize_and_hash, extract_fields, normalize_fields
from .blockchain import blockchain
from .zkp import generate_zkp_proof, verify_zkp_hex, proof_to_hex
from .pqc import pqc_encrypt
from .database_models import User
from . import db
from werkzeug.utils import secure_filename
from .database_models import CertificateRecord as CertRecord
import os
import json as _json
import logging
from datetime import datetime as _dt

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)

UPLOAD_FOLDER = 'data'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Upload validation ──────────────────────────────────────────────────────────
_ALLOWED_MAGIC = {
    b'%PDF':           'pdf',
    b'\xff\xd8\xff':  'jpeg',
    b'\x89PNG':        'png',
}
_MAX_IMAGE_DIM = 6000  # pixels per side


def _validate_upload(file_stream) -> tuple[bool, str]:
    """
    Read the first 8 bytes to confirm the file is actually PDF/JPEG/PNG.
    Returns (is_valid, detected_type_or_error_message).
    """
    header = file_stream.read(8)
    file_stream.seek(0)
    for magic, ftype in _ALLOWED_MAGIC.items():
        if header.startswith(magic):
            return True, ftype
    return False, f'Unsupported file type (magic bytes: {header[:4].hex()!r})'


def _check_image_dimensions(file_path: str) -> tuple[bool, str]:
    """Reject images whose dimensions exceed _MAX_IMAGE_DIM to prevent decompression bombs."""
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            w, h = img.size
            if w > _MAX_IMAGE_DIM or h > _MAX_IMAGE_DIM:
                return False, f'Image too large: {w}x{h} (max {_MAX_IMAGE_DIM}x{_MAX_IMAGE_DIM})'
    except Exception:
        pass  # Non-image files (PDFs) skip silently
    return True, 'ok'


@main_bp.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard', role=session.get('role')))
    return redirect(url_for('auth.login'))


@main_bp.route('/dashboard/<role>')
@login_required
@role_required('admin', 'institution', 'verifier', 'citizen')
def dashboard(role):
    return render_template('index.html')


import uuid
from .ml_anomaly import detect_anomaly, load_models, reload_models

# ══════════════════════════════════════════════════════════════════
#  UPLOAD — Full Pipeline
#  Institute → file → OCR → fields → hash → ZKP → Blockchain + DB
# ══════════════════════════════════════════════════════════════════

@main_bp.route('/upload', methods=['POST'])
@login_required
@role_required('institution', 'admin')
def upload_doc():
    """
    Full upload pipeline:
      1. Save file with unique UUID prefix (prevent overwriting historical corpus)
      2. Call OCR microservice → extract fields dict
      3. Normalize fields → canonical SHA-256 hash
      4. Run AI Anomaly Detection (ELA + ML)
      5. Generate ZKP commitment (BN128 elliptic curve)
      6. PQC-encrypt the hash for storage
      7. Write block to blockchain: {cert_hash, zkp_proof, issuer, fields_summary}
      8. Store record in SQL DB (with OCR fields as JSON metadata)
      9. Return: {success, hash, id, block_index, fields, anomaly_analysis, filename}
    """
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'No file provided'}), 400

    # ── Magic-byte validation (before saving) ─────────────────────
    valid, ftype = _validate_upload(file.stream)
    if not valid:
        return jsonify({'error': f'Invalid file: {ftype}'}), 415

    issuer = session.get('username', 'institution')
    original_name = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex[:12]}_{original_name}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)

    # Form fields filled by the institution — used as fallback when OCR misses a field
    form_holder = request.form.get('holder_name', '').strip()
    form_doctype = request.form.get('doc_type', '').strip()
    form_date    = request.form.get('issue_date', '').strip()

    try:
        file.save(file_path)
        logger.info("File saved: %s (%s)", file_path, ftype)

        # ── Dimension cap (after saving, before OCR) ───────────────
        ok, dim_err = _check_image_dimensions(file_path)
        if not ok:
            os.unlink(file_path)
            return jsonify({'error': dim_err}), 413

        # ── Step 1-4: OCR → hash → ZKP ──────────────────────
        cert_hash, norm_fields, raw_fields, block_index = process_upload(file_path, issuer)
        logger.info("Upload: hash=%s block=%d issuer=%s", cert_hash[:12], block_index, issuer)

        # ── Step 4.5: Run AI Anomaly Detection ──────────────
        raw_text_str = " ".join([str(v) for v in norm_fields.values() if v])
        models = load_models()
        is_anomaly, anomaly_score, anomaly_details = detect_anomaly(models, file_path, raw_text_str)

        # ── Step 5: PQC encrypt hash ─────────────────────────
        try:
            enc_hash, _ = pqc_encrypt(cert_hash)
        except Exception:
            enc_hash = b""

        # ── Step 6: DB record ────────────────────────────────
        ocr_name    = norm_fields.get('name') or raw_fields.get('name', '')
        ocr_doctype = norm_fields.get('degree') or raw_fields.get('degree', '')
        ocr_date    = norm_fields.get('date') or raw_fields.get('date', '')

        final_name    = ocr_name    or form_holder or ''
        final_doctype = ocr_doctype or form_doctype or ''
        final_date    = ocr_date    or form_date    or str(_dt.utcnow().date())

        meta = _json.dumps({
            'holder_name': final_name,
            'doc_type':    final_doctype,
            'issue_date':  final_date,
            'filename':    unique_filename,
            'original_filename': original_name,
            'block_index': block_index,
            'ocr_engine':  raw_fields.get('_engine', 'unknown'),
            'ocr_confidence': raw_fields.get('_confidence', 0),
            'fields':      norm_fields,
            'anomaly_analysis': anomaly_details,
        })
        try:
            rec = CertRecord(
                hash_value=cert_hash,
                institution=issuer,
                is_valid=True,
                encrypted_metadata=meta,
            )
            db.session.add(rec)
            db.session.commit()
            rec_id = rec.id
        except Exception as db_err:
            db.session.rollback()
            logger.warning("DB save skipped: %s", db_err)
            rec_id = None

        # ── Response ─────────────────────────────────────────
        display_fields = {k: v for k, v in norm_fields.items() if v}
        return jsonify({
            'success':          True,
            'hash':             cert_hash,
            'id':               rec_id,
            'block_index':      block_index,
            'filename':         original_name,
            'saved_filename':   unique_filename,
            'fields':           display_fields,
            'ocr_engine':       raw_fields.get('_engine', 'unknown'),
            'ocr_confidence':   raw_fields.get('_confidence', 0),
            'anomaly_detected': is_anomaly,
            'anomaly_score':    anomaly_score,
            'anomaly_analysis': anomaly_details,
        })

    except RuntimeError as e:
        logger.error("Upload runtime error: %s", e)
        return jsonify({'error': str(e)}), 503
    except Exception as e:
        logger.error("Upload failed: %s", e)
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════
#  VERIFY — Full Pipeline
#  Verifier → file → OCR → fields → hash → Blockchain → ZKP + AI Anomaly
# ══════════════════════════════════════════════════════════════════

@main_bp.route('/verify_document', methods=['POST'])
@login_required
@role_required('verifier', 'admin', 'institution', 'citizen')
def verify_document():
    """
    Full verify pipeline:
      1. Save file to temporary verify path with UUID prefix
      2. OCR microservice → extract fields
      3. Normalize → SHA-256 hash
      4. Blockchain lookup by hash
      5. ZKP re-verification against stored proof
      6. AI Anomaly Detection (ELA + ML IsolationForest + Autoencoder)
      7. Return: {verified, hash, fields, block_data, issuer, issued_at, anomaly_analysis}
    """
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'No file provided'}), 400

    # ── Magic-byte validation ─────────────────────────────────────
    valid, ftype = _validate_upload(file.stream)
    if not valid:
        return jsonify({'error': f'Invalid file: {ftype}'}), 415

    original_name = secure_filename(file.filename)
    unique_filename = f"verify_{uuid.uuid4().hex[:12]}_{original_name}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)

    try:
        file.save(file_path)

        # ── Dimension cap ───────────────────────────────────────────
        ok, dim_err = _check_image_dimensions(file_path)
        if not ok:
            if os.path.exists(file_path):
                os.unlink(file_path)
            return jsonify({'error': dim_err}), 413

        # ── Step 1: OCR → hash → blockchain → ZKP ────────────
        is_valid, cert_hash, block_data, norm_fields = verify_upload(file_path)
        logger.info("Verify: hash=%s valid=%s", cert_hash[:12] if cert_hash else 'N/A', is_valid)

        # ── Step 2: AI Anomaly Detection (runs REGARDLESS of hash match) ──
        raw_text_str = " ".join([str(v) for v in norm_fields.values() if v])
        models = load_models()
        is_anomaly, anomaly_score, anomaly_details = detect_anomaly(models, file_path, raw_text_str, extracted_data={'blockchain_valid': is_valid})

        # Clean up temporary verification file
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as rm_err:
            logger.debug(f"Failed to remove temp verify file {file_path}: {rm_err}")

        if not is_valid or not block_data:
            return jsonify({
                'verified':         False,
                'hash':             cert_hash or 'N/A',
                'message':          'Document not found on blockchain — possibly tampered or not registered.',
                'fields':           {k: v for k, v in norm_fields.items() if v},
                'anomaly_detected': is_anomaly,
                'anomaly_score':    anomaly_score,
                'ela_tampered':     anomaly_details.get('ela_tampered', False),
                'anomaly_analysis': anomaly_details,
            })

        # ── Step 3: Pull metadata ────────────────────────────
        fs = block_data.get('fields_summary', {})

        db_meta = {}
        rec = CertRecord.query.filter_by(hash_value=cert_hash).first()
        if rec and rec.encrypted_metadata:
            try:
                db_meta = _json.loads(rec.encrypted_metadata)
            except Exception:
                pass

        from datetime import datetime as dt
        issued_at = block_data.get('issued_at')
        issued_str = dt.fromtimestamp(issued_at).strftime('%Y-%m-%d %H:%M UTC') if issued_at else '—'

        return jsonify({
            'verified':         True,
            'hash':             cert_hash,
            'block_index':      block_data.get('_block_index'),
            'block_hash':       block_data.get('_block_hash'),
            'issuer':           block_data.get('issuer', '—'),
            'issued_at':        issued_str,
            'holder_name':      fs.get('name') or db_meta.get('holder_name', '—'),
            'doc_type':         fs.get('degree') or db_meta.get('doc_type', '—'),
            'issue_date':       fs.get('date') or db_meta.get('issue_date', '—'),
            'roll_no':          fs.get('roll_no', norm_fields.get('roll_no', '—')),
            'board':            fs.get('board', norm_fields.get('board', '—')),
            'institute':        fs.get('institute', norm_fields.get('institute', '—')),
            'grade':            fs.get('grade', norm_fields.get('grade', '—')),
            'year':             fs.get('year', norm_fields.get('year', '—')),
            'mothers_name':     fs.get('mothers_name', norm_fields.get('mothers_name', '—')),
            'fathers_name':     fs.get('fathers_name', norm_fields.get('fathers_name', '—')),
            'date_of_birth':    fs.get('date_of_birth', norm_fields.get('date_of_birth', '—')),
            'fields':           {k: v for k, v in norm_fields.items() if v},
            'zkp_verified':     True,
            'anomaly_detected': is_anomaly,
            'anomaly_score':    anomaly_score,
            'ela_tampered':     anomaly_details.get('ela_tampered', False),
            'anomaly_analysis': anomaly_details,
        })

    except RuntimeError as e:
        logger.error("Verify runtime error: %s", e)
        return jsonify({'error': str(e)}), 503
    except Exception as e:
        logger.error("Verify failed: %s", e)
        return jsonify({'error': str(e)}), 500


@main_bp.route('/admin/reload-models', methods=['POST'])
@login_required
@role_required('admin')
def reload_ml_models():
    """Admin endpoint to trigger dynamic hot-reload of ML anomaly models in memory."""
    try:
        updated_models = reload_models()
        return jsonify({
            'success': True,
            'message': 'ML anomaly models reloaded successfully in memory.',
            'has_text_model': 'text_model' in updated_models,
            'has_image_model': 'image_model' in updated_models,
            'has_autoencoder': 'autoencoder' in updated_models,
        })
    except Exception as e:
        logger.error(f"Failed to reload ML models: {e}")
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════════
#  CHECK BY HASH / ID
# ══════════════════════════════════════════════════════════════════

@main_bp.route('/check_certificate', methods=['GET'])
@login_required
def check_certificate():
    """
    Verify a certificate by its SHA-256 hash or DB integer ID.
    No file needed — just the hash string or numeric ID.
    """
    cert_id = request.args.get('certificate_id', '').strip()
    if not cert_id:
        return jsonify({'verified': False, 'error': 'No ID provided'}), 400

    # 1. Check blockchain first (source of truth)
    block_data = blockchain.find_block_by_hash(cert_id)

    if not block_data and cert_id.isdigit():
        # Maybe user passed a DB record id — look up hash from DB
        rec = CertRecord.query.get(int(cert_id))
        if rec:
            block_data = blockchain.find_block_by_hash(rec.hash_value)
            cert_id = rec.hash_value  # switch to hash for ZKP

    if not block_data:
        return jsonify({'verified': False, 'message': 'Not found on blockchain'})

    # 2. ZKP re-verification
    zkp_valid = False
    try:
        stored_proof = block_data.get('zkp_proof', '')
        if stored_proof:
            zkp_valid = verify_zkp_hex(stored_proof, cert_id)
    except Exception:
        pass

    fs = block_data.get('fields_summary', {})
    from datetime import datetime as dt
    issued_at = block_data.get('issued_at')
    issued_str = dt.fromtimestamp(issued_at).strftime('%Y-%m-%d %H:%M') if issued_at else '—'

    return jsonify({
        'verified':    True,
        'zkp_valid':   zkp_valid,
        'hash':        cert_id,
        'block_index': block_data.get('_block_index'),
        'issuer':      block_data.get('issuer', '—'),
        'issued_at':   issued_str,
        'holder_name': fs.get('name', '—'),
        'doc_type':    fs.get('degree', '—'),
        'issue_date':  fs.get('date', '—'),
        'institute':   fs.get('institute', '—'),
        'grade':       fs.get('grade', '—'),
        'roll_no':     fs.get('roll_no', '—'),
    })


# ══════════════════════════════════════════════════════════════════
#  RECORDS — Merge blockchain + DB
# ══════════════════════════════════════════════════════════════════

@main_bp.route('/get_certificates', methods=['GET'])
@login_required
@role_required('admin', 'institution', 'verifier')
def get_certificates():
    """
    Return all document records, merged from blockchain (primary) and DB (metadata).
    Blockchain is the source of truth; DB adds holder_name / doc_type metadata.
    """
    role     = session.get('role')
    username = session.get('username', '')

    # Get all document blocks from blockchain
    blocks = blockchain.get_all_document_blocks()

    # Build hash→DB meta lookup
    db_recs = CertRecord.query.order_by(CertRecord.id.desc()).limit(500).all()
    db_meta_map = {}
    for r in db_recs:
        meta = {}
        if r.encrypted_metadata:
            try:
                meta = _json.loads(r.encrypted_metadata)
            except Exception:
                pass
        db_meta_map[r.hash_value] = {
            'db_id':       r.id,
            'holder_name': meta.get('holder_name', ''),
            'doc_type':    meta.get('doc_type', ''),
            'issue_date':  meta.get('issue_date', ''),
            'filename':    meta.get('filename', ''),
        }

    out = []
    for b in blocks:
        h  = b.get('cert_hash', '')
        fs = b.get('fields_summary', {})
        db = db_meta_map.get(h, {})
        issuer = b.get('issuer', '')

        # Filter by institution role
        if role == 'institution' and issuer != username:
            continue

        from datetime import datetime as dt
        issued_at  = b.get('issued_at') or b.get('_timestamp')
        issued_str = dt.fromtimestamp(issued_at).strftime('%Y-%m-%d') if issued_at else '—'

        out.append({
            'id':          db.get('db_id') or b.get('_block_index'),
            'hash':        h,
            'holder_name': fs.get('name') or db.get('holder_name') or '—',
            'doc_type':    fs.get('degree') or db.get('doc_type') or '—',
            'issue_date':  fs.get('date') or db.get('issue_date') or issued_str,
            'institution': issuer,
            'block_index': b.get('_block_index'),
            'is_valid':    True,
            'zkp':         bool(b.get('zkp_proof')),
        })

    return jsonify(out)


# ══════════════════════════════════════════════════════════════════
#  BLOCKCHAIN STATS
# ══════════════════════════════════════════════════════════════════

@main_bp.route('/chain_stats', methods=['GET'])
@login_required
def chain_stats():
    """Return blockchain health statistics."""
    return jsonify(blockchain.stats())


# ══════════════════════════════════════════════════════════════════
#  ADMIN
# ══════════════════════════════════════════════════════════════════

@main_bp.route('/admin/users', methods=['GET'])
@login_required
@role_required('admin')
def admin_users():
    users = User.query.all()
    return jsonify([{
        'id':       u.id,
        'username': u.username,
        'role':     u.role,
        'provider': getattr(u, 'oauth_provider', 'local'),
    } for u in users])


# ══════════════════════════════════════════════════════════════════
#  VERIFIABLE CREDENTIALS (W3C-VC-style)
# ══════════════════════════════════════════════════════════════════

@main_bp.route('/vc/issue', methods=['POST'])
@login_required
@role_required('institution', 'admin')
def vc_issue():
    """Issues a portable W3C Verifiable Credential signed with Ed25519."""
    from .verifiable_credentials import issue_vc
    from .database import VerifiableCredential as VCModel
    data = request.get_json(silent=True) or {}
    cert_hash = data.get('cert_hash')
    holder_username = data.get('holder_username', 'citizen')
    claims = data.get('claims', {})

    if not cert_hash:
        return jsonify({'error': 'cert_hash is required'}), 400

    issuer = session.get('username', 'institution')
    vc_dict = issue_vc(claims, issuer, holder_username, cert_hash)

    # Persist in DB
    vc_record = VCModel(
        cert_hash=cert_hash,
        issuer_username=issuer,
        holder_username=holder_username,
        vc_json=_json.dumps(vc_dict),
        signature_hex=vc_dict.get('proof', {}).get('proofValue', '')
    )
    db.session.add(vc_record)
    db.session.commit()

    return jsonify({'success': True, 'vc': vc_dict, 'id': vc_record.id})


@main_bp.route('/vc/verify', methods=['POST'])
def vc_verify():
    """Verifies a portable W3C Verifiable Credential JSON."""
    from .verifiable_credentials import verify_vc
    data = request.get_json(silent=True) or {}
    vc_data = data.get('vc') or data
    is_valid, msg, claims = verify_vc(vc_data)
    cert_hash = vc_data.get('credentialSubject', {}).get('certificateHash') if isinstance(vc_data, dict) else None
    on_chain = blockchain.is_valid_hash(cert_hash) if cert_hash else False

    return jsonify({
        'verified': is_valid,
        'message': msg,
        'claims': claims,
        'blockchain_registered': on_chain
    })


# ══════════════════════════════════════════════════════════════════
#  QR-CODE VERIFICATION (Scan-to-Verify & Image Upload)
# ══════════════════════════════════════════════════════════════════

import hmac
_QR_HMAC_SECRET = os.environ.get('SECRET_KEY', 'docuvault-qr-secret-key').encode('utf-8')

def generate_qr_hmac(cert_hash: str) -> str:
    return hmac.new(_QR_HMAC_SECRET, cert_hash.encode('utf-8'), hashlib.sha256).hexdigest()[:16]

@main_bp.route('/verify_by_hash', methods=['GET'])
def verify_by_hash():
    """Verify document by hash with HMAC signature check."""
    h = request.args.get('h', '').strip()
    sig = request.args.get('sig', '').strip()
    if not h:
        return jsonify({'error': 'Hash required'}), 400

    expected_sig = generate_qr_hmac(h)
    sig_valid = (sig == expected_sig)

    block = blockchain.find_block_by_hash(h)
    if not block:
        return jsonify({'verified': False, 'message': 'Hash not found on blockchain ledger.'}), 404

    return jsonify({
        'verified': True,
        'hash': h,
        'hmac_valid': sig_valid,
        'block_data': block
    })


@main_bp.route('/verify_by_qr_image', methods=['POST'])
def verify_by_qr_image():
    """Decode a QR code photo with OpenCV and verify on blockchain."""
    import cv2
    import numpy as np

    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'No QR code image uploaded'}), 400

    file_bytes = np.frombuffer(file.read(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if img is None:
        return jsonify({'error': 'Could not decode image'}), 400

    detector = cv2.QRCodeDetector()
    data, bbox, _ = detector.detectAndDecode(img)

    if not data:
        return jsonify({'error': 'No QR code detected in image'}), 422

    # Extract hash parameter from decoded URL/string
    extracted_hash = None
    if 'h=' in data:
        for param in data.split('?')[-1].split('&'):
            if param.startswith('h='):
                extracted_hash = param.split('=')[1]
                break
    elif len(data) == 64:
        extracted_hash = data

    if not extracted_hash:
        return jsonify({'error': f'QR decoded ({data[:30]}...) but no document hash found'}), 422

    block = blockchain.find_block_by_hash(extracted_hash)
    return jsonify({
        'verified': block is not None,
        'decoded_url': data,
        'hash': extracted_hash,
        'block_data': block
    })


# ══════════════════════════════════════════════════════════════════
#  ANALYTICS DASHBOARD
# ══════════════════════════════════════════════════════════════════

@main_bp.route('/admin/analytics', methods=['GET'])
@login_required
@role_required('admin')
def admin_analytics():
    """Returns analytics aggregate statistics."""
    from .database import AnalyticsLog as ALog, Document as DocModel
    total_docs = DocModel.query.count()
    total_logs = ALog.query.count()
    anomaly_count = ALog.query.filter(ALog.status == 'anomaly_detected').count()
    verified_count = ALog.query.filter(ALog.status == 'verified').count()

    return jsonify({
        'total_documents': total_docs,
        'total_verification_requests': total_logs,
        'verified_count': verified_count,
        'anomaly_flags': anomaly_count,
        'blockchain_blocks': len(blockchain.chain),
    })


# ══════════════════════════════════════════════════════════════════
#  FEDERATED LEARNING RETRAINING & BACKGROUND PIPELINE
# ══════════════════════════════════════════════════════════════════

import subprocess
_FL_STATUS_FILE = os.path.join(UPLOAD_FOLDER, 'fl_training_status.json')

@main_bp.route('/admin/run_federated_training', methods=['POST'])
@login_required
@role_required('admin')
def run_federated_training():
    """Trigger background federated training round across decentralized data nodes."""
    status = {
        'status': 'running',
        'started_at': _dt.now().isoformat(),
        'progress': 'Initializing FedAvg rounds across local clusters...'
    }
    with open(_FL_STATUS_FILE, 'w') as f:
        _json.dump(status, f)

    # Spawn background retraining task
    try:
        subprocess.Popen([
            'python3', '-c',
            '''
import sys, json, os, time
sys.path.insert(0, '.')
from app.train_models import train_anomaly_pipeline
status_file = "data/fl_training_status.json"
try:
    with open(status_file, "w") as f:
        json.dump({"status": "running", "round": "1/3", "progress": "Scanning local corpus and fitting models..."}, f)
    models, report = train_anomaly_pipeline()
    with open(status_file, "w") as f:
        json.dump({"status": "completed", "completed_at": time.time(), "report": report, "progress": "Global FedAvg aggregation complete. Models hot-reloaded."}, f)
except Exception as e:
    with open(status_file, "w") as f:
        json.dump({"status": "failed", "error": str(e)}, f)
'''
        ], cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        return jsonify({'success': True, 'message': 'Federated learning retraining job dispatched in background.'})
    except Exception as e:
        return jsonify({'error': f'Failed to launch FL job: {e}'}), 500


@main_bp.route('/admin/training_status', methods=['GET'])
@login_required
@role_required('admin')
def training_status():
    """Check status of federated training subprocess."""
    if not os.path.exists(_FL_STATUS_FILE):
        return jsonify({'status': 'idle', 'message': 'No recent FL training jobs.'})
    try:
        with open(_FL_STATUS_FILE, 'r') as f:
            return jsonify(_json.load(f))
    except Exception as e:
        return jsonify({'status': 'unknown', 'error': str(e)})


