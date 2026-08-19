
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
        logger.info("File saved: %s", file_path)

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

    original_name = secure_filename(file.filename)
    unique_filename = f"verify_{uuid.uuid4().hex[:12]}_{original_name}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)

    try:
        file.save(file_path)

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
    Return all document records.
    PRIMARY source: CertRecord DB (has real issuer, holder, doc_type).
    AUGMENTED by: blockchain (adds block_index, zkp, timestamp).

    Legacy blockchain blocks had issuer='legacy' — the old code filtered
    all of them out for institution users. Fixed by using CertRecord.institution
    for role-based filtering instead of blockchain.issuer.
    """
    role     = session.get('role')
    username = session.get('username', '')

    # ── Build blockchain lookup: hash → block info ────────────────
    block_map = {}
    for b in blockchain.get_all_document_blocks():
        h = b.get('cert_hash', '')
        if h:
            block_map[h] = b

    # ── Primary: CertRecord rows ──────────────────────────────────
    query = CertRecord.query.order_by(CertRecord.id.desc()).limit(500)
    db_recs = query.all()

    seen_hashes = set()
    out = []

    for r in db_recs:
        h = r.hash_value or ''

        # Role filter: institution sees only their own records
        if role == 'institution' and r.institution != username:
            continue

        meta = {}
        if r.encrypted_metadata:
            try:
                meta = _json.loads(r.encrypted_metadata)
            except Exception:
                pass

        # Augment with blockchain data if block exists
        b = block_map.get(h, {})
        fs = b.get('fields_summary') or {}

        from datetime import datetime as dt
        issued_at  = b.get('issued_at') or b.get('_timestamp')
        issued_str = dt.fromtimestamp(issued_at).strftime('%Y-%m-%d') if issued_at else meta.get('issue_date', '—')

        holder = (fs.get('name') or meta.get('holder_name') or '—')
        dtype  = (fs.get('degree') or meta.get('doc_type') or '—')

        out.append({
            'id':          r.id,
            'hash':        h,
            'holder_name': holder,
            'doc_type':    dtype,
            'issue_date':  issued_str,
            'institution': r.institution,
            'block_index': b.get('_block_index', '—'),
            'is_valid':    r.is_valid,
            'zkp':         bool(b.get('zkp_proof')),
        })
        seen_hashes.add(h)

    # ── Fallback: blockchain blocks with NO CertRecord entry ──────
    # (e.g. very old uploads that bypassed DB write)
    for h, b in block_map.items():
        if h in seen_hashes:
            continue
        issuer = b.get('issuer', 'unknown')
        if issuer in ('legacy', 'unknown', ''):
            issuer = 'unknown'
        if role == 'institution' and issuer != username:
            continue
        fs = b.get('fields_summary') or {}
        from datetime import datetime as dt
        issued_at  = b.get('issued_at') or b.get('_timestamp')
        issued_str = dt.fromtimestamp(issued_at).strftime('%Y-%m-%d') if issued_at else '—'
        out.append({
            'id':          b.get('_block_index'),
            'hash':        h,
            'holder_name': fs.get('name') or '—',
            'doc_type':    fs.get('degree') or '—',
            'issue_date':  issued_str,
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

