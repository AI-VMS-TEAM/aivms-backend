"""
Tracking API Routes for Vision 30

Endpoints:
- GET /api/tracking/status - Service status and statistics
- GET /api/tracking/tracks - Query closed tracks
- GET /api/tracking/active - Get active tracks for camera
- GET /api/tracking/stats - Tracking statistics
"""

import logging
import sqlite3
from flask import Blueprint, request, jsonify
from datetime import datetime

logger = logging.getLogger(__name__)

tracking_bp = Blueprint('tracking', __name__, url_prefix='/api/tracking')

# Global references (set by app.py)
_tracking_service = None
_frame_extractors = None
_db_path = None


def set_tracking_service(tracking_service, frame_extractors, db_path):
    """Set global references for tracking service."""
    global _tracking_service, _frame_extractors, _db_path
    _tracking_service = tracking_service
    _frame_extractors = frame_extractors
    _db_path = db_path


@tracking_bp.route('/status', methods=['GET'])
def get_tracking_status():
    """Get tracking service status."""
    if not _tracking_service:
        return jsonify({'error': 'Tracking service not initialized'}), 500
    
    try:
        stats = _tracking_service.get_stats()
        
        # Get frame extractor stats
        extractors_stats = {}
        if _frame_extractors:
            for camera_id, extractor in _frame_extractors.items():
                extractors_stats[camera_id] = extractor.get_stats()
        
        return jsonify({
            'tracking_service': stats,
            'frame_extractors': extractors_stats
        }), 200
    except Exception as e:
        logger.error(f"Error getting tracking status: {e}")
        return jsonify({'error': str(e)}), 500


@tracking_bp.route('/active', methods=['GET'])
def get_active_tracks():
    """
    Get active tracks for a camera.

    Query Parameters:
        camera_id: Camera identifier (required)
        real_time: If 'true', calculate dwell time up to current time (default: false)
    """
    if not _tracking_service:
        return jsonify({'error': 'Tracking service not initialized'}), 500

    camera_id = request.args.get('camera_id')
    if not camera_id:
        return jsonify({'error': 'camera_id parameter required'}), 400

    # Check if real-time dwell time is requested
    real_time = request.args.get('real_time', 'false').lower() == 'true'

    try:
        import time
        if real_time:
            # Get tracks with real-time dwell time
            tracks = _tracking_service.get_active_tracks_with_dwell(camera_id, time.time())
        else:
            # Get tracks with last_seen_time dwell time
            tracks = _tracking_service.get_active_tracks(camera_id)

        return jsonify({
            'camera_id': camera_id,
            'active_tracks': len(tracks),
            'tracks': tracks,
            'real_time': real_time
        }), 200
    except Exception as e:
        logger.error(f"Error getting active tracks: {e}")
        return jsonify({'error': str(e)}), 500


@tracking_bp.route('/tracks', methods=['GET'])
def query_tracks():
    """Query closed tracks from database."""
    if not _db_path:
        return jsonify({'error': 'Database not initialized'}), 500
    
    camera_id = request.args.get('camera_id')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    class_filter = request.args.get('class')
    min_dwell = request.args.get('min_dwell', type=float, default=0.0)
    
    if not camera_id or not start_time or not end_time:
        return jsonify({
            'error': 'camera_id, start_time, end_time parameters required'
        }), 400
    
    try:
        # Parse timestamps
        start_ts = datetime.fromisoformat(start_time).timestamp()
        end_ts = datetime.fromisoformat(end_time).timestamp()
        
        conn = sqlite3.connect(_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Build query
        query = """
            SELECT * FROM tracks
            WHERE camera_id = ? 
            AND enter_time >= ? 
            AND enter_time <= ?
            AND dwell_time >= ?
        """
        params = [camera_id, start_ts, end_ts, min_dwell]
        
        if class_filter:
            query += " AND class = ?"
            params.append(class_filter)
        
        query += " ORDER BY enter_time DESC LIMIT 1000"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        tracks = []
        for row in rows:
            track = dict(row)
            # Parse JSON fields
            import json
            track['last_bbox'] = json.loads(track['last_bbox'])
            tracks.append(track)
        
        conn.close()
        
        return jsonify({
            'camera_id': camera_id,
            'start_time': start_time,
            'end_time': end_time,
            'total_tracks': len(tracks),
            'tracks': tracks
        }), 200
    except Exception as e:
        logger.error(f"Error querying tracks: {e}")
        return jsonify({'error': str(e)}), 500


@tracking_bp.route('/stats', methods=['GET'])
def get_tracking_stats():
    """Get tracking statistics."""
    if not _tracking_service or not _db_path:
        return jsonify({'error': 'Services not initialized'}), 500
    
    try:
        stats = _tracking_service.get_stats()
        
        # Get database statistics
        conn = sqlite3.connect(_db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM tracks")
        total_closed_tracks = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT class, COUNT(*) as count 
            FROM tracks 
            GROUP BY class
        """)
        by_class = {row[0]: row[1] for row in cursor.fetchall()}
        
        cursor.execute("""
            SELECT camera_id, COUNT(*) as count 
            FROM tracks 
            GROUP BY camera_id
        """)
        by_camera = {row[0]: row[1] for row in cursor.fetchall()}
        
        cursor.execute("""
            SELECT AVG(dwell_time), MAX(dwell_time), MIN(dwell_time)
            FROM tracks
        """)
        dwell_stats = cursor.fetchone()
        
        conn.close()
        
        return jsonify({
            'service_stats': stats,
            'database_stats': {
                'total_closed_tracks': total_closed_tracks,
                'by_class': by_class,
                'by_camera': by_camera,
                'dwell_time': {
                    'average': dwell_stats[0],
                    'max': dwell_stats[1],
                    'min': dwell_stats[2]
                }
            }
        }), 200
    except Exception as e:
        logger.error(f"Error getting tracking stats: {e}")
        return jsonify({'error': str(e)}), 500

