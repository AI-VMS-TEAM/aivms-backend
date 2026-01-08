"""
Edge Routes
REST API endpoints for edge device communication.
(Alternative to WebSocket for simple commands/queries)
"""

from flask import Blueprint, request, jsonify
from datetime import datetime

edge_bp = Blueprint('edge', __name__, url_prefix='/api/edge')

# Module-level service reference
_edge_manager = None


def set_edge_manager(manager):
    """Set the edge manager instance."""
    global _edge_manager
    _edge_manager = manager


def get_tenant_service():
    """Get tenant service from app context."""
    from flask import current_app
    return current_app.config.get('tenant_service')


def get_event_service():
    """Get event service from app context."""
    from flask import current_app
    return current_app.config.get('event_service')


def get_edge_manager():
    """Get edge manager from app context."""
    from flask import current_app
    return current_app.config.get('edge_manager')


def verify_edge_auth():
    """Verify edge device authentication from headers."""
    edge_id = request.headers.get('X-Edge-ID')
    edge_secret = request.headers.get('X-Edge-Secret')
    
    if not edge_id or not edge_secret:
        return None
    
    tenant_service = get_tenant_service()
    return tenant_service.verify_edge_device(edge_id, edge_secret)


# ==========================================
# Edge Authentication
# ==========================================

@edge_bp.route('/authenticate', methods=['POST'])
def authenticate():
    """Authenticate edge device and get connection info."""
    data = request.get_json()
    
    edge_id = data.get('edge_id')
    edge_secret = data.get('edge_secret')
    
    if not edge_id or not edge_secret:
        return jsonify({'error': 'edge_id and edge_secret required'}), 400
    
    tenant_service = get_tenant_service()
    edge = tenant_service.verify_edge_device(edge_id, edge_secret)
    
    if not edge:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    return jsonify({
        'success': True,
        'edge': edge,
        'websocket_url': '/edge',  # WebSocket namespace for real-time connection
        'api_version': '1.0'
    })


# ==========================================
# Event Ingestion (REST alternative)
# ==========================================

@edge_bp.route('/events/detection', methods=['POST'])
def ingest_detection():
    """Ingest detection event from edge device."""
    edge = verify_edge_auth()
    if not edge:
        return jsonify({'error': 'Authentication required'}), 401
    
    data = request.get_json()
    
    event_service = get_event_service()
    event_id = event_service.store_detection({
        'tenant_id': edge['tenant_id'],
        'edge_id': edge['edge_id'],
        **data
    })
    
    if event_id:
        return jsonify({'success': True, 'event_id': event_id}), 201
    else:
        return jsonify({'error': 'Failed to store event'}), 500


@edge_bp.route('/events/zone', methods=['POST'])
def ingest_zone_event():
    """Ingest zone event from edge device."""
    edge = verify_edge_auth()
    if not edge:
        return jsonify({'error': 'Authentication required'}), 401
    
    data = request.get_json()
    
    event_service = get_event_service()
    event_id = event_service.store_zone_event({
        'tenant_id': edge['tenant_id'],
        'edge_id': edge['edge_id'],
        **data
    })
    
    if event_id:
        return jsonify({'success': True, 'event_id': event_id}), 201
    else:
        return jsonify({'error': 'Failed to store event'}), 500


@edge_bp.route('/events/batch', methods=['POST'])
def ingest_batch():
    """Ingest batch of events from edge device."""
    edge = verify_edge_auth()
    if not edge:
        return jsonify({'error': 'Authentication required'}), 401
    
    data = request.get_json()
    detections = data.get('detections', [])
    zone_events = data.get('zone_events', [])
    
    event_service = get_event_service()
    results = {
        'detections_stored': 0,
        'zone_events_stored': 0,
        'errors': []
    }
    
    for detection in detections:
        event_id = event_service.store_detection({
            'tenant_id': edge['tenant_id'],
            'edge_id': edge['edge_id'],
            **detection
        })
        if event_id:
            results['detections_stored'] += 1
        else:
            results['errors'].append(f"Failed to store detection: {detection.get('timestamp')}")
    
    for zone_event in zone_events:
        event_id = event_service.store_zone_event({
            'tenant_id': edge['tenant_id'],
            'edge_id': edge['edge_id'],
            **zone_event
        })
        if event_id:
            results['zone_events_stored'] += 1
        else:
            results['errors'].append(f"Failed to store zone event: {zone_event.get('timestamp')}")
    
    return jsonify(results)


# ==========================================
# Clip Upload
# ==========================================

@edge_bp.route('/clips', methods=['POST'])
def upload_clip():
    """Upload event clip from edge device."""
    edge = verify_edge_auth()
    if not edge:
        return jsonify({'error': 'Authentication required'}), 401
    
    # Check if file was uploaded
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    metadata = request.form.get('metadata', '{}')
    
    import json
    import os
    
    try:
        meta = json.loads(metadata)
    except:
        meta = {}
    
    # Save file
    from flask import current_app
    upload_dir = current_app.config.get('CLIP_UPLOAD_DIR', './clips')
    os.makedirs(upload_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{edge['edge_id']}_{timestamp}_{file.filename}"
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    
    # Store metadata
    event_service = get_event_service()
    clip_id = event_service.store_clip_metadata({
        'tenant_id': edge['tenant_id'],
        'edge_id': edge['edge_id'],
        'camera_id': meta.get('camera_id'),
        'event_type': meta.get('event_type', 'unknown'),
        'event_id': meta.get('event_id'),
        'timestamp': meta.get('timestamp', datetime.now().isoformat()),
        'duration': meta.get('duration'),
        'file_path': filepath,
        'file_size': os.path.getsize(filepath),
        'metadata': meta
    })
    
    return jsonify({
        'success': True,
        'clip_id': clip_id,
        'filename': filename
    }), 201


# ==========================================
# Edge Status & Health
# ==========================================

@edge_bp.route('/heartbeat', methods=['POST'])
def heartbeat():
    """Edge device heartbeat."""
    edge = verify_edge_auth()
    if not edge:
        return jsonify({'error': 'Authentication required'}), 401
    
    data = request.get_json() or {}
    
    # Update edge status in manager
    edge_manager = get_edge_manager()
    if edge_manager:
        edge_manager.update_edge_status(edge['edge_id'], {
            'last_heartbeat': datetime.now().isoformat(),
            **data
        })
    
    return jsonify({
        'success': True,
        'server_time': datetime.now().isoformat()
    })


@edge_bp.route('/config', methods=['GET'])
def get_config():
    """Get configuration for edge device."""
    edge = verify_edge_auth()
    if not edge:
        return jsonify({'error': 'Authentication required'}), 401
    
    tenant_service = get_tenant_service()
    edges = tenant_service.list_edge_devices(edge['tenant_id'])
    edge_data = next((e for e in edges if e['id'] == edge['edge_id']), None)
    
    config = {}
    if edge_data and edge_data.get('config'):
        import json
        try:
            config = json.loads(edge_data['config'])
        except:
            pass
    
    return jsonify({'config': config})


@edge_bp.route('/status', methods=['GET'])
def list_connected_edges():
    """List all connected edge devices (admin endpoint)."""
    # This would need admin auth in production
    edge_manager = get_edge_manager()
    
    if not edge_manager:
        return jsonify({'error': 'Edge manager not available'}), 500
    
    status = edge_manager.get_all_status()
    return jsonify({'edges': status})
