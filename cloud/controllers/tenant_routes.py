"""
Tenant Routes
Manages tenant settings and edge devices.
"""

from flask import Blueprint, request, jsonify, g
from .auth_routes import token_required, admin_required

tenant_bp = Blueprint('tenant', __name__, url_prefix='/api/tenant')

# Module-level service reference
_tenant_service = None


def set_tenant_service(service):
    """Set the tenant service instance."""
    global _tenant_service
    _tenant_service = service


def get_tenant_service():
    """Get tenant service from app context."""
    from flask import current_app
    return current_app.config.get('tenant_service')


@tenant_bp.route('/', methods=['GET'])
@token_required
def get_tenant():
    """Get current tenant details."""
    tenant_service = get_tenant_service()
    tenant = tenant_service.get_tenant(g.user['tenant_id'])
    
    if not tenant:
        return jsonify({'error': 'Tenant not found'}), 404
    
    return jsonify({'tenant': tenant})


@tenant_bp.route('/', methods=['PUT'])
@admin_required
def update_tenant():
    """Update tenant details."""
    data = request.get_json()
    
    tenant_service = get_tenant_service()
    success = tenant_service.update_tenant(g.user['tenant_id'], data)
    
    if not success:
        return jsonify({'error': 'Failed to update tenant'}), 400
    
    tenant = tenant_service.get_tenant(g.user['tenant_id'])
    return jsonify({'tenant': tenant})


# ==========================================
# Edge Device Management
# ==========================================

@tenant_bp.route('/edges', methods=['GET'])
@token_required
def list_edges():
    """List edge devices for tenant."""
    tenant_service = get_tenant_service()
    edges = tenant_service.list_edge_devices(g.user['tenant_id'])
    
    # Add online status from edge manager
    from flask import current_app
    edge_manager = current_app.config.get('edge_manager')
    
    if edge_manager:
        for edge in edges:
            edge['online'] = edge_manager.is_edge_connected(edge['id'])
    
    return jsonify({'edges': edges})


@tenant_bp.route('/edges', methods=['POST'])
@admin_required
def register_edge():
    """Register a new edge device."""
    data = request.get_json()
    
    name = data.get('name')
    location = data.get('location')
    
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    
    tenant_service = get_tenant_service()
    
    # Check edge limit
    tenant = tenant_service.get_tenant(g.user['tenant_id'])
    current_edges = tenant_service.list_edge_devices(g.user['tenant_id'])
    
    if len(current_edges) >= tenant.get('max_edges', 5):
        return jsonify({'error': 'Edge device limit reached'}), 403
    
    edge = tenant_service.register_edge_device(
        tenant_id=g.user['tenant_id'],
        name=name,
        location=location
    )
    
    if not edge:
        return jsonify({'error': 'Failed to register edge device'}), 500
    
    return jsonify({
        'edge': edge,
        'message': 'Save the edge_secret - it will not be shown again!'
    }), 201


@tenant_bp.route('/edges/<edge_id>', methods=['GET'])
@token_required
def get_edge(edge_id):
    """Get edge device details."""
    tenant_service = get_tenant_service()
    edges = tenant_service.list_edge_devices(g.user['tenant_id'])
    
    edge = next((e for e in edges if e['id'] == edge_id), None)
    if not edge:
        return jsonify({'error': 'Edge not found'}), 404
    
    # Add online status
    from flask import current_app
    edge_manager = current_app.config.get('edge_manager')
    if edge_manager:
        edge['online'] = edge_manager.is_edge_connected(edge_id)
    
    return jsonify({'edge': edge})


@tenant_bp.route('/edges/<edge_id>', methods=['PUT'])
@admin_required
def update_edge(edge_id):
    """Update edge device."""
    data = request.get_json()
    
    tenant_service = get_tenant_service()
    
    # Verify ownership
    edges = tenant_service.list_edge_devices(g.user['tenant_id'])
    edge = next((e for e in edges if e['id'] == edge_id), None)
    if not edge:
        return jsonify({'error': 'Edge not found'}), 404
    
    success = tenant_service.update_edge_device(edge_id, data)
    
    if not success:
        return jsonify({'error': 'Failed to update edge device'}), 400
    
    return jsonify({'success': True})


@tenant_bp.route('/edges/<edge_id>', methods=['DELETE'])
@admin_required
def delete_edge(edge_id):
    """Deactivate edge device."""
    tenant_service = get_tenant_service()
    
    # Verify ownership
    edges = tenant_service.list_edge_devices(g.user['tenant_id'])
    edge = next((e for e in edges if e['id'] == edge_id), None)
    if not edge:
        return jsonify({'error': 'Edge not found'}), 404
    
    success = tenant_service.update_edge_device(edge_id, {'is_active': False})
    
    return jsonify({'success': success})


@tenant_bp.route('/edges/<edge_id>/regenerate-secret', methods=['POST'])
@admin_required
def regenerate_edge_secret(edge_id):
    """Regenerate edge device secret."""
    tenant_service = get_tenant_service()
    
    # Verify ownership
    edges = tenant_service.list_edge_devices(g.user['tenant_id'])
    edge = next((e for e in edges if e['id'] == edge_id), None)
    if not edge:
        return jsonify({'error': 'Edge not found'}), 404
    
    new_secret = tenant_service.regenerate_edge_secret(edge_id)
    
    if not new_secret:
        return jsonify({'error': 'Failed to regenerate secret'}), 500
    
    return jsonify({
        'edge_id': edge_id,
        'edge_secret': new_secret,
        'message': 'Save the new edge_secret - it will not be shown again!'
    })


@tenant_bp.route('/edges/<edge_id>/command', methods=['POST'])
@admin_required
def send_edge_command(edge_id):
    """Send command to edge device."""
    data = request.get_json()
    
    command = data.get('command')
    payload = data.get('payload', {})
    
    if not command:
        return jsonify({'error': 'Command is required'}), 400
    
    tenant_service = get_tenant_service()
    
    # Verify ownership
    edges = tenant_service.list_edge_devices(g.user['tenant_id'])
    edge = next((e for e in edges if e['id'] == edge_id), None)
    if not edge:
        return jsonify({'error': 'Edge not found'}), 404
    
    # Send command via edge manager
    from flask import current_app
    edge_manager = current_app.config.get('edge_manager')
    
    if not edge_manager:
        return jsonify({'error': 'Edge manager not available'}), 500
    
    if not edge_manager.is_edge_connected(edge_id):
        return jsonify({'error': 'Edge is offline'}), 503
    
    success = edge_manager.send_command(edge_id, command, payload)
    
    return jsonify({'success': success})
