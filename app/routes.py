from flask import render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_user, current_user, logout_user, login_required
from app import app, db
from app.auth_checker import extract_data, validate_data
from app.ml_anomaly import load_models, detect_anomaly
from app.blockchain import blockchain
from app.crypto_utils import generate_keys, sign_vc, embed_watermark
from app.qr_integration import generate_qr, verify_qr
from app.database_models import User, CertificateRecord, VerifiableCredential, AnalyticsLog
from app.national_integration import integrate_national
from app.biometrics import match_face
from werkzeug.utils import secure_filename
import os
import hashlib
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import time
import requests
import cv2
import tempfile
import json
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'data')
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

blockchain = blockchain

@app.route('/', methods=['GET', 'POST'])
def upload():
    ml_models = load_models()
    if request.method == 'POST':
        if 'manual' in request.form:
            extracted_data = {
                'name': request.form['name'],
                'roll': request.form['roll'],
                'grade': request.form['grade'],
                'id': request.form['id'],
                'institution': request.form['institution'],
                'uid': request.form['uid'] or f'UID_{int(time.time())}'
            }
            extracted_text = ' '.join(extracted_data.values())
            is_anomaly, anomaly_score = detect_anomaly(ml_models, None, extracted_text, extracted_data)
            if is_anomaly:
                logger.warning(f"Manual entry anomaly detected: Score {anomaly_score}")
                flash(f"Anomaly detected: Score {anomaly_score}", 'error')
                return redirect(url_for('upload'))
            is_valid = validate_data(extracted_data, blockchain, None, is_legacy=True)
            if is_valid:
                flash('Manual entry validated successfully.', 'success')
            else:
                flash('Validation failed.', 'error')
            return redirect(url_for('upload'))
        if 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                flash('No file selected.', 'error')
                return redirect(request.url)
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                extracted_data, extracted_text = extract_data(file_path)
                if extracted_data:
                    is_anomaly, anomaly_score = detect_anomaly(ml_models, file_path, extracted_text, extracted_data)
                    if is_anomaly:
                        logger.warning(f"Anomaly detected in {filename}: Score {anomaly_score}")
                        flash(f"Anomaly detected in {filename}: Score {anomaly_score}", 'error')
                    else:
                        is_valid = validate_data(extracted_data, blockchain, file_path, is_legacy=True)
                        if is_valid:
                            data_hash = hashlib.sha256(str(extracted_data).encode()).hexdigest()
                            record = CertificateRecord(
                                hash_value=data_hash,
                                institution=extracted_data['institution'],
                                is_valid=True,
                                encrypted_metadata=json.dumps(extracted_data)
                            )
                            db.session.add(record)
                            db.session.commit()
                            flash(f'Upload validated successfully for {filename}.', 'success')
                if os.path.exists(file_path):
                    os.remove(file_path)
                return redirect(url_for('upload'))
    return render_template('upload.html')

@app.route('/dashboard/<role>')
@login_required
@role_required('admin', 'institution', 'verifier')
def dashboard(role):
    return render_template('dashboard.html', role=role)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))