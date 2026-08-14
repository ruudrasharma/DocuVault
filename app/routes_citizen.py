"""
app/routes_citizen.py — Citizen Authentication & Self-Registration
===================================================================
Blueprint for citizen registration and wallet initialization.
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, flash
from .database import User
from . import db, consent, wallet
import logging

logger = logging.getLogger(__name__)

citizen_bp = Blueprint('citizen', __name__)

@citizen_bp.route('/citizen/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard', role=session.get('role', 'citizen')))
        
    if request.method == 'POST':
        if request.is_json:
            data = request.get_json() or {}
            username = data.get('username', '').strip()
            password = data.get('password', '')
        else:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            
        if not username or not password:
            msg = 'Username and password are required.'
            if request.is_json:
                return jsonify({'error': msg}), 400
            flash(msg, 'error')
            return render_template('citizen_register.html')
            
        if len(password) < 8:
            msg = 'Password must be at least 8 characters long.'
            if request.is_json:
                return jsonify({'error': msg}), 400
            flash(msg, 'error')
            return render_template('citizen_register.html')
            
        if User.query.filter_by(username=username).first():
            msg = f'Username "{username}" is already taken.'
            if request.is_json:
                return jsonify({'error': msg}), 409
            flash(msg, 'error')
            return render_template('citizen_register.html')
            
        # Create citizen user
        user = User(username=username, role='citizen', oauth_provider='local')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        # Provision wallet key with citizen password
        consent.ensure_wallet_key(user, password)
        
        logger.info(f"New citizen registered: {username}")
        
        if request.is_json:
            return jsonify({'success': True, 'username': username})
            
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('citizen_register.html')
