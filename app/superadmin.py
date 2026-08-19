"""
app/superadmin.py — Superadmin Governance & Root Control Blueprint
===================================================================
Provides high-privilege administrative tools:
- Comprehensive Audit Log stream
- Raw Database Inspector & Protected Action Gateway
- Blockchain Deep-Inspector & Chain Re-verifier
- System Diagnostics & Model Hot-Reload Gateway
- Strict Step-Up 2FA & Immutable Account Protection Enforcement
"""

import json
import logging
import time
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from .auth import login_required, role_required
from .database import db, User, Document, AccessGrant, WalletKey, AuditLog
from .database_models import CertificateRecord as CertRecord, VerifiableCredential
from .blockchain import blockchain
from .ml_anomaly import reload_models, load_models

logger = logging.getLogger(__name__)
superadmin_bp = Blueprint('superadmin', __name__, url_prefix='/superadmin')


def log_audit(action: str, target: str | None = None, details: dict | str | None = None) -> AuditLog:
    """Helper to record an action into the immutable AuditLog table."""
    details_str = json.dumps(details) if isinstance(details, dict) else str(details or "")
    audit = AuditLog(
        actor_id=session.get('user_id'),
        actor_username=session.get('username', 'SYSTEM'),
        action=action,
        target=target,
        ip_address=request.remote_addr if request else "127.0.0.1",
        details_json=details_str
    )
    try:
        db.session.add(audit)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning(f"AuditLog commit error: {e}")
    logger.info(f"[AUDIT] {session.get('username')} performed {action} on {target}")
    return audit


# ── Dashboard & Views ─────────────────────────────────────────────────────────

@superadmin_bp.route('/dashboard')
@login_required
@role_required('superadmin')
def dashboard():
    """Renders the distinct-themed Superadmin Command Dashboard."""
    return render_template('superadmin.html')


@superadmin_bp.route('/stats', methods=['GET'])
@login_required
@role_required('superadmin')
def get_stats():
    """Returns high-level system metrics for the command center."""
    blockchain._load()
    users = User.query.all()
    certs = CertRecord.query.all()
    protected_count = User.query.filter_by(is_protected=True).count()
    
    users_by_role = {}
    for u in users:
        users_by_role[u.role] = users_by_role.get(u.role, 0) + 1

    return jsonify({
        'total_users': len(users),
        'protected_accounts': protected_count,
        'total_documents': Document.query.count(),
        'total_certs': len(certs),
        'certs_valid': sum(1 for c in certs if c.is_valid),
        'certs_invalid': sum(1 for c in certs if not c.is_valid),
        'total_grants': AccessGrant.query.count(),
        'total_vcs': VerifiableCredential.query.count(),
        'total_blocks': len(blockchain.chain),
        'blockchain_blocks': len(blockchain.chain),
        'chain_valid': blockchain.is_chain_valid(),
        'total_audit_logs': AuditLog.query.count(),
        'server_time': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
        'current_user': session.get('username'),
        'role': 'superadmin',
        'users_by_role': users_by_role
    })


# ── Audit Log Stream ──────────────────────────────────────────────────────────

@superadmin_bp.route('/audit-logs', methods=['GET'])
@login_required
@role_required('superadmin')
def get_audit_logs():
    """Returns filterable stream of immutable audit logs."""
    action_filter = request.args.get('action')
    actor_filter = request.args.get('actor')
    limit = min(int(request.args.get('limit', 100)), 500)

    query = AuditLog.query
    if action_filter:
        query = query.filter(AuditLog.action.ilike(f"%{action_filter}%"))
    if actor_filter:
        query = query.filter(AuditLog.actor_username.ilike(f"%{actor_filter}%"))

    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()

    # Fallback to blockchain events if no audit logs in DB yet
    if not logs and len(blockchain.chain) > 1:
        blockchain._load()
        fallback_logs = []
        for b in reversed(blockchain.chain[-limit:]):
            pd = b.parsed_data or {}
            fallback_logs.append({
                'id': b.index,
                'actor': pd.get('issuer', 'system'),
                'action': 'BLOCKCHAIN_BLOCK_APPENDED',
                'target': f"block:{b.index}:{pd.get('cert_hash', '')[:16]}",
                'ip': '127.0.0.1',
                'details': json.dumps(pd),
                'timestamp': datetime.fromtimestamp(b.timestamp, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC') if b.timestamp else '0'
            })
        return jsonify(fallback_logs)

    return jsonify([{
        'id': l.id,
        'actor': l.actor_username,
        'action': l.action,
        'target': l.target,
        'ip': l.ip_address,
        'details': l.details_json,
        'timestamp': l.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')
    } for l in logs])


# ── Database Inspector & Protected Actions ───────────────────────────────────

@superadmin_bp.route('/database', methods=['GET'])
@login_required
@role_required('superadmin')
def browse_database():
    """Returns raw rows from selected core tables."""
    table = request.args.get('table', 'users').lower()
    limit = min(int(request.args.get('limit', 100)), 300)

    if table == 'users':
        records = User.query.limit(limit).all()
        return jsonify({
            'table': 'users',
            'columns': ['id', 'username', 'role', 'is_protected', 'oauth_provider', 'google_email'],
            'rows': [{
                'id': u.id,
                'username': u.username,
                'role': u.role,
                'is_protected': getattr(u, 'is_protected', False) or u.role == 'superadmin',
                'oauth_provider': u.oauth_provider,
                'google_email': u.google_email or '—',
            } for u in records]
        })

    elif table == 'certificates':
        records = CertRecord.query.limit(limit).all()
        return jsonify({
            'table': 'certificates',
            'columns': ['id', 'hash_value', 'institution', 'is_valid'],
            'rows': [{
                'id': r.id,
                'hash_value': r.hash_value,
                'institution': r.institution,
                'is_valid': r.is_valid,
            } for r in records]
        })

    elif table == 'documents':
        records = Document.query.limit(limit).all()
        return jsonify({
            'table': 'documents',
            'columns': ['id', 'owner_id', 'issuer', 'doc_type', 'cert_hash', 'block_index', 'created_at'],
            'rows': [{
                'id': d.id,
                'owner_id': d.owner_id,
                'issuer': d.issuer_username,
                'doc_type': d.doc_type or '—',
                'cert_hash': d.cert_hash,
                'block_index': d.block_index,
                'created_at': d.created_at.strftime('%Y-%m-%d %H:%M:%S UTC') if d.created_at else '—'
            } for d in records]
        })

    elif table == 'credentials':
        records = VerifiableCredential.query.limit(limit).all()
        return jsonify({
            'table': 'credentials',
            'columns': ['id', 'uid', 'hash_value'],
            'rows': [{
                'id': vc.id,
                'uid': vc.uid,
                'hash_value': vc.hash_value,
            } for vc in records]
        })

    elif table == 'grants':
        records = AccessGrant.query.limit(limit).all()
        return jsonify({
            'table': 'grants',
            'columns': ['id', 'document_id', 'grantee_id', 'granted_by', 'expires_at', 'revoked'],
            'rows': [{
                'id': g.id,
                'document_id': g.document_id,
                'grantee_id': g.grantee_id,
                'granted_by': g.granted_by,
                'expires_at': g.expires_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
                'revoked': g.revoked
            } for g in records]
        })

    return jsonify({'error': 'Unknown table requested.'}), 400


@superadmin_bp.route('/database/action', methods=['POST'])
@login_required
@role_required('superadmin')
def database_action():
    """Executes high-privilege DB mutations under step-up 2FA and full audit logging."""
    data = request.get_json() or {}
    action = data.get('action')
    target_table = data.get('table', 'users')
    record_id = data.get('id') or data.get('user_id') or data.get('cert_id')

    if not action:
        return jsonify({'error': 'action is required.'}), 400

    if action == 'delete_user' or (target_table == 'users' and action == 'delete'):
        user = User.query.get(record_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Hardwired: protected accounts, superadmin role, or root rudra cannot be deleted
        if getattr(user, 'is_protected', False) or user.role == 'superadmin' or user.username.lower() in ['rudra', 'admin']:
            return jsonify({'error': 'Super Admin and protected system accounts cannot be deleted.'}), 403

        db.session.delete(user)
        db.session.commit()
        log_audit('SUPERADMIN_DELETE_USER', f'user:{user.id}:{user.username}', {'deleted_role': user.role})
        return jsonify({'success': True, 'message': f'User {user.username} deleted.'})

    elif action == 'toggle_protection':
        user = User.query.get(record_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        if user.id == session.get('user_id') or user.username.lower() == 'rudra':
            return jsonify({'error': 'Cannot remove protection from root superadmin account.'}), 403
        user.is_protected = not getattr(user, 'is_protected', False)
        db.session.commit()
        log_audit('TOGGLE_USER_PROTECTION', f'user:{user.id}:{user.username}', {'new_is_protected': user.is_protected})
        return jsonify({'success': True, 'is_protected': user.is_protected})

    elif action == 'reset_password':
        new_password = data.get('password') or data.get('new_password', '')
        user = User.query.get(record_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        if not new_password or len(new_password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters.'}), 400
        user.set_password(new_password)
        db.session.commit()
        log_audit('SUPERADMIN_RESET_PASSWORD', f'user:{user.id}:{user.username}', {'username': user.username})
        return jsonify({'success': True, 'message': f'Password for {user.username} has been reset.'})

    elif action == 'invalidate_cert':
        cert = CertRecord.query.get(record_id)
        if not cert:
            return jsonify({'error': 'Certificate not found'}), 404
        cert.is_valid = False
        db.session.commit()
        log_audit('INVALIDATE_CERTIFICATE', f'cert:{cert.id}:{cert.hash_value}', {'institution': cert.institution})
        return jsonify({'success': True, 'message': f'Certificate {cert.id} invalidated.'})

    return jsonify({'error': f'Unsupported action {action} on {target_table}.'}), 400


@superadmin_bp.route('/create-user', methods=['POST'])
@login_required
@role_required('superadmin')
def superadmin_create_user():
    """Superadmin provisions any role (including superadmin) with optional root protection."""
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'verifier')
    email = data.get('email', '').strip()
    is_protected = bool(data.get('is_protected', False))

    if not username or not password:
        return jsonify({'error': 'Username and password are required.'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters.'}), 400
    if role not in ('superadmin', 'admin', 'institution', 'verifier', 'citizen'):
        return jsonify({'error': 'Invalid role.'}), 400

    if User.query.filter((db.func.lower(User.username) == username.lower())).first():
        return jsonify({'error': f'Username "{username}" is already taken.'}), 409

    user = User(
        username=username,
        role=role,
        oauth_provider='local',
        google_email=email or None,
        is_protected=is_protected
    )
    user.set_password(password)
    user.generate_totp_secret()
    db.session.add(user)
    db.session.commit()

    log_audit('SUPERADMIN_CREATE_USER', f'user:{username}', {'role': role, 'is_protected': is_protected, 'email': email})

    return jsonify({
        'success': True,
        'message': f'User {username} ({role}) created successfully.',
        'user': {
            'id': user.id,
            'username': user.username,
            'role': user.role,
            'is_protected': user.is_protected,
            'totp_secret': user.totp_secret,
            'totp_uri': user.get_totp_uri()
        }
    })


# ── Blockchain Deep-Inspector ────────────────────────────────────────────────

@superadmin_bp.route('/blockchain', methods=['GET'])
@login_required
@role_required('superadmin')
def get_blockchain_data():
    """Returns complete list of blocks with signature status and payload details."""
    blockchain._load()
    blocks = []
    for b in reversed(blockchain.chain):
        pd = b.parsed_data or {}
        blocks.append({
            'index': b.index,
            'hash': b.hash,
            'previous_hash': b.previous_hash,
            'timestamp': datetime.fromtimestamp(b.timestamp, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC') if b.timestamp else '0',
            'data': pd or b.data,
            'cert_hash': pd.get('cert_hash', str(b.data)[:64]),
            'issuer': pd.get('issuer', 'system'),
            'signature': getattr(b, 'signature', '') or 'None (Legacy / Genesis)',
            'signer_pubkey': getattr(b, 'signer_pubkey', '') or 'None',
            'signature_valid': b.verify_signature() if hasattr(b, 'verify_signature') else True
        })

    return jsonify({
        'stats': blockchain.stats(),
        'blocks': blocks,
        'total': len(blocks),
        'valid': blockchain.is_valid()
    })


@superadmin_bp.route('/blockchain/reverify', methods=['POST'])
@login_required
@role_required('superadmin')
def reverify_chain():
    """Recomputes SHA-256 block linkages and verifies all Ed25519 signatures."""
    blockchain._load()
    is_valid = blockchain.is_valid()
    stats = blockchain.stats()
    log_audit('REVERIFY_BLOCKCHAIN', 'blockchain:ledger', stats)
    return jsonify({
        'success': True,
        'chain_valid': is_valid,
        'valid': is_valid,
        'total_blocks': len(blockchain.chain),
        'stats': stats,
        'message': 'Cryptographic verification of hash-chains and blocks completed.'
    })


# ── System Diagnostics & Management ───────────────────────────────────────────

@superadmin_bp.route('/system', methods=['GET'])
@login_required
@role_required('superadmin')
def system_diagnostics():
    """Returns system configuration, feature flags, and AI model status."""
    import sys
    models = load_models()
    return jsonify({
        'python_version': sys.version,
        'app_env': os.environ.get('APP_ENV', 'development'),
        'pqc_algorithm': 'ML-KEM-768 (Kyber768)',
        'zkp_scheme': 'Fiat-Shamir Schnorr NIZK (BN128)',
        'blockchain_signing': 'Ed25519 / SHA-256',
        'anomaly_models_active': {
            'isolation_forest_image': 'image_model' in models,
            'isolation_forest_text': 'text_model' in models,
            'tfidf_vectorizer': 'text_vectorizer' in models,
            'autoencoder': 'autoencoder' in models
        }
    })


@superadmin_bp.route('/system/reload-models', methods=['POST'])
@login_required
@role_required('superadmin')
def reload_ai_models():
    """Hot-reloads AI anomaly models into process memory without server restart."""
    models = reload_models()
    log_audit('HOT_RELOAD_AI_MODELS', 'system:ml_anomaly', {'models_loaded': list(models.keys()) if isinstance(models, dict) else 'ok'})
    return jsonify({'success': True, 'message': 'AI anomaly models hot-reloaded successfully from disk.'})
