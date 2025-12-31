"""
Health monitoring REST API routes
"""

from flask import Blueprint, jsonify, request
import logging

logger = logging.getLogger(__name__)

# Blueprint will be registered in app.py
health_bp = Blueprint('health', __name__, url_prefix='/api/health')

# Global reference to health monitor (set by app.py)
_health_monitor = None


def set_health_monitor(health_monitor):
    """Set the health monitor instance (called from app.py)"""
    global _health_monitor
    _health_monitor = health_monitor


@health_bp.route('/status', methods=['GET'])
def get_health_status():
    """
    Get current health status

    Returns:
        {
            "timestamp": 1699372800.0,
            "disk_status": "healthy|warning|critical",
            "iops_status": "healthy|warning|critical",
            "segment_status": "healthy|warning|critical",
            "overall_status": "healthy|warning|critical",
            "disk_metrics": {...},
            "camera_metrics": [...],
            "active_alerts": [...]
        }
    """
    logger.info(f"GET /api/health/status called, _health_monitor={_health_monitor}")

    if not _health_monitor:
        logger.warning("Health monitor not initialized")
        return jsonify({'error': 'Health monitor not initialized'}), 503

    try:
        status = _health_monitor.get_health_status()
        if status:
            return jsonify(status.to_dict()), 200
        else:
            return jsonify({'error': 'Health status not yet available'}), 503
    except Exception as e:
        logger.error(f"Error getting health status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@health_bp.route('/disk-usage', methods=['GET'])
def get_disk_usage():
    """
    Get detailed disk usage metrics
    
    Returns:
        {
            "timestamp": 1699372800.0,
            "total_gb": 976.0,
            "used_gb": 245.0,
            "free_gb": 731.0,
            "percent_used": 25.1,
            "percent_free": 74.9,
            "growth_rate_gb_per_hour": 12.5,
            "estimated_hours_until_full": 58.5,
            "camera_usage": [
                {
                    "camera_id": "wisenet_front",
                    "camera_name": "Wisenet Front",
                    "total_gb": 65.0,
                    "segment_count": 1250,
                    "percent_of_total": 26.5,
                    "growth_rate_gb_per_hour": 3.2
                },
                ...
            ]
        }
    """
    if not _health_monitor:
        return jsonify({'error': 'Health monitor not initialized'}), 503
    
    try:
        disk_metrics = _health_monitor.get_disk_metrics()
        if not disk_metrics:
            return jsonify({'error': 'Disk metrics not yet available'}), 503
        
        # Get camera metrics
        camera_metrics = []
        for camera_id in _health_monitor.camera_ids:
            metrics_list = _health_monitor.get_camera_metrics(camera_id)
            if metrics_list:
                latest = metrics_list[-1]
                camera_metrics.append({
                    'camera_id': latest.camera_id,
                    'camera_name': latest.camera_name,
                    'total_gb': latest.total_gb,
                    'segment_count': latest.segment_count,
                    'percent_of_total': latest.percent_of_total,
                    'growth_rate_gb_per_hour': latest.growth_rate_bytes_per_hour / (1024**3),
                })
        
        return jsonify({
            'timestamp': disk_metrics.timestamp,
            'total_gb': disk_metrics.total_gb,
            'used_gb': disk_metrics.used_gb,
            'free_gb': disk_metrics.free_gb,
            'percent_used': disk_metrics.percent_used,
            'percent_free': disk_metrics.percent_free,
            'growth_rate_gb_per_hour': disk_metrics.growth_rate_bytes_per_hour / (1024**3),
            'estimated_hours_until_full': disk_metrics.estimated_hours_until_full,
            'camera_usage': camera_metrics,
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting disk usage: {e}")
        return jsonify({'error': str(e)}), 500


@health_bp.route('/alerts', methods=['GET'])
def get_alerts():
    """
    Get recent alerts
    
    Query parameters:
        limit: Maximum number of alerts to return (default: 100)
    
    Returns:
        {
            "alerts": [
                {
                    "timestamp": 1699372800.0,
                    "alert_type": "disk_usage|iops|corruption|performance",
                    "severity": "info|warning|critical",
                    "message": "Alert message",
                    "camera_id": "camera_id or null",
                    "metric_value": 85.5,
                    "threshold": 85.0
                },
                ...
            ]
        }
    """
    if not _health_monitor:
        return jsonify({'error': 'Health monitor not initialized'}), 503
    
    try:
        limit = request.args.get('limit', 100, type=int)
        alerts = _health_monitor.get_alerts(limit=limit)
        
        return jsonify({
            'alerts': [alert.to_dict() for alert in alerts],
            'count': len(alerts),
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        return jsonify({'error': str(e)}), 500


@health_bp.route('/metrics', methods=['GET'])
def get_metrics_history():
    """
    Get historical metrics
    
    Query parameters:
        hours: Number of hours of history to return (default: 24)
    
    Returns:
        {
            "disk_metrics": [...],
            "camera_metrics": {...},
            "alerts": [...]
        }
    """
    if not _health_monitor:
        return jsonify({'error': 'Health monitor not initialized'}), 503
    
    try:
        hours = request.args.get('hours', 24, type=int)
        metrics = _health_monitor.get_metrics_history(hours=hours)
        
        return jsonify({
            'disk_metrics': [m.to_dict() for m in metrics['disk_metrics']],
            'camera_metrics': {
                camera_id: [m.to_dict() for m in metrics_list]
                for camera_id, metrics_list in metrics['camera_metrics'].items()
            },
            'alerts': [a.to_dict() for a in metrics['alerts']],
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting metrics history: {e}")
        return jsonify({'error': str(e)}), 500


@health_bp.route('/iops', methods=['GET'])
def get_iops():
    """
    Get write performance metrics (IOPS and throughput)

    Returns:
        {
            "current": {
                "timestamp": 1699372800.0,
                "operations_per_second": 1245.5,
                "throughput_mbps": 125.5,
                "total_operations": 450000,
                "total_bytes_written": 1099511627776
            },
            "by_camera": [
                {
                    "camera_id": "dahua_front_cam",
                    "total_operations": 120000,
                    "total_bytes": 549755813888,
                    "percent_of_total_ops": 26.67,
                    "percent_of_total_bytes": 50.0
                }
            ],
            "average_1h": {
                "avg_iops": 1200.5,
                "avg_throughput_mbps": 120.0,
                "min_iops": 1100.0,
                "max_iops": 1300.0
            },
            "average_24h": {...}
        }
    """
    if not _health_monitor:
        return jsonify({'error': 'Health monitor not initialized'}), 503

    try:
        iops_metrics = _health_monitor.get_iops_metrics()
        return jsonify(iops_metrics), 200
    except Exception as e:
        logger.error(f"Error getting IOPS metrics: {e}")
        return jsonify({'error': str(e)}), 500


@health_bp.route('/recovery/status', methods=['GET'])
def get_recovery_status():
    """
    Get recovery status for all cameras

    Returns:
        {
            "camera_id": {
                "error_count": 0,
                "recovery_count": 0,
                "last_error_time": 1699372800.0,
                "is_healthy": true
            },
            ...
        }
    """
    print("DEBUG: GET /api/health/recovery/status called")
    logger.info(f"GET /api/health/recovery/status called, _health_monitor={_health_monitor}")

    if not _health_monitor:
        logger.warning("Health monitor not initialized")
        return jsonify({'error': 'Health monitor not initialized'}), 503

    try:
        logger.info(f"Has recording_engine: {hasattr(_health_monitor, 'recording_engine')}")
        if hasattr(_health_monitor, 'recording_engine'):
            logger.info(f"recording_engine value: {_health_monitor.recording_engine}")

        if not hasattr(_health_monitor, 'recording_engine') or not _health_monitor.recording_engine:
            logger.warning("Recording engine not initialized or not linked")
            return jsonify({'error': 'Recording engine not initialized'}), 503

        recovery_tracker = _health_monitor.recording_engine.recovery_tracker
        print(f"DEBUG: recovery_tracker.camera_error_counts = {recovery_tracker.camera_error_counts}")
        status = recovery_tracker.get_all_camera_status()
        print(f"DEBUG: status = {status}")

        return jsonify(status), 200
    except Exception as e:
        logger.error(f"Error getting recovery status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@health_bp.route('/recovery/history', methods=['GET'])
def get_recovery_history():
    """
    Get recovery event history

    Query parameters:
        - camera_id: Optional camera ID to filter by
        - limit: Number of events to return (default: 100)

    Returns:
        [
            {
                "camera_id": "camera_1",
                "error_type": "write_failure",
                "message": "Disk full",
                "timestamp": 1699372800.0,
                "recovered": true,
                "recovery_time": 1699372805.0,
                "duration_seconds": 5.0
            },
            ...
        ]
    """
    if not _health_monitor:
        return jsonify({'error': 'Health monitor not initialized'}), 503

    try:
        if not hasattr(_health_monitor, 'recording_engine') or not _health_monitor.recording_engine:
            return jsonify({'error': 'Recording engine not initialized'}), 503

        camera_id = request.args.get('camera_id')
        limit = int(request.args.get('limit', 100))

        recovery_tracker = _health_monitor.recording_engine.recovery_tracker
        history = recovery_tracker.get_recovery_history(camera_id=camera_id, limit=limit)

        return jsonify(history), 200
    except Exception as e:
        logger.error(f"Error getting recovery history: {e}")
        return jsonify({'error': str(e)}), 500


# Retention Management Endpoints

@health_bp.route('/retention/policies', methods=['GET', 'POST'])
def retention_policies():
    """
    Get all retention policies (GET) or create/update a policy (POST)
    """
    if not _health_monitor:
        return jsonify({'error': 'Health monitor not initialized'}), 503

    try:
        if not hasattr(_health_monitor, 'recording_engine') or not _health_monitor.recording_engine:
            return jsonify({'error': 'Recording engine not initialized'}), 503

        policy_manager = _health_monitor.recording_engine.retention_manager.policy_manager

        if request.method == 'GET':
            policies = policy_manager.get_all_policies()
            return jsonify({'policies': policies}), 200
        else:  # POST
            data = request.get_json()
            camera_id = data.get('camera_id')
            retention_days = data.get('retention_days', 30)
            min_free_space_gb = data.get('min_free_space_gb', 50)
            emergency_cleanup_threshold = data.get('emergency_cleanup_threshold', 0.90)

            if not camera_id:
                return jsonify({'error': 'camera_id is required'}), 400

            success = policy_manager.create_or_update_policy(
                camera_id, retention_days, min_free_space_gb, emergency_cleanup_threshold
            )

            if success:
                policy = policy_manager.get_policy(camera_id)
                return jsonify(policy), 200
            else:
                return jsonify({'error': 'Failed to create/update policy'}), 500
    except Exception as e:
        logger.error(f"Error with retention policies: {e}")
        return jsonify({'error': str(e)}), 500


@health_bp.route('/retention/policies/<camera_id>', methods=['GET'])
def get_retention_policy(camera_id):
    """Get retention policy for a specific camera"""
    if not _health_monitor:
        return jsonify({'error': 'Health monitor not initialized'}), 503

    try:
        if not hasattr(_health_monitor, 'recording_engine') or not _health_monitor.recording_engine:
            return jsonify({'error': 'Recording engine not initialized'}), 503

        policy_manager = _health_monitor.recording_engine.retention_manager.policy_manager
        policy = policy_manager.get_policy(camera_id)

        if policy:
            return jsonify(policy), 200
        else:
            return jsonify({'error': f'No policy found for {camera_id}'}), 404
    except Exception as e:
        logger.error(f"Error getting retention policy: {e}")
        return jsonify({'error': str(e)}), 500


@health_bp.route('/retention/cleanup-history', methods=['GET'])
def get_cleanup_history():
    """Get cleanup history"""
    if not _health_monitor:
        return jsonify({'error': 'Health monitor not initialized'}), 503

    try:
        if not hasattr(_health_monitor, 'recording_engine') or not _health_monitor.recording_engine:
            return jsonify({'error': 'Recording engine not initialized'}), 503

        camera_id = request.args.get('camera_id')
        limit = int(request.args.get('limit', 100))

        policy_manager = _health_monitor.recording_engine.retention_manager.policy_manager
        history = policy_manager.get_cleanup_history(camera_id=camera_id, limit=limit)

        return jsonify({'history': history}), 200
    except Exception as e:
        logger.error(f"Error getting cleanup history: {e}")
        return jsonify({'error': str(e)}), 500


@health_bp.route('/retention/emergency-cleanup', methods=['POST'])
def trigger_emergency_cleanup():
    """Manually trigger emergency cleanup"""
    if not _health_monitor:
        return jsonify({'error': 'Health monitor not initialized'}), 503

    try:
        if not hasattr(_health_monitor, 'recording_engine') or not _health_monitor.recording_engine:
            return jsonify({'error': 'Recording engine not initialized'}), 503

        emergency_manager = _health_monitor.recording_engine.emergency_cleanup_manager
        emergency_manager._trigger_emergency_cleanup()

        status = emergency_manager.get_status()
        return jsonify({'status': 'Emergency cleanup triggered', 'details': status}), 200
    except Exception as e:
        logger.error(f"Error triggering emergency cleanup: {e}")
        return jsonify({'error': str(e)}), 500


@health_bp.route('/retention/status', methods=['GET'])
def get_retention_status():
    """Get retention system status"""
    if not _health_monitor:
        return jsonify({'error': 'Health monitor not initialized'}), 503

    try:
        if not hasattr(_health_monitor, 'recording_engine') or not _health_monitor.recording_engine:
            return jsonify({'error': 'Recording engine not initialized'}), 503

        retention_manager = _health_monitor.recording_engine.retention_manager
        emergency_manager = _health_monitor.recording_engine.emergency_cleanup_manager

        status = {
            'retention_info': retention_manager.get_retention_info(),
            'emergency_cleanup_status': emergency_manager.get_status()
        }

        return jsonify(status), 200
    except Exception as e:
        logger.error(f"Error getting retention status: {e}")
        return jsonify({'error': str(e)}), 500


# Timeline Indexing Endpoints

@health_bp.route('/timeline/<camera_id>', methods=['GET'])
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
            "buckets": [...]
        }
    """
    if not _health_monitor:
        return jsonify({'error': 'Health monitor not initialized'}), 503

    try:
        if not hasattr(_health_monitor, 'recording_engine') or not _health_monitor.recording_engine:
            return jsonify({'error': 'Recording engine not initialized'}), 503

        from datetime import datetime, timedelta

        # Get query parameters
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        granularity = request.args.get('granularity', 'hourly')

        # Default to last 7 days if not specified
        if not end_date_str:
            end_date = datetime.now()
        else:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')

        if not start_date_str:
            start_date = end_date - timedelta(days=7)
        else:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')

        timeline_manager = _health_monitor.recording_engine.timeline_manager
        buckets = timeline_manager.get_timeline(camera_id, start_date, end_date)

        return jsonify({
            'camera_id': camera_id,
            'granularity': granularity,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'buckets': buckets
        }), 200

    except Exception as e:
        logger.error(f"Error getting timeline for {camera_id}: {e}")
        return jsonify({'error': str(e)}), 500


@health_bp.route('/timeline/<camera_id>/hourly/<date>', methods=['GET'])
def get_timeline_hourly(camera_id, date):
    """
    Get detailed hourly breakdown for a specific date

    Args:
        camera_id: Camera identifier
        date: Date in YYYY-MM-DD format

    Returns:
        {
            "camera_id": "wisenet_front",
            "date": "2025-11-11",
            "hours": [...]
        }
    """
    if not _health_monitor:
        return jsonify({'error': 'Health monitor not initialized'}), 503

    try:
        if not hasattr(_health_monitor, 'recording_engine') or not _health_monitor.recording_engine:
            return jsonify({'error': 'Recording engine not initialized'}), 503

        from datetime import datetime

        # Parse date
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

        timeline_manager = _health_monitor.recording_engine.timeline_manager
        hours = timeline_manager.get_hourly_summary(camera_id, date_obj)

        return jsonify({
            'camera_id': camera_id,
            'date': date,
            'hours': hours
        }), 200

    except Exception as e:
        logger.error(f"Error getting hourly timeline for {camera_id}: {e}")
        return jsonify({'error': str(e)}), 500
