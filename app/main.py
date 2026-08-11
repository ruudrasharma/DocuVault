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

@main_bp.route('/upload', methods=['POST'])
@login_required
@role_required('institution')
def upload():
    files = request.files.getlist('file')
    logger.debug(f"Received {len(files)} files for upload. Form keys: {list(request.files.keys())}")
    results = []
    for file in files:
        if file and file.filename:
            filename = secure_filename(file.filename)
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            logger.debug(f"Processing file: {filename}")
            try:
                file.save(file_path)
                logger.debug(f"File saved to: {file_path}")
                cert_hash = process_upload(file_path, 'institution')
                proof = generate_zkp_proof(cert_hash)
                enc_hash, _ = pqc_encrypt(cert_hash)
                results.append({'hash': cert_hash, 'zkp': proof, 'encrypted_hash': enc_hash.hex(), 'filename': filename})
            except Exception as e:
                logger.error(f"Upload failed for {filename}: {str(e)}")
                results.append({'error': f'Upload failed for {filename}: {str(e)}', 'valid': False, 'hash': 'N/A', 'filename': filename})
        else:
            logger.warning("Invalid or empty file provided")
            results.append({'error': 'Invalid or empty file provided', 'valid': False, 'hash': 'N/A', 'filename': 'N/A'})
    if not results:
        logger.error("No valid files uploaded")
        return jsonify({'error': 'No valid files uploaded', 'results': []}), 400
    logger.debug(f"Upload results: {results}")
    return jsonify({'results': results})

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