"""
Detection API Routes

Endpoints for querying object detections.
Includes WebSocket support for real-time detection streaming.
"""

from flask import Blueprint, request, jsonify
from flask_socketio import emit, join_room, leave_room
import logging
import sqlite3
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

detection_bp = Blueprint('detection', __name__, url_prefix='/api/detection')

# Global references (set by app.py)
_detection_service = None
_frame_extractors = {}
_db_path = None
_socketio = None


def set_detection_service(detection_service, frame_extractors, db_path):
    """Set global references for detection service."""
    global _detection_service, _frame_extractors, _db_path
    _detection_service = detection_service
    _frame_extractors = frame_extractors
    _db_path = db_path


def set_socketio(socketio):
    """Set SocketIO instance for WebSocket support."""
    global _socketio
    _socketio = socketio


def broadcast_detections(camera_id, detections, timestamp, tracks=None):
    """
    Broadcast detections and tracks to WebSocket clients.
    Called by detection service when new detections are made.

    Args:
        camera_id: Camera identifier
        detections: List of detection dicts
        timestamp: Detection timestamp
        tracks: Optional list of track dicts (with track IDs)
    """
    if not _socketio:
        return

    # Prepare detection data for broadcasting
    detection_data = {
        'camera_id': camera_id,
        'timestamp': timestamp,
        'detections': detections,
        'count': len(detections),
        'tracks': tracks or [],
        'track_count': len(tracks) if tracks else 0
    }

    # Broadcast to all clients subscribed to this camera
    _socketio.emit('detections', detection_data, room=f'camera_{camera_id}', namespace='/detections')

    # Also broadcast to 'all' room for clients monitoring all cameras
    _socketio.emit('detections', detection_data, room='all', namespace='/detections')


def broadcast_zone_event(zone_event):
    """
    Broadcast zone entry/exit event to WebSocket clients (Vision 31).

    Args:
        zone_event: ZoneEvent object with track_id, camera_id, zone_id, event_type, timestamp, bbox
    """
    if not _socketio:
        return

    # Prepare zone event data for broadcasting
    event_data = {
        'track_id': zone_event.track_id,
        'camera_id': zone_event.camera_id,
        'zone_id': zone_event.zone_id,
        'event_type': zone_event.event_type,
        'timestamp': zone_event.timestamp,
        'bbox': zone_event.bbox
    }

    # Broadcast to zone-specific room
    _socketio.emit('zone_event', event_data, room=f'zone_{zone_event.zone_id}', namespace='/detections')

    # Broadcast to camera-specific room
    _socketio.emit('zone_event', event_data, room=f'camera_{zone_event.camera_id}', namespace='/detections')

    # Broadcast to 'all' room
    _socketio.emit('zone_event', event_data, room='all', namespace='/detections')


@detection_bp.route('/status', methods=['GET'])
def get_detection_status():
    """Get detection service status."""
    if not _detection_service:
        return jsonify({'error': 'Detection service not initialized'}), 503
    
    stats = _detection_service.get_stats()
    extractor_stats = {cid: ext.get_stats() for cid, ext in _frame_extractors.items()}
    
    return jsonify({
        'detection_service': stats,
        'frame_extractors': extractor_stats
    })


@detection_bp.route('/detections', methods=['GET'])
def get_detections():
    """
    Query detections for a camera in a time range.
    
    Query params:
    - camera_id: Camera identifier (required)
    - start_time: ISO format timestamp (required)
    - end_time: ISO format timestamp (required)
    - class: Filter by class (optional)
    - min_confidence: Minimum confidence (optional, default 0.0)
    """
    try:
        camera_id = request.args.get('camera_id')
        start_time_str = request.args.get('start_time')
        end_time_str = request.args.get('end_time')
        class_filter = request.args.get('class')
        min_confidence = float(request.args.get('min_confidence', 0.0))
        
        if not all([camera_id, start_time_str, end_time_str]):
            return jsonify({'error': 'Missing required parameters'}), 400
        
        # Parse timestamps
        start_time = datetime.fromisoformat(start_time_str).timestamp()
        end_time = datetime.fromisoformat(end_time_str).timestamp()
        
        # Query database
        conn = sqlite3.connect(_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = """
            SELECT * FROM detections
            WHERE camera_id = ? AND timestamp BETWEEN ? AND ?
            AND confidence >= ?
        """
        params = [camera_id, start_time, end_time, min_confidence]
        
        if class_filter:
            query += " AND class = ?"
            params.append(class_filter)
        
        query += " ORDER BY timestamp DESC LIMIT 1000"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        detections = []
        for row in rows:
            detections.append({
                'id': row['id'],
                'camera_id': row['camera_id'],
                'timestamp': row['timestamp'],
                'class': row['class'],
                'confidence': row['confidence'],
                'bbox': row['bbox']
            })
        
        return jsonify({
            'camera_id': camera_id,
            'start_time': start_time_str,
            'end_time': end_time_str,
            'count': len(detections),
            'detections': detections
        })
        
    except Exception as e:
        logger.error(f"Error querying detections: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@detection_bp.route('/stats', methods=['GET'])
def get_detection_stats():
    """Get detection statistics."""
    try:
        conn = sqlite3.connect(_db_path)
        cursor = conn.cursor()
        
        # Total detections
        cursor.execute("SELECT COUNT(*) FROM detections")
        total_detections = cursor.fetchone()[0]
        
        # Detections by class
        cursor.execute("""
            SELECT class, COUNT(*) as count
            FROM detections
            GROUP BY class
            ORDER BY count DESC
        """)
        by_class = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Detections by camera
        cursor.execute("""
            SELECT camera_id, COUNT(*) as count
            FROM detections
            GROUP BY camera_id
            ORDER BY count DESC
        """)
        by_camera = {row[0]: row[1] for row in cursor.fetchall()}
        
        conn.close()
        
        return jsonify({
            'total_detections': total_detections,
            'by_class': by_class,
            'by_camera': by_camera
        })
        
    except Exception as e:
        logger.error(f"Error getting detection stats: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ============================================================
# WebSocket Event Handlers
# ============================================================

def register_socketio_handlers(socketio):
    """Register SocketIO event handlers for real-time detections."""

    @socketio.on('connect', namespace='/detections')
    def handle_connect():
        """Handle client connection."""
        logger.info(f"Client connected to detections WebSocket")
        emit('connected', {'message': 'Connected to detection stream'})

    @socketio.on('disconnect', namespace='/detections')
    def handle_disconnect():
        """Handle client disconnection."""
        logger.info(f"Client disconnected from detections WebSocket")

    @socketio.on('subscribe', namespace='/detections')
    def handle_subscribe(data):
        """
        Subscribe to detection stream for specific camera or all cameras.

        Args:
            data: {'camera_id': 'camera_name'} or {'camera_id': 'all'}
        """
        camera_id = data.get('camera_id', 'all')

        if camera_id == 'all':
            join_room('all')
            logger.info(f"Client subscribed to all cameras")
            emit('subscribed', {'camera_id': 'all', 'message': 'Subscribed to all cameras'})
        else:
            join_room(f'camera_{camera_id}')
            logger.info(f"Client subscribed to camera: {camera_id}")
            emit('subscribed', {'camera_id': camera_id, 'message': f'Subscribed to {camera_id}'})

    @socketio.on('unsubscribe', namespace='/detections')
    def handle_unsubscribe(data):
        """
        Unsubscribe from detection stream.

        Args:
            data: {'camera_id': 'camera_name'} or {'camera_id': 'all'}
        """
        camera_id = data.get('camera_id', 'all')

        if camera_id == 'all':
            leave_room('all')
            logger.info(f"Client unsubscribed from all cameras")
            emit('unsubscribed', {'camera_id': 'all', 'message': 'Unsubscribed from all cameras'})
        else:
            leave_room(f'camera_{camera_id}')
            logger.info(f"Client unsubscribed from camera: {camera_id}")
            emit('unsubscribed', {'camera_id': camera_id, 'message': f'Unsubscribed from {camera_id}'})

