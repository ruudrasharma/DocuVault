"""
app/routes_wallet.py — Citizen Wallet & Consent API Routes
===========================================================
API Blueprint implementing wallet setup, document deposit, sharing, revocation,
decryption/fetching, and immutable audit trail verification.
"""

from flask import Blueprint, request, jsonify, session, Response
from werkzeug.utils import secure_filename
from datetime import datetime, timezone
import logging
import io

from .auth import login_required, role_required
from .database import User, Document, AccessGrant, WalletKey
from . import db, consent, wallet, documents
from .blockchain import blockchain

logger = logging.getLogger(__name__)

wallet_bp = Blueprint('wallet', __name__)

@wallet_bp.route('/wallet/setup', methods=['POST'])
@login_required
@role_required('citizen', 'verifier', 'admin')
def setup_wallet():
    """Provision wallet keypair for citizen if not yet established."""
    try:
        user = db.session.get(User, session['user_id'])
        if not user:
            return jsonify({'error': 'User session invalid.'}), 401
            
        data = request.get_json(silent=True) or {}
        password = data.get('password') or request.form.get('password')
        
        wk = WalletKey.query.filter_by(user_id=user.id).first()
        if not wk:
            if not password:
                return jsonify({'error': 'Password is required for first-time wallet setup.'}), 400
            wk = consent.ensure_wallet_key(user, password)
            
        return jsonify({
            'success': True,
            'public_key': wk.public_key_pem
        })
    except Exception as e:
        logger.error(f"Wallet setup failed: {e}")
        return jsonify({'error': str(e)}), 500


@wallet_bp.route('/wallet/my-documents', methods=['GET'])
@login_required
@role_required('citizen', 'verifier', 'admin')
def my_documents():
    """Return list of metadata for documents owned by current citizen."""
    try:
        user_id = session['user_id']
        docs = Document.query.filter_by(owner_id=user_id).order_by(Document.id.desc()).all()
        
        out = []
        for d in docs:
            out.append({
                'id': d.id,
                'original_filename': d.original_filename,
                'doc_type': d.doc_type or 'Document',
                'issuer_username': d.issuer_username,
                'cert_hash': d.cert_hash,
                'block_index': d.block_index,
                'created_at': d.created_at.strftime('%Y-%m-%d %H:%M UTC') if d.created_at else '—'
            })
            
        return jsonify(out)
    except Exception as e:
        logger.error(f"Error loading my-documents: {e}")
        return jsonify({'error': str(e)}), 500


@wallet_bp.route('/wallet/upload', methods=['POST'])
@login_required
@role_required('institution', 'admin')
def upload_to_wallet():
    """Issuer uploads an opaque document directly to a citizen's wallet."""
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'No file provided.'}), 400
        
    owner_username = request.form.get('owner_username', '').strip()
    doc_type = request.form.get('doc_type', 'Other').strip()
    
    if not owner_username:
        return jsonify({'error': 'owner_username is required.'}), 400
        
    owner_user = User.query.filter_by(username=owner_username).first()
    if not owner_user:
        return jsonify({'error': f'Citizen user "{owner_username}" not found.'}), 404
        
    issuer = session.get('username', 'institution')
    filename = secure_filename(file.filename)
    file_bytes = file.read()
    
    try:
        doc = consent.issue_to_wallet(
            owner_user=owner_user,
            issuer_username=issuer,
            file_bytes=file_bytes,
            filename=filename,
            doc_type=doc_type
        )
        return jsonify({
            'success': True,
            'document_id': doc.id,
            'cert_hash': doc.cert_hash,
            'block_index': doc.block_index
        })
    except Exception as e:
        logger.error(f"Wallet upload failed: {e}")
        return jsonify({'error': str(e)}), 500


@wallet_bp.route('/wallet/share', methods=['POST'])
@login_required
@role_required('citizen', 'verifier', 'admin')
def share_document():
    """Citizen grants temporary access to a grantee agency/verifier."""
    data = request.get_json(silent=True) or {}
    doc_id = data.get('document_id')
    grantee_username = data.get('grantee_username', '').strip()
    expires_at_str = data.get('expires_at')
    if not doc_id or not grantee_username or not expires_at_str:
        return jsonify({'error': 'document_id, grantee_username, and expires_at are required.'}), 400
        
    doc = db.session.get(Document, doc_id)
    if not doc:
        return jsonify({'error': 'Document not found.'}), 404
        
    if doc.owner_id != session['user_id']:
        return jsonify({'error': 'You do not own this document.'}), 403
        
    grantee_user = User.query.filter_by(username=grantee_username).first()
    if not grantee_user:
        return jsonify({'error': f'Grantee user "{grantee_username}" not found.'}), 404
        
    try:
        # Parse ISO datetime
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
    except ValueError:
        return jsonify({'error': 'Invalid date format for expires_at. Use ISO format.'}), 400
        
    owner_user = db.session.get(User, session['user_id'])
    
    try:
        grant = consent.grant_access(
            owner_user=owner_user,
            document=doc,
            grantee_user=grantee_user,
            expires_at=expires_at,
            owner_password=password
        )
        return jsonify({
            'success': True,
            'grant_id': grant.id,
            'block_index': grant.granted_block_index
        })
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 403
    except Exception as e:
        logger.error(f"Sharing document failed: {e}")
        return jsonify({'error': str(e)}), 500


@wallet_bp.route('/wallet/revoke', methods=['POST'])
@login_required
@role_required('citizen', 'verifier', 'admin')
def revoke_grant():
    """Citizen revokes a previously issued access grant."""
    data = request.get_json(silent=True) or {}
    grant_id = data.get('grant_id')
    
    if not grant_id:
        return jsonify({'error': 'grant_id is required.'}), 400
        
    grant = db.session.get(AccessGrant, grant_id)
    if not grant:
        return jsonify({'error': 'Grant not found.'}), 404
        
    owner_user = db.session.get(User, session['user_id'])
    
    try:
        consent.revoke_access(owner_user, grant)
        return jsonify({
            'success': True,
            'block_index': grant.revoked_block_index
        })
    except PermissionError as pe:
        return jsonify({'error': str(pe)}), 403
    except Exception as e:
        logger.error(f"Revoke grant failed: {e}")
        return jsonify({'error': str(e)}), 500


@wallet_bp.route('/wallet/my-grants', methods=['GET'])
@login_required
@role_required('citizen', 'verifier', 'admin')
def my_grants():
    """List all access grants issued by the current citizen with computed status."""
    try:
        user_id = session['user_id']
        requester_user = db.session.get(User, user_id)
        
        # Get grants for documents owned by user
        grants = db.session.query(AccessGrant)\
            .join(Document, AccessGrant.document_id == Document.id)\
            .filter(Document.owner_id == user_id)\
            .order_by(AccessGrant.id.desc()).all()
            
        out = []
        now = datetime.now(timezone.utc)
        for g in grants:
            doc = db.session.get(Document, g.document_id)
            grantee = db.session.get(User, g.grantee_id)
            
            exp_utc = g.expires_at if g.expires_at.tzinfo else g.expires_at.replace(tzinfo=timezone.utc)
            is_active = (not g.revoked) and (exp_utc > now) and consent.check_access(doc, grantee)
            
            status = 'revoked' if g.revoked else ('expired' if exp_utc <= now else 'active')
            
            out.append({
                'grant_id': g.id,
                'document_id': doc.id if doc else None,
                'original_filename': doc.original_filename if doc else 'Unknown',
                'grantee_username': grantee.username if grantee else 'Unknown',
                'expires_at': exp_utc.strftime('%Y-%m-%d %H:%M UTC'),
                'revoked': g.revoked,
                'status': status,
                'is_active': is_active
            })
            
        return jsonify(out)
    except Exception as e:
        logger.error(f"Error loading my-grants: {e}")
        return jsonify({'error': str(e)}), 500


@wallet_bp.route('/wallet/received', methods=['GET'])
@login_required
@role_required('verifier', 'citizen', 'admin')
def received_documents():
    """Verifier/agency lists non-expired, non-revoked documents shared to them."""
    try:
        user_id = session['user_id']
        user = db.session.get(User, user_id)
        
        grants = AccessGrant.query.filter_by(grantee_id=user_id, revoked=False).all()
        now = datetime.now(timezone.utc)
        
        out = []
        for g in grants:
            doc = db.session.get(Document, g.document_id)
            if not doc:
                continue
                
            exp_utc = g.expires_at if g.expires_at.tzinfo else g.expires_at.replace(tzinfo=timezone.utc)
            if exp_utc <= now:
                continue
                
            # Verify against blockchain smart contract logic
            if not consent.check_access(doc, user):
                continue
                
            owner = db.session.get(User, doc.owner_id)
            out.append({
                'grant_id': g.id,
                'document_id': doc.id,
                'original_filename': doc.original_filename,
                'doc_type': doc.doc_type or 'Document',
                'owner_username': owner.username if owner else 'Unknown',
                'issuer_username': doc.issuer_username,
                'expires_at': exp_utc.strftime('%Y-%m-%d %H:%M UTC'),
                'cert_hash': doc.cert_hash,
            })
            
        return jsonify(out)
    except Exception as e:
        logger.error(f"Error loading received documents: {e}")
        return jsonify({'error': str(e)}), 500


@wallet_bp.route('/wallet/fetch/<int:document_id>', methods=['GET', 'POST'])
@login_required
def fetch_document(document_id):
    """
    Fetch and decrypt document binary bytes.
    Accessible to document owner (with password) or grantee (with active consent grant).
    """
    doc = db.session.get(Document, document_id)
    if not doc:
        return jsonify({'error': 'Document not found.'}), 404
        
    current_user = db.session.get(User, session['user_id'])
    
    # Check permission
    has_access = consent.check_access(doc, current_user)
    if not has_access:
        return jsonify({'error': 'Access denied or consent grant expired/revoked.'}), 403
        
    json_data = request.get_json(silent=True) or {}
    password = request.args.get('password') or json_data.get('password') or request.form.get('password')
    
    try:
        if current_user.id == doc.owner_id:
            priv_pem = consent.get_user_private_key(current_user, password)
            dek = wallet.unwrap_dek(doc.wrapped_dek_owner, priv_pem)
        else:
            # Grantee access
            grant = AccessGrant.query.filter_by(document_id=doc.id, grantee_id=current_user.id, revoked=False).first()
            if not grant:
                return jsonify({'error': 'No grant record found for this document.'}), 403
            priv_pem = consent.get_user_private_key(current_user, password)
            dek = wallet.unwrap_dek(grant.wrapped_dek_grantee, priv_pem)
            
        file_bytes = documents.decrypt_blob(doc.encrypted_blob_path, doc.iv, dek)
        
        return Response(
            file_bytes,
            mimetype='application/octet-stream',
            headers={
                'Content-Disposition': f'attachment; filename="{doc.original_filename}"'
            }
        )
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 403
    except Exception as e:
        logger.error(f"Fetch document error: {e}")
        return jsonify({'error': str(e)}), 500


@wallet_bp.route('/wallet/audit/<int:document_id>', methods=['GET'])
@login_required
def audit_trail(document_id):
    """Return immutable on-chain event timeline for a document."""
    doc = db.session.get(Document, document_id)
    if not doc:
        return jsonify({'error': 'Document not found.'}), 404
        
    current_user = db.session.get(User, session['user_id'])
    if current_user.role != 'admin' and current_user.id != doc.owner_id:
        return jsonify({'error': 'Only document owner or admin can view audit trail.'}), 403
        
    try:
        events = blockchain.get_events_for_hash(doc.cert_hash)
        
        formatted = []
        for ev in events:
            ts = ev.get('ts')
            ts_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC') if ts else '—'
            exp_ts = ev.get('expires_at')
            exp_str = datetime.fromtimestamp(exp_ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC') if exp_ts else None
            
            formatted.append({
                'block_index': ev.get('_block_index'),
                'type': ev.get('type'),
                'owner': ev.get('owner'),
                'issuer': ev.get('issuer'),
                'grantee': ev.get('grantee'),
                'timestamp': ts_str,
                'expires_at': exp_str
            })
            
        return jsonify({
            'document_id': doc.id,
            'original_filename': doc.original_filename,
            'cert_hash': doc.cert_hash,
            'events': formatted
        })
    except Exception as e:
        logger.error(f"Audit trail error: {e}")
        return jsonify({'error': str(e)}), 500


@wallet_bp.route('/wallet/prove-claim', methods=['POST'])
@login_required
@role_required('citizen', 'verifier', 'admin')
def prove_claim():
    """
    Generate a zero-knowledge proof token for a document predicate (e.g. proof of degree ownership).
    Returns a ZKP proof token without revealing document blob or DEK.
    """
    data = request.get_json(silent=True) or {}
    doc_id = data.get('document_id')
    
    if not doc_id:
        return jsonify({'error': 'document_id is required.'}), 400
        
    doc = db.session.get(Document, doc_id)
    if not doc or doc.owner_id != session['user_id']:
        return jsonify({'error': 'Document not found or access denied.'}), 404
        
    try:
        from .zkp import generate_zkp_proof, proof_to_hex
        proof = generate_zkp_proof(doc.cert_hash)
        proof_hex = proof_to_hex(proof)
        
        return jsonify({
            'success': True,
            'cert_hash': doc.cert_hash,
            'doc_type': doc.doc_type,
            'issuer_username': doc.issuer_username,
            'proof_hex': proof_hex,
            'claim': f"Citizen holds valid {doc.doc_type or 'document'} issued by {doc.issuer_username}"
        })
    except Exception as e:
        logger.error(f"Prove claim failed: {e}")
        return jsonify({'error': str(e)}), 500


@wallet_bp.route('/wallet/verify-claim', methods=['POST'])
@login_required
def verify_claim():
    """
    Verify a ZKP proof token submitted by a citizen.
    Allows verifier/agency to verify document validity without decrypting blob.
    """
    data = request.get_json(silent=True) or {}
    cert_hash = data.get('cert_hash')
    proof_hex = data.get('proof_hex')
    
    if not cert_hash or not proof_hex:
        return jsonify({'error': 'cert_hash and proof_hex are required.'}), 400
        
    try:
        from .zkp import verify_zkp_hex
        is_valid = verify_zkp_hex(proof_hex, cert_hash)
        on_chain = blockchain.is_valid_hash(cert_hash) or len(blockchain.get_events_for_hash(cert_hash)) > 0
        
        return jsonify({
            'verified': is_valid and on_chain,
            'zkp_valid': is_valid,
            'on_chain': on_chain,
            'cert_hash': cert_hash
        })
    except Exception as e:
        logger.error(f"Verify claim failed: {e}")
        return jsonify({'error': str(e)}), 500
