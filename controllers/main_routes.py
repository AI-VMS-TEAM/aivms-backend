from flask import Blueprint, jsonify, request
from services.discovery_service import discover_onvif_cameras
from datetime import datetime
import logging
import requests

logger = logging.getLogger(__name__)

def check_camera_stream_status(camera_name):
    """
    Check if a camera's HLS stream is actually available on MediaMTX
    Returns True if stream is active, False otherwise
    """
    try:
        camera_id = camera_name.lower().replace(' ', '_').replace('-', '_')
        hls_url = f'http://localhost:8888/{camera_id}/index.m3u8'
        response = requests.get(hls_url, timeout=2)
        return response.status_code == 200
    except:
        return False

# MODIFICATION: Added recording_engine parameter
def create_blueprint(camera_manager, nvr_ip, recording_engine=None):
    main_bp = Blueprint('main', __name__, static_folder='../public', static_url_path='')

    @main_bp.route('/')
    def index():
        return main_bp.send_static_file('index.html')

    @main_bp.route('/dashboard.html')
    def dashboard():
        return main_bp.send_static_file('dashboard.html')

    @main_bp.route('/api/cameras')
    def get_cameras():
        camera_data = []
        for i, cam in enumerate(camera_manager.cameras):
            cam_id = i + 1
            camera_name = cam.get('name', 'Unknown')

            # Check if the camera's HLS stream is actually available
            is_stream_active = check_camera_stream_status(camera_name)

            camera_data.append({
                'id': cam_id,
                'name': camera_name,
                'ip': cam.get('ip', 'Unknown'),
                'port': cam.get('port', ''),
                'location': cam.get('location', ''),
                'type': cam.get('type', ''),
                'description': cam.get('description', ''),
                'active': is_stream_active,  # Use actual stream status instead of JSON field
                'metrics': cam.get('metrics', [])
            })
        return jsonify(camera_data)

    @main_bp.route('/api/discover')
    def api_discover():
        cameras = discover_onvif_cameras(nvr_ip)
        return jsonify({'cameras': cameras})

    @main_bp.route('/api/add_camera', methods=['POST'])
    def api_add_camera():
        camera_data, error_message = camera_manager.add_camera(request.json)
        if error_message:
            return jsonify({'status': 'error', 'message': error_message}), 400
        else:
            # We no longer need to start the stream here; the manager handles it
            return jsonify({'status': 'success', 'camera': camera_data})

    # ===== RECORDING API ENDPOINTS =====

    @main_bp.route('/api/recording/status')
    def recording_status():
        """Get recording status for all cameras."""
        if not recording_engine:
            return jsonify({'error': 'Recording engine not initialized'}), 503

        status = recording_engine.get_status()
        return jsonify(status)

    @main_bp.route('/api/recording/<camera_id>/status')
    def recording_camera_status(camera_id):
        """Get recording status for specific camera."""
        if not recording_engine:
            return jsonify({'error': 'Recording engine not initialized'}), 503

        status = recording_engine.get_status(camera_id)
        if not status:
            return jsonify({'error': 'Camera not found'}), 404

        return jsonify(status)

    @main_bp.route('/api/recording/<camera_id>/segments')
    def recording_segments(camera_id):
        """Get segments for a camera in time range."""
        if not recording_engine:
            return jsonify({'error': 'Recording engine not initialized'}), 503

        start_time = request.args.get('start')
        end_time = request.args.get('end')

        # Parse timestamps if provided
        if start_time:
            try:
                start_time = datetime.fromisoformat(start_time)
            except:
                return jsonify({'error': 'Invalid start_time format'}), 400

        if end_time:
            try:
                end_time = datetime.fromisoformat(end_time)
            except:
                return jsonify({'error': 'Invalid end_time format'}), 400

        segments = recording_engine.get_segments(camera_id, start_time, end_time)
        return jsonify({'segments': segments})

    @main_bp.route('/api/recording/<camera_id>/stats')
    def recording_stats(camera_id):
        """Get recording statistics for a camera."""
        if not recording_engine:
            return jsonify({'error': 'Recording engine not initialized'}), 503

        stats = recording_engine.index_db.get_camera_stats(camera_id)
        return jsonify(stats)

    @main_bp.route('/api/recording/storage/stats')
    def storage_stats():
        """Get storage usage statistics."""
        if not recording_engine:
            return jsonify({'error': 'Recording engine not initialized'}), 503

        stats = recording_engine.retention_manager.get_storage_stats()
        return jsonify(stats)

    @main_bp.route('/api/recording/storage/estimate')
    def storage_estimate():
        """Estimate storage needed for retention period."""
        if not recording_engine:
            return jsonify({'error': 'Recording engine not initialized'}), 503

        bitrate = request.args.get('bitrate', 5, type=float)
        cameras = request.args.get('cameras', len(camera_manager.cameras), type=int)

        estimate_gb = recording_engine.retention_manager.estimate_storage_needed(bitrate, cameras)
        return jsonify({'estimated_storage_gb': estimate_gb})

    @main_bp.route('/api/recording/recovery/log')
    def recovery_log():
        """Get recovery event log."""
        if not recording_engine:
            return jsonify({'error': 'Recording engine not initialized'}), 503

        camera_id = request.args.get('camera_id')
        limit = request.args.get('limit', 100, type=int)

        log = recording_engine.recovery_manager.get_recovery_log(camera_id, limit)
        return jsonify({'log': log})

    return main_bp