from flask import Blueprint, jsonify, request
from services.discovery_service import discover_onvif_cameras

def create_blueprint(camera_manager, stream_manager, nvr_ip):
    main_bp = Blueprint('main', __name__, static_folder='../public', static_url_path='')

    @main_bp.route('/')
    def index():
        """Serves the main setup page."""
        return main_bp.send_static_file('index.html')

    @main_bp.route('/dashboard.html')
    def dashboard():
        """Serves the dashboard page."""
        return main_bp.send_static_file('dashboard.html')

    @main_bp.route('/api/cameras')
    def get_cameras():
        """Returns the full list of cameras for the frontend."""
        camera_data = []
        for i, cam in enumerate(camera_manager.cameras):
            cam_id = i + 1
            camera_data.append({
                'id': cam_id,
                'name': cam.get('name', 'Unknown'),
                'ip': cam.get('ip', 'Unknown')
            })
        return jsonify(camera_data)

    @main_bp.route('/api/discover')
    def api_discover():
        """Triggers the ONVIF discovery service."""
        cameras = discover_onvif_cameras(nvr_ip)
        return jsonify({'cameras': cameras})

    @main_bp.route('/api/add_camera', methods=['POST'])
    def api_add_camera():
        """Handles adding a new camera."""
        camera_data, error_message = camera_manager.add_camera(request.json)
        if error_message:
            return jsonify({'status': 'error', 'message': error_message}), 400
        else:
            # Dynamically start the stream for the new camera
            new_camera_id = len(camera_manager.cameras)
            stream_manager.start_single_stream(camera_data, new_camera_id)
            return jsonify({'status': 'success', 'camera': camera_data})
            
    return main_bp