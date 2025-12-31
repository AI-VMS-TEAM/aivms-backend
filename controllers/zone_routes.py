"""
Zone Analytics API Routes for Vision 31: Structured Metadata & Context System

Provides REST API endpoints for zone-based analytics:
- Zone list and configuration
- Zone traffic analytics (entries/exits)
- Zone dwell time analytics
- Zone heatmap data
- Zone event history
"""

import logging
import sqlite3
import json
from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Create blueprint
zone_bp = Blueprint('zones', __name__, url_prefix='/api/zones')

# Global references (set by app.py)
_zone_service = None
_tracking_service = None
_db_path = None


def set_zone_service(zone_service, tracking_service, db_path):
    """Set zone service, tracking service, and database path."""
    global _zone_service, _tracking_service, _db_path
    _zone_service = zone_service
    _tracking_service = tracking_service
    _db_path = db_path
    logger.info(f"Zone service initialized: {zone_service is not None}")


@zone_bp.route('/debug', methods=['GET'])
def debug():
    """Debug endpoint to verify blueprint is loaded."""
    return jsonify({
        'status': 'ok',
        'zone_service_initialized': _zone_service is not None,
        'tracking_service_initialized': _tracking_service is not None,
        'db_path': _db_path
    }), 200


@zone_bp.route('/list', methods=['GET'])
def get_zones():
    """
    Get list of zones for a camera.
    
    Query Parameters:
        camera_id: Camera identifier (required)
    """
    if not _zone_service:
        return jsonify({'error': 'Zone service not initialized'}), 500
    
    camera_id = request.args.get('camera_id')
    if not camera_id:
        return jsonify({'error': 'camera_id parameter required'}), 400
    
    try:
        zones = _zone_service.get_zones_for_camera(camera_id)
        
        zones_data = []
        for zone in zones:
            zones_data.append({
                'id': zone.id,
                'name': zone.name,
                'description': zone.description,
                'type': zone.type,
                'color': zone.color,
                'polygon': zone.polygon
            })
        
        return jsonify({
            'camera_id': camera_id,
            'zone_count': len(zones_data),
            'zones': zones_data
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting zones: {e}")
        return jsonify({'error': str(e)}), 500


@zone_bp.route('/analytics', methods=['GET'])
def get_zone_analytics():
    """
    Get zone analytics (traffic, dwell time, etc.).
    
    Query Parameters:
        camera_id: Camera identifier (required)
        zone_id: Zone identifier (optional, all zones if not specified)
        start_time: Start time ISO format (optional, default: 24 hours ago)
        end_time: End time ISO format (optional, default: now)
    """
    if not _db_path:
        return jsonify({'error': 'Database not initialized'}), 500
    
    camera_id = request.args.get('camera_id')
    if not camera_id:
        return jsonify({'error': 'camera_id parameter required'}), 400
    
    zone_id = request.args.get('zone_id')
    
    # Parse time range
    end_time = request.args.get('end_time')
    start_time = request.args.get('start_time')
    
    if end_time:
        end_ts = datetime.fromisoformat(end_time).timestamp()
    else:
        end_ts = datetime.now().timestamp()
    
    if start_time:
        start_ts = datetime.fromisoformat(start_time).timestamp()
    else:
        start_ts = (datetime.now() - timedelta(hours=24)).timestamp()
    
    try:
        conn = sqlite3.connect(_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Build query
        if zone_id:
            query = """
                SELECT 
                    zone_id,
                    COUNT(CASE WHEN event_type = 'enter' THEN 1 END) as entries,
                    COUNT(CASE WHEN event_type = 'exit' THEN 1 END) as exits,
                    COUNT(DISTINCT track_id) as unique_tracks
                FROM zone_events
                WHERE camera_id = ? AND zone_id = ? 
                AND timestamp >= ? AND timestamp <= ?
                GROUP BY zone_id
            """
            cursor.execute(query, (camera_id, zone_id, start_ts, end_ts))
        else:
            query = """
                SELECT 
                    zone_id,
                    COUNT(CASE WHEN event_type = 'enter' THEN 1 END) as entries,
                    COUNT(CASE WHEN event_type = 'exit' THEN 1 END) as exits,
                    COUNT(DISTINCT track_id) as unique_tracks
                FROM zone_events
                WHERE camera_id = ? 
                AND timestamp >= ? AND timestamp <= ?
                GROUP BY zone_id
            """
            cursor.execute(query, (camera_id, start_ts, end_ts))
        
        rows = cursor.fetchall()
        conn.close()
        
        analytics = []
        for row in rows:
            analytics.append({
                'zone_id': row['zone_id'],
                'entries': row['entries'],
                'exits': row['exits'],
                'unique_tracks': row['unique_tracks'],
                'current_occupancy': row['entries'] - row['exits']
            })
        
        return jsonify({
            'camera_id': camera_id,
            'zone_id': zone_id,
            'start_time': datetime.fromtimestamp(start_ts).isoformat(),
            'end_time': datetime.fromtimestamp(end_ts).isoformat(),
            'analytics': analytics
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting zone analytics: {e}")
        return jsonify({'error': str(e)}), 500


@zone_bp.route('/events', methods=['GET'])
def get_zone_events():
    """
    Get zone entry/exit events.

    Query Parameters:
        camera_id: Camera identifier (required)
        zone_id: Zone identifier (optional)
        event_type: Event type - 'enter' or 'exit' (optional)
        start_time: Start time ISO format (optional, default: 1 hour ago)
        end_time: End time ISO format (optional, default: now)
        limit: Maximum number of events (optional, default: 100)
    """
    if not _db_path:
        return jsonify({'error': 'Database not initialized'}), 500

    camera_id = request.args.get('camera_id')
    if not camera_id:
        return jsonify({'error': 'camera_id parameter required'}), 400

    zone_id = request.args.get('zone_id')
    event_type = request.args.get('event_type')
    limit = int(request.args.get('limit', 100))

    # Parse time range
    end_time = request.args.get('end_time')
    start_time = request.args.get('start_time')

    if end_time:
        end_ts = datetime.fromisoformat(end_time).timestamp()
    else:
        end_ts = datetime.now().timestamp()

    if start_time:
        start_ts = datetime.fromisoformat(start_time).timestamp()
    else:
        start_ts = (datetime.now() - timedelta(hours=1)).timestamp()

    try:
        conn = sqlite3.connect(_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Build query
        query = """
            SELECT * FROM zone_events
            WHERE camera_id = ?
            AND timestamp >= ? AND timestamp <= ?
        """
        params = [camera_id, start_ts, end_ts]

        if zone_id:
            query += " AND zone_id = ?"
            params.append(zone_id)

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        events = []
        for row in rows:
            event = dict(row)
            # Parse JSON fields
            if event['bbox']:
                event['bbox'] = json.loads(event['bbox'])
            if event['metadata_json']:
                event['metadata'] = json.loads(event['metadata_json'])
                del event['metadata_json']

            # Add zone name
            zone_id = event.get('zone_id')
            zone_name = zone_id
            if _zone_service and camera_id in _zone_service.zones:
                for z in _zone_service.zones[camera_id]:
                    if z.id == zone_id:
                        zone_name = z.name
                        break
            event['zone_name'] = zone_name

            events.append(event)

        return jsonify({
            'camera_id': camera_id,
            'zone_id': zone_id,
            'event_type': event_type,
            'start_time': datetime.fromtimestamp(start_ts).isoformat(),
            'end_time': datetime.fromtimestamp(end_ts).isoformat(),
            'event_count': len(events),
            'events': events
        }), 200

    except Exception as e:
        logger.error(f"Error getting zone events: {e}")
        return jsonify({'error': str(e)}), 500


@zone_bp.route('/current', methods=['GET'])
def get_current_zone_occupancy():
    """
    Get current zone occupancy (active tracks per zone).

    Query Parameters:
        camera_id: Camera identifier (required)
    """
    if not _zone_service or not _tracking_service:
        return jsonify({'error': 'Services not initialized'}), 500

    camera_id = request.args.get('camera_id')
    if not camera_id:
        return jsonify({'error': 'camera_id parameter required'}), 400

    try:
        import time
        current_time = time.time()

        # Get active tracks
        tracks = _tracking_service.get_active_tracks_with_dwell(camera_id, current_time)

        # Count tracks per zone
        zone_occupancy = {}
        for track in tracks:
            zone_id = _zone_service.get_current_zone(camera_id, track['track_id'])
            if zone_id:
                if zone_id not in zone_occupancy:
                    # Get zone object to get zone name
                    zone_obj = None
                    if camera_id in _zone_service.zones:
                        for z in _zone_service.zones[camera_id]:
                            if z.id == zone_id:
                                zone_obj = z
                                break

                    zone_occupancy[zone_id] = {
                        'zone_id': zone_id,
                        'zone_name': zone_obj.name if zone_obj else zone_id,
                        'track_count': 0,
                        'tracks': []
                    }
                zone_occupancy[zone_id]['track_count'] += 1
                zone_occupancy[zone_id]['tracks'].append({
                    'track_id': track['track_id'],
                    'class': track['class'],
                    'dwell_time': track['dwell_time']
                })

        return jsonify({
            'camera_id': camera_id,
            'timestamp': current_time,
            'zones': list(zone_occupancy.values())
        }), 200

    except Exception as e:
        logger.error(f"Error getting current zone occupancy: {e}")
        return jsonify({'error': str(e)}), 500

