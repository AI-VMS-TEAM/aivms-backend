"""
Authentication routes for login/logout and session management
"""

from flask import Blueprint, request, jsonify, session, redirect, url_for
from models.user import User
import logging
from datetime import datetime
import sqlite3

logger = logging.getLogger(__name__)

# Blueprint for authentication routes
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

# Global reference to database path (set by app.py)
_db_path = None


def set_db_path(db_path: str):
    """Set the database path (called from app.py)"""
    global _db_path
    _db_path = db_path


def log_audit(user_id: int, username: str, action: str, details: str = None, 
              ip_address: str = None, user_agent: str = None):
    """Log user action to audit_logs table"""
    try:
        conn = sqlite3.connect(_db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO audit_logs (user_id, username, action, details, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, username, action, details, ip_address, user_agent))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error logging audit: {e}")


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Login endpoint
    
    Request body:
        {
            "username": "admin",
            "password": "admin123"
        }
    
    Returns:
        {
            "success": true,
            "user": {
                "id": 1,
                "username": "admin",
                "role": "admin",
                "must_change_password": false
            }
        }
    """
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        # Verify credentials
        user = User.verify_password(_db_path, username, password)
        
        if not user:
            # Log failed login attempt
            log_audit(
                user_id=None,
                username=username,
                action='login_failed',
                details='Invalid credentials',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            return jsonify({'error': 'Invalid username or password'}), 401
        
        # Check if user is active
        if not user.is_active:
            log_audit(
                user_id=user.id,
                username=username,
                action='login_failed',
                details='Account is inactive',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
            return jsonify({'error': 'Account is inactive'}), 403
        
        # Create session
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role
        session['must_change_password'] = user.must_change_password
        session.permanent = True  # Use permanent session (configurable timeout)
        
        # Update last login
        User.update_last_login(_db_path, user.id)
        
        # Log successful login
        log_audit(
            user_id=user.id,
            username=username,
            action='login_success',
            details='User logged in successfully',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        logger.info(f"✅ User '{username}' logged in successfully")
        
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'full_name': user.full_name,
                'email': user.email,
                'role': user.role,
                'must_change_password': user.must_change_password
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Logout endpoint - clear session"""
    try:
        user_id = session.get('user_id')
        username = session.get('username')

        if user_id and username:
            # Log logout
            log_audit(
                user_id=user_id,
                username=username,
                action='logout',
                details='User logged out',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )

        # Clear session
        session.clear()

        logger.info(f"✅ User '{username}' logged out")

        return jsonify({'success': True}), 200

    except Exception as e:
        logger.error(f"Logout error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/check', methods=['GET'])
def check_session():
    """
    Check if user is logged in

    Returns:
        {
            "authenticated": true,
            "user": {
                "id": 1,
                "username": "admin",
                "role": "admin"
            }
        }
    """
    try:
        user_id = session.get('user_id')

        if not user_id:
            return jsonify({'authenticated': False}), 200

        # Get user from database
        user = User.get_by_id(_db_path, user_id)

        if not user or not user.is_active:
            # Session exists but user is invalid/inactive
            session.clear()
            return jsonify({'authenticated': False}), 200

        return jsonify({
            'authenticated': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'full_name': user.full_name,
                'email': user.email,
                'role': user.role,
                'must_change_password': user.must_change_password
            }
        }), 200

    except Exception as e:
        logger.error(f"Session check error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

