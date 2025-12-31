"""
Timeline REST API routes
"""

from flask import Blueprint, jsonify, request
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Blueprint for timeline routes
timeline_bp = Blueprint('timeline', __name__, url_prefix='/api/timeline')

# Global reference to timeline manager (set by app.py)
_timeline_manager = None


def set_timeline_manager(timeline_manager):
    """Set the timeline manager instance (called from app.py)"""
    global _timeline_manager
    _timeline_manager = timeline_manager


@timeline_bp.route('/<camera_id>', methods=['GET'])
def get_timeline(camera_id):
    """
    Get timeline buckets for a camera in date range
    
    Query Parameters:
        start_date (YYYY-MM-DD) - Start date
        end_date (YYYY-MM-DD) - End date
        granularity (hourly|daily) - Bucket size (default: hourly)
    
    Returns:
        {
            "camera_id": "wisenet_front",
            "granularity": "hourly",
            "buckets": [
                {
                    "date": "2025-11-11",
                    "hour": 0,
                    "segment_count": 120,
                    "total_duration_ms": 360000,
                    "total_size_bytes": 52428800,
                    "has_motion": false,
                    "first_segment_time": "2025-11-11T00:00:00",
                    "last_segment_time": "2025-11-11T00:59:59"
                },
                ...
            ]
        }
    """
    if not _timeline_manager:
        return jsonify({'error': 'Timeline manager not initialized'}), 503
    
    try:
        # Get query parameters
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        granularity = request.args.get('granularity', 'hourly')
        
        if not start_date_str or not end_date_str:
            return jsonify({'error': 'start_date and end_date are required (YYYY-MM-DD)'}), 400
        
        # Parse dates
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        # Get timeline buckets
        buckets = _timeline_manager.get_timeline(camera_id, start_date, end_date)
        
        if not buckets:
            return jsonify({
                'camera_id': camera_id,
                'granularity': granularity,
                'buckets': []
            }), 200
        
        # Convert to response format
        response_buckets = []
        for bucket in buckets:
            response_buckets.append({
                'date': bucket.get('date'),
                'hour': bucket.get('hour'),
                'segment_count': bucket.get('segment_count', 0),
                'total_duration_ms': bucket.get('total_duration_ms', 0),
                'total_size_bytes': bucket.get('total_size_bytes', 0),
                'has_motion': bool(bucket.get('has_motion', 0)),
                'first_segment_time': bucket.get('first_segment_time'),
                'last_segment_time': bucket.get('last_segment_time')
            })
        
        return jsonify({
            'camera_id': camera_id,
            'granularity': granularity,
            'start_date': start_date_str,
            'end_date': end_date_str,
            'bucket_count': len(response_buckets),
            'buckets': response_buckets
        }), 200
    
    except Exception as e:
        logger.error(f"Error getting timeline for {camera_id}: {e}")
        return jsonify({'error': str(e)}), 500


@timeline_bp.route('/<camera_id>/hourly/<date>', methods=['GET'])
def get_hourly_summary(camera_id, date):
    """
    Get detailed hourly breakdown for a specific date
    
    Args:
        camera_id: Camera identifier
        date: Date in YYYY-MM-DD format
    
    Returns:
        {
            "camera_id": "wisenet_front",
            "date": "2025-11-11",
            "hours": [
                {
                    "hour": 0,
                    "segment_count": 120,
                    "total_duration_ms": 360000,
                    "total_size_bytes": 52428800,
                    "has_motion": false
                },
                ...
            ]
        }
    """
    if not _timeline_manager:
        return jsonify({'error': 'Timeline manager not initialized'}), 503
    
    try:
        # Parse date
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        # Get hourly summary
        hours = _timeline_manager.get_hourly_summary(camera_id, date_obj)
        
        if not hours:
            return jsonify({
                'camera_id': camera_id,
                'date': date,
                'hours': []
            }), 200
        
        # Convert to response format
        response_hours = []
        for hour in hours:
            response_hours.append({
                'hour': hour.get('hour'),
                'segment_count': hour.get('segment_count', 0),
                'total_duration_ms': hour.get('total_duration_ms', 0),
                'total_size_bytes': hour.get('total_size_bytes', 0),
                'has_motion': bool(hour.get('has_motion', 0))
            })
        
        return jsonify({
            'camera_id': camera_id,
            'date': date,
            'hour_count': len(response_hours),
            'hours': response_hours
        }), 200
    
    except Exception as e:
        logger.error(f"Error getting hourly summary for {camera_id} on {date}: {e}")
        return jsonify({'error': str(e)}), 500

