# app/auth.py
import os
os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')  # Allow HTTP behind reverse proxy

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, session, jsonify, current_app)
from .database import User, PendingAccount
from . import db
from functools import wraps
import qrcode
import io
import base64
import uuid
import hashlib
import logging

logger = logging.getLogger(__name__)
auth_bp = Blueprint('auth', __name__)

# Rate limiter — imported lazily so the app still boots without Flask-Limiter
try:
    from . import limiter as _limiter
except ImportError:
    _limiter = None

def _apply_limit(f):
    """
    Conditionally apply rate limits:
    - Superadmin & Admin: ZERO rate limits (completely exempt)
    - Institution & Verifier: High volume capacity (5000/minute)
    - General unauthenticated: 200/minute
    """
    if _limiter:
        def dynamic_rate_limit():
            user_role = session.get('role')
            if user_role in ('admin', 'superadmin'):
                return None  # Exempt from all rate limits
            elif user_role in ('institution', 'verifier'):
                return '5000 per minute'
            return '200 per minute'
        return _limiter.limit(dynamic_rate_limit)(f)
    return f




# ── Decorators ────────────────────────────────────────────────────────────────

import time

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/wallet/') or request.is_json or 'application/json' in request.headers.get('Accept', ''):
                return jsonify({'error': 'Authentication required. Please log in.'}), 401
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    """Enforces role check. Superadmin always has access to all admin/institution/verifier routes."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_role = session.get('role')
            # Superadmin has universal administrative access
            if user_role == 'superadmin' or user_role in roles:
                return f(*args, **kwargs)
            if request.path.startswith('/wallet/') or request.is_json or 'application/json' in request.headers.get('Accept', ''):
                return jsonify({'error': f'Access restricted. Required role: {", ".join(roles)}'}), 403
            flash('Insufficient permissions', 'error')
            return redirect(url_for('auth.login'))
        return decorated
    return decorator


def reverify_2fa(f):
    """
    Step-up 2FA decorator for high-privilege and destructive operations.
    Enforces a 5-minute (300s) sliding security window since last TOTP verification.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required.'}), 401

        last_verified = session.get('sensitive_verified_at', 0)
        now_ts = time.time()

        if now_ts - last_verified > 300:
            if request.is_json or 'application/json' in request.headers.get('Accept', ''):
                return jsonify({
                    'error': 'STEPUP_2FA_REQUIRED',
                    'message': 'This high-privilege action requires fresh 2FA verification.',
                    'stepup_url': url_for('auth.stepup_2fa')
                }), 403
            session['next_sensitive_url'] = request.url
            return redirect(url_for('auth.stepup_2fa'))
        return f(*args, **kwargs)
    return decorated



# ── QR Code helper ────────────────────────────────────────────────────────────

def make_qr_base64(uri):
    """Generate a base64-encoded PNG QR code from a TOTP URI."""
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('utf-8')


# ── Local auth ────────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
@_apply_limit
def login():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard', role=session.get('role', 'verifier')))
    if request.method == 'POST':
        is_ajax = request.is_json or 'application/json' in request.headers.get('Accept', '') or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if request.is_json:
            data = request.get_json() or {}
            username = data.get('username', '').strip()
            password = data.get('password', '').strip()
        else:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()

        logger.info(f'Login attempt: username={username!r}')

        if not username or not password:
            if is_ajax:
                return jsonify({'error': 'Please enter both username and password'}), 400
            flash('Please enter both username and password', 'error')
            return render_template('login.html', show_splash=False)

        # Case-insensitive username or email lookup — no auto-creation
        user = User.query.filter(
            (db.func.lower(User.username) == username.lower()) | 
            (db.func.lower(User.google_email) == username.lower())
        ).first()
        if not user:
            logger.warning(f'Login failed: unknown username/email {username!r}')
            if is_ajax:
                return jsonify({'error': 'Invalid credentials'}), 401
            flash('Invalid credentials', 'error')
            return render_template('login.html', show_splash=False)

        if not user.check_password(password):
            logger.warning(f'Login failed: wrong password for {username!r}')
            if is_ajax:
                return jsonify({'error': 'Invalid credentials'}), 401
            flash('Invalid credentials', 'error')
            return render_template('login.html', show_splash=False)

        session['user_id'] = user.id
        session['role'] = user.role
        session['username'] = user.username
        logger.info(f'Login success: {username!r} role={user.role!r} → verify_2fa')

        if is_ajax:
            return jsonify({'success': True, 'redirect': url_for('auth.verify_2fa')})
        return redirect(url_for('auth.verify_2fa'))
    return render_template('login.html', show_splash=False)



@auth_bp.route('/verify_2fa', methods=['GET', 'POST'])
@_apply_limit
def verify_2fa():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    # Generate TOTP secret if user doesn't have one
    if not user.totp_secret:
        user.generate_totp_secret()
        from . import db as _db
        _db.session.commit()

    if request.method == 'POST':
        token = request.form.get('totp', '').strip()
        if user.verify_totp(token):
            session['verified'] = True
            session['sensitive_verified_at'] = time.time()
            if user.role == 'superadmin':
                return redirect(url_for('superadmin.dashboard'))
            return redirect(url_for('main.dashboard', role=session['role']))
        flash('Invalid or expired OTP code. Try again.', 'error')

    # Always show QR so user can (re-)scan if needed
    qr_b64  = make_qr_base64(user.get_totp_uri())
    totp_uri = user.get_totp_uri()
    return render_template('verify_2fa.html', qr_b64=qr_b64, totp_uri=totp_uri, username=user.username)


@auth_bp.route('/stepup_2fa', methods=['GET', 'POST'])
@login_required
@_apply_limit
def stepup_2fa():
    """Step-up 2FA re-verification before sensitive or destructive actions."""
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        token = request.form.get('totp', '').strip() or request.json.get('totp', '').strip() if request.is_json else ''
        if user.verify_totp(token):
            session['sensitive_verified_at'] = time.time()
            next_url = session.pop('next_sensitive_url', None)
            if request.is_json or 'application/json' in request.headers.get('Accept', ''):
                return jsonify({'success': True, 'message': 'Step-up 2FA verified successfully.'})
            return redirect(next_url or url_for('superadmin.dashboard'))

        if request.is_json or 'application/json' in request.headers.get('Accept', ''):
            return jsonify({'error': 'Invalid 2FA code.'}), 400
        flash('Invalid OTP code. Please try again.', 'error')

    return render_template('verify_2fa.html', qr_b64=make_qr_base64(user.get_totp_uri()), totp_uri=user.get_totp_uri(), username=user.username, is_stepup=True)


@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    if request.is_json or (request.headers.get('Accept') == 'application/json' and request.headers.get('X-Requested-With') == 'XMLHttpRequest'):
        return jsonify({'success': True, 'redirect': '/'})
    return redirect('/')


@auth_bp.route('/get_role')
@login_required
def get_role():
    user = User.query.get(session['user_id'])
    return jsonify({
        'role': session.get('role'),
        'username': session.get('username'),
        'is_protected': getattr(user, 'is_protected', False),
        'oauth_provider': user.oauth_provider if user else 'local',
        'google_name': user.google_name if user else None,
        'google_avatar': user.google_avatar if user else None,
    })


# ── Google OAuth ──────────────────────────────────────────────────────────────

@auth_bp.route('/auth/google')
def google_login():
    from . import google_oauth
    base_url = os.environ.get('APP_BASE_URL', request.host_url.rstrip('/'))
    redirect_uri = base_url + '/auth/google/callback'
    return google_oauth.authorize_redirect(redirect_uri)


@auth_bp.route('/auth/google/callback')
def google_callback():
    from . import google_oauth
    try:
        token = google_oauth.authorize_access_token()
        user_info = token.get('userinfo')
        if not user_info:
            flash('Google sign-in failed. Please try again.', 'error')
            return redirect(url_for('auth.login'))

        google_id = user_info.get('sub')
        email = user_info.get('email', '').strip()
        name = user_info.get('name', email.split('@')[0])
        avatar = user_info.get('picture', '')

        # 1. Match existing user by google_id OR google_email
        user = User.query.filter(
            (User.google_id == google_id) | (db.func.lower(User.google_email) == email.lower())
        ).first()

        if user:
            # Update OAuth fields
            user.google_id = google_id
            user.google_email = email
            user.google_name = name
            user.google_avatar = avatar
            db.session.commit()

            session['user_id'] = user.id
            session['role'] = user.role
            session['username'] = user.username

            # Special-case: Protected accounts / Superadmin MUST complete TOTP 2FA
            if user.is_protected or user.role == 'superadmin':
                logger.info(f"Protected superadmin account {user.username} authenticated via Google SSO -> requesting TOTP")
                return redirect(url_for('auth.verify_2fa'))

            session['verified'] = True
            return redirect(url_for('main.dashboard', role=user.role))

        # 2. If no user found, auto-create standard verifier account
        username = email.split('@')[0].replace('.', '_').replace('-', '_')
        base_username = username
        count = 1
        while User.query.filter_by(username=username).first():
            username = f'{base_username}_{count}'
            count += 1

        user = User(
            username=username,
            password_hash='',
            salt='',
            oauth_provider='google',
            google_id=google_id,
            google_email=email,
            google_name=name,
            google_avatar=avatar,
            role='verifier',
            is_protected=False,
        )
        db.session.add(user)
        db.session.commit()
        logger.info(f'New verifier account created via Google OAuth: {username} ({email})')

        session['user_id'] = user.id
        session['role'] = user.role
        session['username'] = user.username
        session['verified'] = True
        return redirect(url_for('main.dashboard', role=user.role))

    except Exception as e:
        logger.error(f'Google OAuth error: {e}')
        flash('Google sign-in failed. Please try again.', 'error')
        return redirect(url_for('auth.login'))



# ── Admin: Account Management ─────────────────────────────────────────────────

@auth_bp.route('/admin/init-account', methods=['POST'])
@login_required
@role_required('admin')
def admin_init_account():
    """Step 1: Admin submits username+password+role → returns TOTP QR code."""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', '')

    if not username or not password or role not in ('admin', 'institution', 'citizen'):
        return jsonify({'error': 'Invalid input. Role must be admin, institution, or citizen.'}), 400
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters.'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'error': f'Username "{username}" is already taken.'}), 409

    # Delete any old pending entry for same username
    PendingAccount.query.filter_by(username=username).delete()

    import pyotp
    salt = uuid.uuid4().hex
    pw_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    totp_secret = pyotp.random_base32()

    pending = PendingAccount(
        id=str(uuid.uuid4()),
        username=username,
        password_hash=pw_hash,
        salt=salt,
        role=role,
        totp_secret=totp_secret,
        created_by=session['user_id'],
    )
    db.session.add(pending)
    db.session.commit()

    # Build TOTP URI + QR
    totp_uri = pyotp.TOTP(totp_secret).provisioning_uri(
        name=username, issuer_name='DocuVault'
    )
    qr_b64 = make_qr_base64(totp_uri)

    return jsonify({
        'pending_id': pending.id,
        'totp_secret': totp_secret,
        'totp_uri': totp_uri,
        'qr_code': qr_b64,
    })


@auth_bp.route('/admin/confirm-account', methods=['POST'])
@login_required
@role_required('admin')
def admin_confirm_account():
    """Step 2: Verify OTP entered by the new user → create the account."""
    data = request.get_json()
    pending_id = data.get('pending_id')
    otp = data.get('otp', '').strip()

    pending = PendingAccount.query.get(pending_id)
    if not pending:
        return jsonify({'error': 'Session expired. Please start again.'}), 404
    if pending.is_expired():
        db.session.delete(pending)
        db.session.commit()
        return jsonify({'error': 'This setup session expired (1 hour limit). Start again.'}), 410

    if not pending.verify_otp(otp):
        return jsonify({'error': 'Wrong OTP code. Ask the person to check their authenticator app.'}), 400

    # OTP correct → create the real user
    if User.query.filter_by(username=pending.username).first():
        return jsonify({'error': 'Username already exists (race condition). Try again.'}), 409

    user = User(
        username=pending.username,
        password_hash=pending.password_hash,
        salt=pending.salt,
        role=pending.role,
        totp_secret=pending.totp_secret,
        oauth_provider='local',
    )
    db.session.add(user)
    db.session.delete(pending)
    db.session.commit()

    logger.info(f'Account created by admin {session["username"]}: {user.username} ({user.role})')
    return jsonify({'success': True, 'username': user.username, 'role': user.role})


@auth_bp.route('/admin/regenerate-secret', methods=['POST'])
@login_required
@role_required('admin')
def admin_regenerate_secret():
    """Regenerate TOTP secret for a pending account (if user can't scan)."""
    data = request.get_json()
    pending_id = data.get('pending_id')
    pending = PendingAccount.query.get(pending_id)
    if not pending:
        return jsonify({'error': 'Session not found. Start over.'}), 404

    import pyotp
    pending.totp_secret = pyotp.random_base32()
    db.session.commit()

    totp_uri = pyotp.TOTP(pending.totp_secret).provisioning_uri(
        name=pending.username, issuer_name='DocuVault'
    )
    qr_b64 = make_qr_base64(totp_uri)
    return jsonify({
        'totp_secret': pending.totp_secret,
        'qr_code': qr_b64,
    })


@auth_bp.route('/admin/users', methods=['GET'])
@login_required
@role_required('admin')
def admin_users():
    # Ordinary admins never see superadmin or protected system accounts
    users = User.query.filter(
        User.role != 'student',
        User.role != 'superadmin'
    ).order_by(User.role, User.username).all()

    filtered = [
        u for u in users
        if not getattr(u, 'is_protected', False) and u.role != 'superadmin'
    ]

    return jsonify([{
        'id': u.id,
        'username': u.username,
        'role': u.role,
        'provider': u.oauth_provider,
        'email': u.google_email,
        'name': u.google_name,
        'is_protected': getattr(u, 'is_protected', False),
    } for u in filtered])



@auth_bp.route('/admin/direct-create-user', methods=['POST'])
@login_required
@role_required('admin')
def admin_direct_create_user():
    """Admin directly provisions an account with username, password, and role."""
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'verifier')
    email = data.get('email', '').strip()

    if not username or not password:
        return jsonify({'error': 'Username and password are required.'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters.'}), 400
    if role not in ('admin', 'institution', 'verifier', 'citizen'):
        return jsonify({'error': 'Invalid role. Choose admin, institution, verifier, or citizen.'}), 400

    if User.query.filter((db.func.lower(User.username) == username.lower())).first():
        return jsonify({'error': f'Username "{username}" is already taken.'}), 409

    user = User(
        username=username,
        role=role,
        oauth_provider='local',
        google_email=email or None,
        is_protected=False
    )
    user.set_password(password)
    user.generate_totp_secret()
    db.session.add(user)

    from .database import AuditLog
    audit = AuditLog(
        actor_id=session.get('user_id'),
        actor_username=session.get('username', 'admin'),
        action='CREATE_USER',
        target=f'user:{username}',
        ip_address=request.remote_addr,
        details_json=f'{{"username": "{username}", "role": "{role}"}}'
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'User {username} ({role}) created successfully.',
        'user': {
            'id': user.id,
            'username': user.username,
            'role': user.role,
            'totp_secret': user.totp_secret,
            'totp_uri': user.get_totp_uri()
        }
    })


@auth_bp.route('/admin/reset-password/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_reset_password(user_id):
    """Admin resets password for any non-protected user account."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found.'}), 404

    if getattr(user, 'is_protected', False) or user.role == 'superadmin':
        return jsonify({'error': 'Protected accounts cannot be modified.'}), 403

    data = request.get_json() or {}
    new_password = data.get('new_password', '')
    if not new_password or len(new_password) < 6:
        return jsonify({'error': 'New password must be at least 6 characters.'}), 400

    user.set_password(new_password)
    from .database import AuditLog
    audit = AuditLog(
        actor_id=session.get('user_id'),
        actor_username=session.get('username', 'admin'),
        action='RESET_USER_PASSWORD',
        target=f'user:{user.id}:{user.username}',
        ip_address=request.remote_addr,
        details_json=f'{{"username": "{user.username}"}}'
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify({'success': True, 'message': f'Password for {user.username} has been reset successfully.'})


@auth_bp.route('/admin/delete-user/<int:user_id>', methods=['POST', 'DELETE'])
@login_required
@role_required('admin')
def admin_delete_user(user_id):
    if user_id == session['user_id']:
        return jsonify({'error': 'Cannot delete your own account.'}), 400
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found.'}), 404

    # Strict server-side route-level enforcement: protected accounts can NEVER be deleted
    if getattr(user, 'is_protected', False) or user.role == 'superadmin':
        logger.warning(f"BLOCKED: Attempt to delete protected account '{user.username}' by {session.get('username')}")
        return jsonify({'error': 'Protected system account cannot be modified or deleted.'}), 403

    from .database import AuditLog
    audit = AuditLog(
        actor_id=session.get('user_id'),
        actor_username=session.get('username', 'admin'),
        action='DELETE_USER',
        target=f'user:{user.id}:{user.username}',
        ip_address=request.remote_addr,
        details_json=f'{{"deleted_username": "{user.username}", "role": "{user.role}"}}'
    )
    db.session.add(audit)
    db.session.delete(user)
    db.session.commit()
    logger.info(f"User '{user.username}' deleted by {session.get('username')}")
    return jsonify({'success': True, 'message': f"User '{user.username}' deleted."})