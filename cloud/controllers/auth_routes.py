"""
Auth Routes
Handles authentication for cloud API.
"""

from flask import Blueprint, request, jsonify, g
from functools import wraps
import jwt
import os
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


def get_tenant_service():
    """Get tenant service from app context."""
    from flask import current_app
    return current_app.config.get('tenant_service')


def create_token(user: dict, secret: str, expires_hours: int = 24) -> str:
    """Create JWT token for user."""
    payload = {
        'user_id': user['id'],
        'tenant_id': user['tenant_id'],
        'email': user['email'],
        'role': user['role'],
        'exp': datetime.utcnow() + timedelta(hours=expires_hours)
    }
    return jwt.encode(payload, secret, algorithm='HS256')


def token_required(f):
    """Decorator for routes that require authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Get token from header
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({'error': 'Token required'}), 401
        
        try:
            from flask import current_app
            secret = current_app.config.get('JWT_SECRET', 'dev-secret')
            payload = jwt.decode(token, secret, algorithms=['HS256'])
            g.user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator for routes that require admin role."""
    @wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        if g.user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated


@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new tenant and admin user."""
    data = request.get_json()
    
    tenant_name = data.get('tenant_name')
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')
    
    if not all([tenant_name, email, password, name]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    tenant_service = get_tenant_service()
    
    # Create tenant
    tenant = tenant_service.create_tenant(tenant_name, email)
    if not tenant:
        return jsonify({'error': 'Tenant with this email already exists'}), 409
    
    # Create admin user
    user = tenant_service.create_user(
        tenant_id=tenant['id'],
        email=email,
        password=password,
        name=name,
        role='admin'
    )
    
    if not user:
        return jsonify({'error': 'Failed to create user'}), 500
    
    # Generate token
    from flask import current_app
    secret = current_app.config.get('JWT_SECRET', 'dev-secret')
    token = create_token(user, secret)
    
    return jsonify({
        'success': True,
        'tenant': tenant,
        'user': user,
        'token': token
    }), 201


@auth_bp.route('/login', methods=['POST'])
def login():
    """Login with email and password."""
    data = request.get_json()
    
    email = data.get('email')
    password = data.get('password')
    
    if not all([email, password]):
        return jsonify({'error': 'Email and password required'}), 400
    
    tenant_service = get_tenant_service()
    user = tenant_service.authenticate_user(email, password)
    
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Generate token
    from flask import current_app
    secret = current_app.config.get('JWT_SECRET', 'dev-secret')
    token = create_token(user, secret)
    
    return jsonify({
        'success': True,
        'user': user,
        'token': token
    })


@auth_bp.route('/me', methods=['GET'])
@token_required
def get_current_user():
    """Get current user info."""
    tenant_service = get_tenant_service()
    user = tenant_service.get_user(g.user['user_id'])
    tenant = tenant_service.get_tenant(g.user['tenant_id'])
    
    return jsonify({
        'user': user,
        'tenant': tenant
    })


@auth_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    """List users in tenant."""
    tenant_service = get_tenant_service()
    users = tenant_service.list_users(g.user['tenant_id'])
    return jsonify({'users': users})


@auth_bp.route('/users', methods=['POST'])
@admin_required
def create_user():
    """Create a new user in tenant."""
    data = request.get_json()
    
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')
    role = data.get('role', 'viewer')
    
    if not all([email, password, name]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    tenant_service = get_tenant_service()
    user = tenant_service.create_user(
        tenant_id=g.user['tenant_id'],
        email=email,
        password=password,
        name=name,
        role=role
    )
    
    if not user:
        return jsonify({'error': 'User with this email already exists'}), 409
    
    return jsonify({'user': user}), 201
