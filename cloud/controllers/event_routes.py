"""
Event Routes
Query events, alerts, and clips from edge devices.
"""

from flask import Blueprint, request, jsonify, g, send_file
from .auth_routes import token_required
from datetime import datetime, timedelta
import os

event_bp = Blueprint('events', __name__, url_prefix='/api/events')


def get_event_service():
    """Get event service from app context."""
    from flask import current_app
    return current_app.config.get('event_service')


def get_alert_service():
    """Get alert service from app context."""
    from flask import current_app
    return current_app.config.get('alert_service')


# ==========================================
# Detections
# ==========================================

@event_bp.route('/detections', methods=['GET'])
@token_required
def list_detections():
    """List detection events."""
    event_service = get_event_service()
    
    # Query parameters
    edge_id = request.args.get('edge_id')
    camera_id = request.args.get('camera_id')
    object_class = request.args.get('object_class')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    limit = int(request.args.get('limit', 100))
    
    # Default to last 24 hours if no time specified
    if not start_time:
        start_time = (datetime.now() - timedelta(hours=24)).isoformat()
    
    detections = event_service.get_detections(
        tenant_id=g.user['tenant_id'],
        edge_id=edge_id,
        camera_id=camera_id,
        object_class=object_class,
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )
    
    return jsonify({
        'detections': detections,
        'count': len(detections)
    })


# ==========================================
# Zone Events
# ==========================================

@event_bp.route('/zones', methods=['GET'])
@token_required
def list_zone_events():
    """List zone events."""
    event_service = get_event_service()
    
    # Query parameters
    edge_id = request.args.get('edge_id')
    zone_id = request.args.get('zone_id')
    event_type = request.args.get('event_type')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    limit = int(request.args.get('limit', 100))
    
    # Default to last 24 hours if no time specified
    if not start_time:
        start_time = (datetime.now() - timedelta(hours=24)).isoformat()
    
    events = event_service.get_zone_events(
        tenant_id=g.user['tenant_id'],
        edge_id=edge_id,
        zone_id=zone_id,
        event_type=event_type,
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )
    
    return jsonify({
        'zone_events': events,
        'count': len(events)
    })


# ==========================================
# Clips
# ==========================================

@event_bp.route('/clips', methods=['GET'])
@token_required
def list_clips():
    """List event clips."""
    event_service = get_event_service()
    
    # Query parameters
    edge_id = request.args.get('edge_id')
    camera_id = request.args.get('camera_id')
    event_type = request.args.get('event_type')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    limit = int(request.args.get('limit', 50))
    
    # Default to last 7 days if no time specified
    if not start_time:
        start_time = (datetime.now() - timedelta(days=7)).isoformat()
    
    clips = event_service.get_clips(
        tenant_id=g.user['tenant_id'],
        edge_id=edge_id,
        camera_id=camera_id,
        event_type=event_type,
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )
    
    return jsonify({
        'clips': clips,
        'count': len(clips)
    })


@event_bp.route('/clips/<clip_id>/download', methods=['GET'])
@token_required
def download_clip(clip_id):
    """Download a clip file."""
    event_service = get_event_service()
    
    # Get clip metadata
    clips = event_service.get_clips(
        tenant_id=g.user['tenant_id'],
        limit=1000
    )
    
    clip = next((c for c in clips if c['id'] == clip_id), None)
    if not clip:
        return jsonify({'error': 'Clip not found'}), 404
    
    file_path = clip.get('file_path')
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': 'Clip file not found'}), 404
    
    return send_file(
        file_path,
        mimetype='video/mp4',
        as_attachment=True,
        download_name=f"clip_{clip_id}.mp4"
    )


# ==========================================
# Alerts
# ==========================================

@event_bp.route('/alerts', methods=['GET'])
@token_required
def list_alerts():
    """List alerts."""
    event_service = get_event_service()
    
    # Query parameters
    edge_id = request.args.get('edge_id')
    alert_type = request.args.get('alert_type')
    severity = request.args.get('severity')
    acknowledged = request.args.get('acknowledged')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    limit = int(request.args.get('limit', 100))
    
    # Convert acknowledged to bool
    ack_filter = None
    if acknowledged is not None:
        ack_filter = acknowledged.lower() == 'true'
    
    # Default to last 7 days if no time specified
    if not start_time:
        start_time = (datetime.now() - timedelta(days=7)).isoformat()
    
    alerts = event_service.get_alerts(
        tenant_id=g.user['tenant_id'],
        edge_id=edge_id,
        alert_type=alert_type,
        severity=severity,
        acknowledged=ack_filter,
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )
    
    # Get unacknowledged count
    unack_count = event_service.get_unacknowledged_count(g.user['tenant_id'])
    
    return jsonify({
        'alerts': alerts,
        'count': len(alerts),
        'unacknowledged_count': unack_count
    })


@event_bp.route('/alerts/<alert_id>/acknowledge', methods=['POST'])
@token_required
def acknowledge_alert(alert_id):
    """Acknowledge an alert."""
    event_service = get_event_service()
    
    success = event_service.acknowledge_alert(alert_id, g.user['user_id'])
    
    if not success:
        return jsonify({'error': 'Failed to acknowledge alert'}), 400
    
    return jsonify({'success': True})


@event_bp.route('/alerts/acknowledge-all', methods=['POST'])
@token_required
def acknowledge_all_alerts():
    """Acknowledge all alerts."""
    event_service = get_event_service()
    
    # Get all unacknowledged alerts
    alerts = event_service.get_alerts(
        tenant_id=g.user['tenant_id'],
        acknowledged=False,
        limit=1000
    )
    
    count = 0
    for alert in alerts:
        if event_service.acknowledge_alert(alert['id'], g.user['user_id']):
            count += 1
    
    return jsonify({
        'success': True,
        'acknowledged_count': count
    })


# ==========================================
# Analytics
# ==========================================

@event_bp.route('/analytics/detections', methods=['GET'])
@token_required
def detection_analytics():
    """Get detection analytics."""
    event_service = get_event_service()
    
    # Query parameters
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    group_by = request.args.get('group_by', 'hour')
    
    # Default to last 24 hours
    if not start_time:
        start_time = (datetime.now() - timedelta(hours=24)).isoformat()
    if not end_time:
        end_time = datetime.now().isoformat()
    
    data = event_service.get_detection_counts(
        tenant_id=g.user['tenant_id'],
        start_time=start_time,
        end_time=end_time,
        group_by=group_by
    )
    
    return jsonify({'analytics': data})


@event_bp.route('/analytics/zones', methods=['GET'])
@token_required
def zone_analytics():
    """Get zone activity analytics."""
    event_service = get_event_service()
    
    # Query parameters
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    
    # Default to last 24 hours
    if not start_time:
        start_time = (datetime.now() - timedelta(hours=24)).isoformat()
    if not end_time:
        end_time = datetime.now().isoformat()
    
    data = event_service.get_zone_activity(
        tenant_id=g.user['tenant_id'],
        start_time=start_time,
        end_time=end_time
    )
    
    return jsonify({'analytics': data})


# ==========================================
# Alert Rules
# ==========================================

@event_bp.route('/rules', methods=['GET'])
@token_required
def list_alert_rules():
    """List alert rules."""
    alert_service = get_alert_service()
    rules = alert_service.get_rules(g.user['tenant_id'])
    return jsonify({'rules': rules})


@event_bp.route('/rules', methods=['POST'])
@token_required
def create_alert_rule():
    """Create a new alert rule."""
    data = request.get_json()
    
    alert_service = get_alert_service()
    rule_id = alert_service.add_rule(g.user['tenant_id'], data)
    
    return jsonify({
        'rule_id': rule_id,
        'success': True
    }), 201


@event_bp.route('/rules/<rule_id>', methods=['DELETE'])
@token_required
def delete_alert_rule(rule_id):
    """Delete an alert rule."""
    alert_service = get_alert_service()
    success = alert_service.remove_rule(g.user['tenant_id'], rule_id)
    
    if not success:
        return jsonify({'error': 'Rule not found'}), 404
    
    return jsonify({'success': True})
