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


# ── Decorators ────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or not session.get('verified', False):
            if '2fa_pending_user_id' in session:
                if request.path.startswith('/wallet/') or request.is_json or 'application/json' in request.headers.get('Accept', ''):
                    return jsonify({'error': 'Two-factor authentication required. Please complete 2FA.', 'redirect': url_for('auth.verify_2fa')}), 401
                return redirect(url_for('auth.verify_2fa'))
            if request.path.startswith('/wallet/') or request.is_json or 'application/json' in request.headers.get('Accept', ''):
                return jsonify({'error': 'Authentication required. Please log in.'}), 401
            return redirect(url_for('auth.login', splash='1'))
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_role = session.get('role')
            # Superadmin has full access to admin-level routes as well
            allowed = (user_role in roles) or (user_role == 'superadmin' and 'admin' in roles)
            if not allowed:
                if request.path.startswith('/wallet/') or request.is_json or 'application/json' in request.headers.get('Accept', ''):
                    return jsonify({'error': f'Access restricted. Required role: {", ".join(roles)}'}), 403
                flash('Insufficient permissions', 'error')
                return redirect(url_for('auth.login', splash='1'))
            return f(*args, **kwargs)
        return decorated
    return decorator



# ── QR Code helper ────────────────────────────────────────────────────────────

def make_qr_base64(uri):
    """Generate a base64-encoded PNG QR code from a TOTP URI."""
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode('utf-8')


# ── Local auth ────────────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session and session.get('verified'):
        return redirect(url_for('main.dashboard', role=session.get('role', 'verifier')))

    # Show splash screen on first visit, root landing, or post-logout
    show_splash = request.args.get('splash') == '1' or request.args.get('logout') == '1' or (request.method == 'GET' and 'splash' not in request.args)

    if request.method == 'POST':
        # Support both AJAX JSON body and normal form POST
        is_ajax = request.is_json or request.headers.get('Accept') == 'application/json'
        if request.is_json:
            data     = request.get_json(silent=True) or {}
            username = data.get('username', '').strip()
            password = data.get('password', '').strip()
        else:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()

        logger.info(f'Login attempt: username={username!r} ajax={is_ajax}')

        if not username or not password:
            if is_ajax:
                return jsonify({'error': 'Please enter both username and password'}), 400
            flash('Please enter both username and password', 'error')
            return render_template('login.html', show_splash=False)

        # Strict case-insensitive username lookup — no auto-creation
        user = User.query.filter(db.func.lower(User.username) == username.lower()).first()
        if not user or not user.check_password(password):
            logger.warning(f'Login failed: invalid credentials for {username!r}')
            if is_ajax:
                return jsonify({'error': 'Invalid credentials — incorrect username or password'}), 401
            flash('Invalid credentials — incorrect username or password', 'error')
            return render_template('login.html', show_splash=False)

        # ── Password verified → Set 2FA pending state (DO NOT grant access yet) ──
        session.clear()
        session['2fa_pending_user_id']  = user.id
        session['2fa_pending_role']     = user.role
        session['2fa_pending_username'] = user.username
        logger.info(f'Password verified: {username!r} → redirecting to 2FA challenge')
        if is_ajax:
            return jsonify({'success': True, 'redirect': url_for('auth.verify_2fa')})
        return redirect(url_for('auth.verify_2fa'))

    return render_template('login.html', show_splash=show_splash)


@auth_bp.route('/verify_2fa', methods=['GET', 'POST'])
def verify_2fa():
    # If already fully authenticated, go straight to dashboard
    if 'user_id' in session and session.get('verified'):
        return redirect(url_for('main.dashboard', role=session.get('role', 'verifier')))

    pending_id = session.get('2fa_pending_user_id')
    if not pending_id:
        return redirect(url_for('auth.login', splash='1'))

    user = User.query.get(pending_id)
    if not user:
        session.clear()
        return redirect(url_for('auth.login', splash='1'))

    # Generate TOTP secret if user doesn't have one
    if not user.totp_secret:
        user.generate_totp_secret()
        from . import db as _db
        _db.session.commit()

    if request.method == 'POST':
        token = request.form.get('totp', '').strip()
        if user.verify_totp(token):
            session.clear()
            session['user_id']  = user.id
            session['role']     = user.role
            session['username'] = user.username
            session['verified'] = True
            logger.info(f'2FA verified successfully for user {user.username} (role={user.role})')
            return redirect(url_for('main.dashboard', role=user.role))
        flash('Invalid or expired OTP code. Try again.', 'error')

    return render_template('verify_2fa.html', username=user.username)




@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    if request.method == 'POST' and (request.is_json or request.headers.get('Accept') == 'application/json'):
        return jsonify({'success': True, 'redirect': url_for('auth.login', splash='1')})
    return redirect(url_for('auth.login', splash='1'))


@auth_bp.route('/get_role')
@login_required
def get_role():
    user = User.query.get(session['user_id'])
    return jsonify({
        'role': session.get('role'),
        'username': session.get('username'),
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
        email = user_info.get('email', '')
        name = user_info.get('name', email.split('@')[0])
        avatar = user_info.get('picture', '')

        SUPERADMIN_EMAILS = {'rudraksharma187@gmail.com'}
        norm_email = email.strip().lower()
        target_role = 'superadmin' if norm_email in SUPERADMIN_EMAILS else 'verifier'

        # Find existing user by google_id or google_email
        user = User.query.filter((User.google_id == google_id) | (db.func.lower(User.google_email) == norm_email)).first()

        if not user:
            # Check if email already exists as local user
            user = User.query.filter(db.func.lower(User.google_email) == norm_email).first()
            if user and user.oauth_provider == 'local':
                flash('This email is linked to a local account. Please sign in with username & password.', 'error')
                return redirect(url_for('auth.login'))

            # Auto-create account with appropriate role
            username = email.split('@')[0].replace('.', '_').replace('-', '_')
            base_username = username
            count = 1
            while User.query.filter_by(username=username).first():
                username = f'{base_username}_{count}'
                count += 1

            user = User(
                username=username,
                password_hash='',   # No password for OAuth users
                salt='',            # No salt for OAuth users
                oauth_provider='google',
                google_id=google_id,
                google_email=email,
                google_name=name,
                google_avatar=avatar,
                role=target_role,
            )
            db.session.add(user)
            db.session.commit()
            logger.info(f'New {target_role} account created via Google OAuth: {username} ({email})')
        else:
            # Update profile info and ensure superadmin role if email matches
            user.google_name = name
            user.google_avatar = avatar
            if not user.google_id:
                user.google_id = google_id
            if not user.google_email:
                user.google_email = email
            if norm_email in SUPERADMIN_EMAILS:
                user.role = 'superadmin'
            db.session.commit()

        session['user_id'] = user.id
        session['role'] = user.role
        session['username'] = user.username
        session['verified'] = True  # Google auth = no 2FA needed
        logger.info(f'Google OAuth sign-in success: {user.username} ({email}) with role={user.role}')
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
    users = User.query.filter(User.role != 'student').order_by(User.role, User.username).all()
    return jsonify([{
        'id': u.id,
        'username': u.username,
        'role': u.role,
        'provider': u.oauth_provider,
        'email': u.google_email,
        'name': u.google_name,
    } for u in users])
