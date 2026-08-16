"""
app/consent.py — Smart-Contract Consent & Access Control Logic
===============================================================
Enforces owner consent, time-based expiration, access grants, revokations,
and chain-backed access control evaluation.
"""

from datetime import datetime, timezone
import logging
from . import db
from .database import User, Document, AccessGrant, WalletKey
from .blockchain import blockchain
from . import wallet
from . import documents

logger = logging.getLogger(__name__)

def ensure_wallet_key(user: User, password: str | None = None) -> WalletKey:
    """
    Ensure a WalletKey exists for the user.
    If not, generate keypair and encrypt private key with provided password.
    Raises ValueError if no password is supplied for a new key.
    """
    wk = WalletKey.query.filter_by(user_id=user.id).first()
    if wk:
        return wk

    if not password:
        raise ValueError(
            "Cannot create a wallet key without a password. "
            "Please supply the user's wallet password."
        )

    pub_pem, priv_pem = wallet.generate_keypair()
    enc_priv, salt_hex = wallet.encrypt_private_key(priv_pem, password)

    wk = WalletKey(
        user_id=user.id,
        public_key_pem=pub_pem,
        encrypted_private_key=enc_priv,
        kdf_salt=salt_hex
    )
    db.session.add(wk)
    db.session.commit()
    logger.info(f"Provisioned WalletKey for user {user.username}")
    return wk

def issue_to_wallet(owner_user: User, issuer_username: str, file_bytes: bytes, filename: str, doc_type: str) -> Document:
    """
    Issue a new document directly into a citizen's wallet.
    Encrypts document at rest, adds wallet_issue block on chain, and creates Document DB record.
    """
    wk = ensure_wallet_key(owner_user)
    
    enc_res = documents.encrypt_and_store(file_bytes, wk.public_key_pem)
    cert_hash = enc_res['cert_hash']
    
    block_index = blockchain.add_wallet_issue_block(cert_hash, owner_user.username, issuer_username)
    
    doc = Document(
        owner_id=owner_user.id,
        issuer_username=issuer_username,
        original_filename=filename,
        doc_type=doc_type,
        encrypted_blob_path=enc_res['blob_path'],
        iv=enc_res['iv_hex'],
        wrapped_dek_owner=enc_res['wrapped_dek_owner'],
        cert_hash=cert_hash,
        block_index=block_index,
    )
    db.session.add(doc)
    db.session.commit()
    logger.info(f"Issued document {doc.id} ({doc.original_filename}) to {owner_user.username} by {issuer_username}")
    return doc

def get_user_private_key(user: User, password: str | None = None) -> str:
    """
    Retrieve and decrypt user's RSA private key using the supplied password.
    Raises ValueError if the password is wrong or the wallet key doesn't exist.
    """
    wk = WalletKey.query.filter_by(user_id=user.id).first()
    if not wk:
        raise ValueError(
            f"No wallet key found for user '{user.username}'. "
            "Ask them to set up their wallet first."
        )

    if not password or not password.strip():
        raise ValueError(
            "Wallet password is required to access the private key."
        )

    try:
        return wallet.decrypt_private_key(wk.encrypted_private_key, wk.kdf_salt, password.strip())
    except ValueError:
        raise ValueError(
            "Incorrect wallet password — could not decrypt private key."
        )


def grant_access(owner_user: User, document: Document, grantee_user: User, expires_at: datetime, owner_password: str | None = None) -> AccessGrant:
    """
    Grant access to a document to a grantee (agency/verifier).
    Enforces owner identity, expiration time, decrypts DEK with owner's key, and wraps it for grantee.
    Records 'grant' block on chain.
    """
    if document.owner_id != owner_user.id:
        raise PermissionError("Only the document owner can grant access.")
        
    now = datetime.now(timezone.utc)
    exp_utc = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
    if exp_utc <= now:
        raise ValueError("Expiration date must be in the future.")

    # Decrypt owner's private key (using fallback helper for Google SSO / local accounts)
    owner_priv_pem = get_user_private_key(owner_user, owner_password)
    
    # Unwrap DEK
    dek = wallet.unwrap_dek(document.wrapped_dek_owner, owner_priv_pem)
    
    # Ensure grantee has wallet key & wrap DEK for grantee
    grantee_wk = ensure_wallet_key(grantee_user)
    wrapped_dek_grantee = wallet.wrap_dek(dek, grantee_wk.public_key_pem)
    
    # Add grant block to chain
    block_index = blockchain.add_grant_block(
        cert_hash=document.cert_hash,
        owner_username=owner_user.username,
        grantee_username=grantee_user.username,
        expires_at_ts=exp_utc.timestamp()
    )
    
    # Persist AccessGrant row
    grant = AccessGrant(
        document_id=document.id,
        grantee_id=grantee_user.id,
        wrapped_dek_grantee=wrapped_dek_grantee,
        granted_by=owner_user.id,
        granted_block_index=block_index,
        expires_at=exp_utc,
        revoked=False
    )
    db.session.add(grant)
    db.session.commit()
    
    # Explicitly clear dek/priv_key references
    del dek, owner_priv_pem
    
    logger.info(f"Granted access for doc {document.id} to {grantee_user.username} until {exp_utc}")
    return grant

def revoke_access(owner_user: User, grant: AccessGrant) -> None:
    """
    Revoke a previously granted access.
    Records 'revoke' block on chain and sets revoked flag in DB.
    """
    doc = db.session.get(Document, grant.document_id)
    if not doc or doc.owner_id != owner_user.id:
        raise PermissionError("Only the document owner can revoke grants for this document.")
        
    grantee_user = db.session.get(User, grant.grantee_id)
    grantee_username = grantee_user.username if grantee_user else "unknown"
    
    block_index = blockchain.add_revoke_block(
        cert_hash=doc.cert_hash,
        owner_username=owner_user.username,
        grantee_username=grantee_username
    )
    
    grant.revoked = True
    grant.revoked_block_index = block_index
    db.session.commit()
    logger.info(f"Revoked grant {grant.id} for doc {doc.id} on block #{block_index}")

def check_access(document: Document, requester_user: User) -> bool:
    """
    Evaluates access right based on the blockchain event stream for document.cert_hash.
    Chain is the source of truth.
    - Owner always has access.
    - Otherwise, find all events for (cert_hash) and find latest event for requester.
    """
    if requester_user.id == document.owner_id:
        return True
        
    events = blockchain.get_events_for_hash(document.cert_hash)
    requester_events = [e for e in events if e.get("grantee") == requester_user.username]
    
    if not requester_events:
        return False
        
    latest_event = requester_events[-1]
    if latest_event.get("type") != "grant":
        return False
        
    expires_at_ts = latest_event.get("expires_at", 0)
    now_ts = datetime.now(timezone.utc).timestamp()
    if now_ts > expires_at_ts:
        return False
        
    return True
