# from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
# from .auth import login_required, role_required
# from .ocr import process_upload, verify_upload
# from .legacy_ocr import process_legacy_upload
# from .blockchain import blockchain
# from .zkp import generate_zkp_proof, verify_zkp_proof
# from .pqc import pqc_encrypt
# from .database_models import User
# from . import db
# from werkzeug.utils import secure_filename
# import os
# import logging

# logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)

# main_bp = Blueprint('main', __name__)

# UPLOAD_FOLDER = 'data'
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# @main_bp.route('/')
# def index():
#     if 'user_id' in session:
#         return redirect(url_for('main.dashboard', role=session.get('role')))
#     return redirect(url_for('auth.login'))

# @main_bp.route('/dashboard/<role>')
# @login_required
# @role_required('admin', 'institution', 'verifier')
# def dashboard(role):
#     return render_template('index.html')

# @main_bp.route('/upload', methods=['POST'])
# @login_required
# @role_required('institution')
# def upload():
#     files = request.files.getlist('file')
#     logger.debug(f"Received {len(files)} files for upload. Form keys: {list(request.files.keys())}")
#     results = []
#     for file in files:
#         if file and file.filename:
#             filename = secure_filename(file.filename)
#             file_path = os.path.join(UPLOAD_FOLDER, filename)
#             logger.debug(f"Processing file: {filename}")
#             try:
#                 file.save(file_path)
#                 logger.debug(f"File saved to: {file_path}")
#                 cert_hash = process_upload(file_path, 'institution')
#                 proof = generate_zkp_proof(cert_hash)
#                 enc_hash, _ = pqc_encrypt(cert_hash)
#                 results.append({'hash': cert_hash, 'zkp': proof, 'encrypted_hash': enc_hash.hex(), 'filename': filename})
#             except Exception as e:
#                 logger.error(f"Upload failed for {filename}: {str(e)}")
#                 results.append({'error': f'Upload failed for {filename}: {str(e)}', 'valid': False, 'hash': 'N/A', 'filename': filename})
#         else:
#             logger.warning("Invalid or empty file provided")
#             results.append({'error': 'Invalid or empty file provided', 'valid': False, 'hash': 'N/A', 'filename': 'N/A'})
#     if not results:
#         logger.error("No valid files uploaded")
#         return jsonify({'error': 'No valid files uploaded', 'results': []}), 400
#     logger.debug(f"Upload results: {results}")
#     return jsonify({'results': results})

# @main_bp.route('/verify', methods=['POST'])
# @login_required
# @role_required('verifier', 'admin')
# def verify():
#     files = request.files.getlist('file')
#     logger.debug(f"Received {len(files)} files for verification. Form keys: {list(request.files.keys())}")
#     results = []
#     for file in files:
#         if file and file.filename:
#             filename = secure_filename(file.filename)
#             file_path = os.path.join(UPLOAD_FOLDER, filename)
#             logger.debug(f"Processing file: {filename}")
#             try:
#                 file.save(file_path)
#                 logger.debug(f"File saved to: {file_path}")
#                 is_valid, cert_hash = verify_upload(file_path)
#                 proof = generate_zkp_proof(cert_hash) if cert_hash else None
#                 zkp_valid = verify_zkp_proof(proof, cert_hash) if proof and cert_hash else False
#                 results.append({
#                     'valid': bool(is_valid and zkp_valid),
#                     'hash': cert_hash or 'N/A',
#                     'filename': filename,
#                     'error': None
#                 })
#             except Exception as e:
#                 logger.error(f"Verification failed for {filename}: {str(e)}")
#                 results.append({'error': f'Verification failed for {filename}: {str(e)}', 'valid': False, 'hash': 'N/A', 'filename': filename})
#         else:
#             logger.warning("Invalid or empty file provided")
#             results.append({'error': 'Invalid or empty file provided', 'valid': False, 'hash': 'N/A', 'filename': 'N/A'})
#     if not results:
#         logger.error("No valid files uploaded for verification")
#         return jsonify({'error': 'No valid files uploaded', 'results': []}), 400
#     logger.debug(f"Verification results: {results}")
#     return jsonify({'results': results})

# @main_bp.route('/verify-legacy', methods=['POST'])
# @login_required
# @role_required('verifier', 'admin')
# def verify_legacy():
#     files = request.files.getlist('file')
#     logger.debug(f"Received {len(files)} files for legacy verification. Form keys: {list(request.files.keys())}")
#     results = []
#     for file in files:
#         if file and file.filename:
#             filename = secure_filename(file.filename)
#             file_path = os.path.join(UPLOAD_FOLDER, filename)
#             logger.debug(f"Processing legacy file: {filename}")
#             try:
#                 file.save(file_path)
#                 logger.debug(f"File saved to: {file_path}")
#                 is_valid, cert_hash, error = process_legacy_upload(file_path, session.get('role'))
#                 results.append({
#                     'valid': bool(is_valid),
#                     'hash': cert_hash if cert_hash is not None else 'N/A',
#                     'filename': filename,
#                     'error': error if error else None  # Ensure error includes anomaly score
#                 })
#             except Exception as e:
#                 logger.error(f"Legacy verification failed for {filename}: {str(e)}")
#                 results.append({
#                     'error': f'Legacy verification failed: {str(e)}',
#                     'valid': False,
#                     'hash': 'N/A',
#                     'filename': filename
#                 })
#         else:
#             logger.warning("Invalid or empty file provided for legacy verification")
#             results.append({
#                 'error': 'Invalid or empty file provided',
#                 'valid': False,
#                 'hash': 'N/A',
#                 'filename': 'N/A'
#             })
#     if not results:
#         logger.error("No valid files uploaded for legacy verification")
#         return jsonify({'error': 'No valid files uploaded', 'results': []}), 400
#     logger.debug(f"Legacy verification results: {results}")
#     return jsonify({'results': results})

# @main_bp.route('/admin/users', methods=['GET'])
# @login_required
# @role_required('admin')
# def admin_users():
#     users = User.query.all()
#     logger.debug(f"Listing users: {len(users)} found")
#     return jsonify([{'id': u.id, 'username': u.username, 'role': u.role} for u in users])



from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from .auth import login_required, role_required
from .ocr import process_upload, verify_upload
from .legacy_ocr import process_legacy_upload
from .blockchain import blockchain
from .zkp import generate_zkp_proof, verify_zkp_proof
from .pqc import pqc_encrypt
from .database_models import User
from . import db
from werkzeug.utils import secure_filename
import os
import logging

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
@role_required('admin', 'institution', 'verifier')
def dashboard(role):
    return render_template('index.html')

# Old upload route removed — replaced by upload_doc below

@main_bp.route('/verify', methods=['POST'])
@login_required
@role_required('verifier', 'admin')
def verify():
    files = request.files.getlist('file')
    logger.debug(f"Received {len(files)} files for verification. Form keys: {list(request.files.keys())}")
    results = []
    for file in files:
        if file and file.filename:
            filename = secure_filename(file.filename)
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            logger.debug(f"Processing file: {filename}")
            try:
                file.save(file_path)
                logger.debug(f"File saved to: {file_path}")
                is_valid, cert_hash = verify_upload(file_path)
                proof = generate_zkp_proof(cert_hash) if cert_hash else None
                zkp_valid = verify_zkp_proof(proof, cert_hash) if proof and cert_hash else False
                results.append({
                    'valid': bool(is_valid and zkp_valid),
                    'hash': cert_hash or 'N/A',
                    'filename': filename,
                    'error': None
                })
            except Exception as e:
                logger.error(f"Verification failed for {filename}: {str(e)}")
                results.append({'error': f'Verification failed for {filename}: {str(e)}', 'valid': False, 'hash': 'N/A', 'filename': filename})
        else:
            logger.warning("Invalid or empty file provided")
            results.append({'error': 'Invalid or empty file provided', 'valid': False, 'hash': 'N/A', 'filename': 'N/A'})
    if not results:
        logger.error("No valid files uploaded for verification")
        return jsonify({'error': 'No valid files uploaded', 'results': []}), 400
    logger.debug(f"Verification results: {results}")
    return jsonify({'results': results})

@main_bp.route('/verify-legacy', methods=['POST'])
@login_required
@role_required('verifier', 'admin')
def verify_legacy():
    files = request.files.getlist('file')
    logger.debug(f"Received {len(files)} files for legacy verification. Form keys: {list(request.files.keys())}")
    results = []
    for file in files:
        if file and file.filename:
            filename = secure_filename(file.filename)
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            logger.debug(f"Processing legacy file: {filename}")
            try:
                file.save(file_path)
                logger.debug(f"File saved to: {file_path}")
                is_valid, cert_hash, error = process_legacy_upload(file_path, session.get('role'))
                results.append({
                    'valid': bool(is_valid),
                    'hash': cert_hash if cert_hash is not None else 'N/A',
                    'filename': filename,
                    'error': error if error else None  # Ensure error includes anomaly score
                })
            except Exception as e:
                logger.error(f"Legacy verification failed for {filename}: {str(e)}")
                results.append({
                    'error': f'Legacy verification failed: {str(e)}',
                    'valid': False,
                    'hash': 'N/A',
                    'filename': filename
                })
        else:
            logger.warning("Invalid or empty file provided for legacy verification")
            results.append({
                'error': 'Invalid or empty file provided',
                'valid': False,
                'hash': 'N/A',
                'filename': 'N/A'
            })
    if not results:
        logger.error("No valid files uploaded for legacy verification")
        return jsonify({'error': 'No valid files uploaded', 'results': []}), 400
    logger.debug(f"Legacy verification results: {results}")
    return jsonify({'results': results})

@main_bp.route('/admin/users', methods=['GET'])
@login_required
@role_required('admin')
def admin_users():
    users = User.query.all()
    logger.debug(f"Listing users: {len(users)} found")
    return jsonify([{'id': u.id, 'username': u.username, 'role': u.role} for u in users])


# ── New UI API routes ──────────────────────────────────────────

from .database_models import CertificateRecord as CertRecord
import json as _json
from datetime import datetime as _dt

@main_bp.route('/upload', methods=['POST'])
@login_required
@role_required('institution', 'admin')
def upload_doc():
    """Upload + register document on blockchain, storing metadata."""
    file = request.files.get('file')
    holder_name = request.form.get('holder_name', 'Unknown')
    doc_type    = request.form.get('doc_type', 'Document')
    issue_date  = request.form.get('issue_date', str(_dt.utcnow().date()))

    if not file or not file.filename:
        return jsonify({'error': 'No file provided'}), 400

    filename  = secure_filename(file.filename)
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    try:
        file.save(file_path)
        cert_hash = process_upload(file_path, session.get('username', 'institution'))
        proof     = generate_zkp_proof(cert_hash)
        enc_hash, _ = pqc_encrypt(cert_hash)

        # Store in DB with metadata
        meta = _json.dumps({'holder_name': holder_name, 'doc_type': doc_type, 'issue_date': issue_date, 'filename': filename})
        try:
            rec = CertRecord(hash_value=cert_hash, institution=session.get('username', 'institution'), is_valid=True, encrypted_metadata=meta)
            db.session.add(rec)
            db.session.commit()
            rec_id = rec.id
        except Exception as db_err:
            db.session.rollback()
            logger.warning(f"DB save skipped: {db_err}")
            rec_id = None

        return jsonify({'success': True, 'hash': cert_hash, 'id': rec_id, 'filename': filename, 'holder_name': holder_name, 'doc_type': doc_type})
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return jsonify({'error': str(e)}), 500


@main_bp.route('/verify_document', methods=['POST'])
@login_required
@role_required('verifier', 'admin', 'institution')
def verify_document():
    """Verify a document file against the blockchain."""
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'No file provided'}), 400

    filename  = secure_filename(file.filename)
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    try:
        file.save(file_path)
        is_valid, cert_hash = verify_upload(file_path)
        proof    = generate_zkp_proof(cert_hash) if cert_hash else None
        zkp_valid = verify_zkp_proof(proof, cert_hash) if proof and cert_hash else False

        # Look up metadata from DB
        meta = {}
        rec = CertRecord.query.filter_by(hash_value=cert_hash).first() if cert_hash else None
        if rec and rec.encrypted_metadata:
            try:
                meta = _json.loads(rec.encrypted_metadata)
            except Exception:
                pass

        return jsonify({
            'verified': bool(is_valid and zkp_valid),
            'hash': cert_hash or 'N/A',
            'filename': filename,
            'holder_name': meta.get('holder_name'),
            'doc_type':    meta.get('doc_type'),
            'issue_date':  meta.get('issue_date'),
            'id': rec.id if rec else None,
        })
    except Exception as e:
        logger.error(f"Verify failed: {e}")
        return jsonify({'error': str(e)}), 500


@main_bp.route('/check_certificate', methods=['GET'])
@login_required
def check_certificate():
    """Verify a certificate by its hash or DB id."""
    cert_id = request.args.get('certificate_id', '').strip()
    if not cert_id:
        return jsonify({'verified': False, 'error': 'No ID provided'}), 400

    # Try by hash first, then by integer id
    rec = CertRecord.query.filter_by(hash_value=cert_id).first()
    if not rec and cert_id.isdigit():
        rec = CertRecord.query.get(int(cert_id))

    if not rec:
        return jsonify({'verified': False, 'message': 'Not found on blockchain'})

    meta = {}
    if rec.encrypted_metadata:
        try:
            meta = _json.loads(rec.encrypted_metadata)
        except Exception:
            pass

    return jsonify({
        'verified': bool(rec.is_valid),
        'id': rec.id,
        'hash': rec.hash_value,
        'holder_name': meta.get('holder_name', '—'),
        'doc_type':    meta.get('doc_type', '—'),
        'issue_date':  meta.get('issue_date', '—'),
        'institution': rec.institution,
    })


@main_bp.route('/get_certificates', methods=['GET'])
@login_required
@role_required('admin', 'institution', 'verifier')
def get_certificates():
    """Return paginated list of certificate records."""
    role = session.get('role')
    username = session.get('username', '')
    if role == 'institution':
        recs = CertRecord.query.filter_by(institution=username).order_by(CertRecord.id.desc()).limit(100).all()
    else:
        recs = CertRecord.query.order_by(CertRecord.id.desc()).limit(100).all()

    out = []
    for r in recs:
        meta = {}
        if r.encrypted_metadata:
            try:
                meta = _json.loads(r.encrypted_metadata)
            except Exception:
                pass
        out.append({
            'id': r.id,
            'hash': r.hash_value,
            'holder_name': meta.get('holder_name', '—'),
            'doc_type':    meta.get('doc_type', '—'),
            'issue_date':  meta.get('issue_date', '—'),
            'institution': r.institution,
            'is_valid': r.is_valid,
        })
    return jsonify(out)