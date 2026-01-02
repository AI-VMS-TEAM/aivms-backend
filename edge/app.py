"""
AIVMS Edge Box Application
Runs on-premise, handles video ingestion, ML inference, and local storage.
Communicates with cloud via WebSocket for events and commands.
"""

import os
import sys
import logging
import configparser
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

# Add parent directory to path for shared imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from edge.services.cloud_connector import CloudConnector
from edge.services.event_uploader import EventUploader
from edge.config import EdgeConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, static_folder='../public', static_url_path='')
app.config['SECRET_KEY'] = os.environ.get('EDGE_SECRET_KEY', 'edge-secret-key')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Load configuration
config = EdgeConfig()

# Global services
cloud_connector = None
event_uploader = None
detection_service = None
recording_engine = None


def initialize_services():
    """Initialize all edge services."""
    global cloud_connector, event_uploader, detection_service, recording_engine
    
    logger.info("🚀 Initializing Edge Box services...")
    
    # Initialize cloud connector (WebSocket to cloud)
    cloud_connector = CloudConnector(
        cloud_url=config.cloud_url,
        edge_id=config.edge_id,
        edge_secret=config.edge_secret,
        on_command=handle_cloud_command
    )
    
    # Initialize event uploader
    event_uploader = EventUploader(
        cloud_url=config.cloud_url,
        edge_id=config.edge_id,
        edge_secret=config.edge_secret
    )
    
    # Import and initialize detection service (reuse existing)
    if config.detection_enabled:
        try:
            from services.detection_service import DetectionService
            detection_service = DetectionService(
                model_name=config.detection_model,
                confidence_threshold=config.confidence_threshold,
                target_classes=config.detection_classes,
                use_gpu=config.use_gpu
            )
            detection_service.set_detection_callback(on_detection)
            detection_service.start()
            logger.info("✅ Detection service started")
        except Exception as e:
            logger.error(f"❌ Failed to start detection service: {e}")
    
    # Import and initialize recording engine (reuse existing)
    try:
        from models.camera_manager import CameraManager
        from services.recording_engine import RecordingEngine
        from services.recording_index import RecordingIndex
        
        camera_manager = CameraManager('cameras.json', 'mediamtx.yml')
        recording_index = RecordingIndex(config.db_path)
        
        recording_engine = RecordingEngine(
            camera_manager=camera_manager,
            recording_index=recording_index,
            storage_path=config.storage_path
        )
        recording_engine.start()
        logger.info("✅ Recording engine started")
    except Exception as e:
        logger.error(f"❌ Failed to start recording engine: {e}")
    
    # Connect to cloud
    cloud_connector.connect()
    logger.info("✅ Edge Box initialization complete")


def on_detection(detection_event):
    """Callback when detection service detects objects."""
    if cloud_connector and cloud_connector.is_connected:
        # Send detection metadata to cloud
        cloud_connector.send_detection(detection_event)
        
        # Check if this detection triggers an event clip
        if should_upload_clip(detection_event):
            event_uploader.queue_clip(detection_event)


def should_upload_clip(detection_event):
    """Determine if detection warrants uploading a clip to cloud."""
    # Upload clips for: person in restricted zone, vehicle, etc.
    high_priority_classes = ['person', 'vehicle', 'truck']
    
    for detection in detection_event.get('detections', []):
        if detection.get('class_name') in high_priority_classes:
            if detection.get('confidence', 0) > 0.7:
                return True
        
        # Zone violations always trigger clips
        if detection.get('zone_violation'):
            return True
    
    return False


def handle_cloud_command(command):
    """Handle commands received from cloud."""
    cmd_type = command.get('type')
    payload = command.get('payload', {})
    
    logger.info(f"📥 Received cloud command: {cmd_type}")
    
    if cmd_type == 'start_detection':
        if detection_service:
            detection_service.start()
            return {'status': 'ok', 'message': 'Detection started'}
    
    elif cmd_type == 'stop_detection':
        if detection_service:
            detection_service.stop()
            return {'status': 'ok', 'message': 'Detection stopped'}
    
    elif cmd_type == 'update_zones':
        # Update zone configuration
        zones = payload.get('zones', [])
        # TODO: Update zone service
        return {'status': 'ok', 'message': f'Updated {len(zones)} zones'}
    
    elif cmd_type == 'request_clip':
        # Cloud requesting a specific clip
        camera_id = payload.get('camera_id')
        start_time = payload.get('start_time')
        end_time = payload.get('end_time')
        event_uploader.queue_clip_request(camera_id, start_time, end_time)
        return {'status': 'ok', 'message': 'Clip queued for upload'}
    
    elif cmd_type == 'get_status':
        return get_edge_status()
    
    elif cmd_type == 'reboot':
        # Schedule reboot
        logger.warning("🔄 Reboot requested by cloud")
        # os.system('sudo reboot')  # Uncomment for production
        return {'status': 'ok', 'message': 'Reboot scheduled'}
    
    else:
        logger.warning(f"Unknown command type: {cmd_type}")
        return {'status': 'error', 'message': f'Unknown command: {cmd_type}'}


def get_edge_status():
    """Get current edge box status."""
    import psutil
    
    return {
        'status': 'online',
        'edge_id': config.edge_id,
        'detection_enabled': detection_service is not None and detection_service.is_running,
        'recording_enabled': recording_engine is not None and recording_engine.is_running,
        'cloud_connected': cloud_connector.is_connected if cloud_connector else False,
        'system': {
            'cpu_percent': psutil.cpu_percent(),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage(config.storage_path).percent
        }
    }


# ============================================
# API Routes (Local access only)
# ============================================

@app.route('/api/status')
def api_status():
    """Edge box status endpoint."""
    return get_edge_status()


@app.route('/api/cameras')
def api_cameras():
    """List cameras connected to this edge box."""
    try:
        from models.camera_manager import CameraManager
        camera_manager = CameraManager('cameras.json', 'mediamtx.yml')
        return {'cameras': camera_manager.cameras}
    except Exception as e:
        return {'error': str(e)}, 500


@app.route('/api/detections')
def api_detections():
    """Get recent detections (local query)."""
    if detection_service:
        return {'detections': detection_service.get_recent_detections(limit=100)}
    return {'detections': []}


# ============================================
# SocketIO Events (Local dashboard)
# ============================================

@socketio.on('connect')
def handle_connect():
    logger.info("Local client connected")


@socketio.on('subscribe_detections')
def handle_subscribe():
    """Subscribe to real-time detections."""
    # Client will receive detections via 'detection' event
    pass


# ============================================
# Main Entry Point
# ============================================

def main():
    """Main entry point for edge application."""
    logger.info("=" * 60)
    logger.info("  AIVMS Edge Box Starting")
    logger.info(f"  Edge ID: {config.edge_id}")
    logger.info(f"  Cloud URL: {config.cloud_url}")
    logger.info("=" * 60)
    
    initialize_services()
    
    # Run Flask app
    socketio.run(
        app,
        host='0.0.0.0',
        port=config.edge_port,
        debug=False,
        allow_unsafe_werkzeug=True
    )


if __name__ == '__main__':
    main()
