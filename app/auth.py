from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from .database import User
from . import db
from functools import wraps

auth_bp = Blueprint('auth', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_role = session.get('role')
            if user_role not in roles:
                flash('Insufficient permissions')
                return redirect(url_for('auth.login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['role'] = user.role
            return redirect(url_for('auth.verify_2fa'))
        flash('Invalid credentials')
    return render_template('login.html')

@auth_bp.route('/verify_2fa', methods=['GET', 'POST'])
def verify_2fa():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        token = request.form['totp']
        user = User.query.get(session['user_id'])
        if user.verify_totp(token):
            return redirect(url_for('main.dashboard', role=session['role']))
        flash('Invalid TOTP')
    return render_template('verify_2fa.html')

@auth_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@auth_bp.route('/get_role', methods=['GET'])
@login_required
def get_role():
    return jsonify({'role': session.get('role')})

@auth_bp.route('/admin/add_user', methods=['POST'])
@login_required
@role_required('admin')
def add_user():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')
    if role not in {'admin', 'institution', 'verifier'}:
        return jsonify({'error': 'Invalid role'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'User already exists'}), 400
    user = User(username=username, role=role)
    user.set_password(password)
    totp_secret = user.generate_totp_secret()
    db.session.add(user)
    db.session.commit()
    return jsonify({'secret': totp_secret})

@auth_bp.route('/admin/recover_2fa', methods=['POST'])
@login_required
@role_required('admin')
def recover_2fa():
    data = request.json
    user_id = data.get('user_id')
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    totp_secret = user.generate_totp_secret()
    db.session.commit()
    return jsonify({'new_secret': totp_secret})