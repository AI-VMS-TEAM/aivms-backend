import configparser
import os
from flask import Flask
from flask_socketio import SocketIO
from datetime import datetime, timedelta
from models.camera_manager import CameraManager
from services.recording_engine import RecordingEngine
from services.recording_index import RecordingIndex
from services.mediamtx_index_service import MediaMTXIndexService
from services.timeline_manager import TimelineManager
from services.health_monitor import HealthMonitor
from services.detection_service import DetectionService
from services.frame_extractor import FrameExtractor
from services.tracking_service import TrackingService
from services.zone_service import ZoneService
from services.detection_tracking_integration import DetectionTrackingIntegration
from controllers.main_routes import create_blueprint
from controllers.health_routes import health_bp, set_health_monitor
from controllers.playback_routes import playback_bp, set_recording_engine
from controllers.timeline_routes import timeline_bp, set_timeline_manager
from controllers.detection_routes import (
    detection_bp, set_detection_service, set_socketio,
    broadcast_detections, broadcast_zone_event, register_socketio_handlers
)
from controllers.tracking_routes import tracking_bp, set_tracking_service
from controllers.zone_routes import zone_bp, set_zone_service
from controllers.auth_routes import auth_bp, set_db_path

# --- Initialization ---
app = Flask(__name__, static_folder='public', static_url_path='')
app.config['SECRET_KEY'] = 'aivms-secret-key-change-in-production'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)  # Session timeout: 30 minutes

# Note: SocketIO will be initialized AFTER all blueprints are registered
# to avoid routing issues with Flask-SocketIO
socketio = None

config = configparser.ConfigParser()
config.read('config.ini')
NVR_IP_ADDRESS = config.get('Network', 'nvr_ip', fallback='127.0.0.1')
print(f"Using NVR IP Address from config: {NVR_IP_ADDRESS}")

# Initialize camera manager
camera_manager = CameraManager('cameras.json', 'mediamtx.yml')

# Initialize health monitor first (so recording engine can use it)
storage_path = config.get('Recording', 'storage_path', fallback='./storage/recordings')
camera_ids = [camera.get('name', '').lower().replace(' ', '_').replace('-', '_')
              for camera in camera_manager.cameras]
health_monitor = HealthMonitor(
    storage_path=storage_path,
    camera_ids=camera_ids,
    check_interval_seconds=60  # Check every 60 seconds
)
health_monitor.start()
set_health_monitor(health_monitor)

# Initialize recording index (for both custom engine and MediaMTX)
db_path = config.get('Recording', 'db_path', fallback='./recordings.db')
recording_index = RecordingIndex(db_path)

# Run authentication migration (create users table)
print("\n🔐 Setting up authentication...")
try:
    import sys
    sys.path.insert(0, 'migrations')
    import importlib
    auth_migration = importlib.import_module('004_add_users_table')
    auth_migration.migrate(db_path)
    print("✅ Authentication database ready")
except Exception as e:
    print(f"⚠️  Warning: Authentication migration failed: {e}")

# Set database path for auth routes
set_db_path(db_path)

# Initialize TimelineManager
timeline_manager = TimelineManager(recording_index)

# Build timeline on startup for all cameras (last 7 days)
try:
    start_date = datetime.now() - timedelta(days=7)
    end_date = datetime.now()
    for camera in camera_manager.cameras:
        camera_id = camera.get('name', '').lower().replace(' ', '_').replace('-', '_')
        print(f"Building timeline for {camera_id}...")
        timeline_manager.build_timeline(camera_id, start_date, end_date)
except Exception as e:
    print(f"Warning: Failed to build timeline on startup: {e}")

# Initialize Zone Service (Vision 31)
zone_service = ZoneService(config_path='config/zones.yaml')

# Initialize Tracking Service (Vision 30)
tracking_enabled = config.getboolean('Tracking', 'enabled', fallback=True)
tracking_service = TrackingService(
    db_path=db_path,
    max_distance=float(config.get('Tracking', 'max_distance', fallback='50.0')),
    use_bytetrack_ids=tracking_enabled,
    zone_service=zone_service
)

# Initialize Detection Service (Vision 29) with ByteTrack tracking and pose detection
detection_service = DetectionService(
    db_path=db_path,
    model_name=config.get('Detection', 'model', fallback='yolov8s'),
    confidence_threshold=float(config.get('Detection', 'confidence_threshold', fallback='0.5')),
    gpu_enabled=config.getboolean('Detection', 'gpu_enabled', fallback=True),
    tracking_enabled=tracking_enabled,
    tracker_config='config/bytetrack.yaml',
    pose_enabled=True,  # Enable pose detection for persons
    kalman_smoothing=True  # Enable Kalman smoothing for stable boxes
)
detection_service.start()

print(f"✅ Detection service started with {'ByteTrack tracking' if tracking_enabled else 'detection only'}")

# Initialize Detection-Tracking Integration
integration = DetectionTrackingIntegration(detection_service, tracking_service)
integration.start()

# Set detection callback to feed detections to tracking
detection_service.set_detections_callback(integration.add_detections)

# Set WebSocket callback for real-time detection streaming
detection_service.set_websocket_callback(broadcast_detections)

# Set zone event callback for real-time zone event broadcasting (Vision 31)
tracking_service.set_zone_event_callback(broadcast_zone_event)

# Initialize Frame Extractors for each camera
frame_extractors = {}
detection_fps = float(config.get('Detection', 'detection_fps', fallback='2.0'))
# Use environment variable for MediaMTX host (for Docker support)
mediamtx_host = os.environ.get('MEDIAMTX_HOST', 'localhost')
for camera in camera_manager.cameras:
    camera_id = camera.get('name', '').lower().replace(' ', '_').replace('-', '_')
    hls_url = f"http://{mediamtx_host}:8888/{camera_id}/index.m3u8"
    extractor = FrameExtractor(
        hls_url=hls_url,
        camera_id=camera_id,
        detection_service=detection_service,
        extraction_fps=detection_fps
    )
    extractor.start()
    frame_extractors[camera_id] = extractor
    print(f"Started frame extractor for {camera_id}")

# Initialize MediaMTX Index Service
# Use the same storage path as the recording engine (D:\recordings)
mediamtx_base_path = config.get('Recording', 'storage_path', fallback='D:\\recordings')
mediamtx_index_service = MediaMTXIndexService(
    mediamtx_base_path=mediamtx_base_path,
    recording_index=recording_index,
    scan_interval_seconds=30
)
mediamtx_index_service.start()

# Initialize recording engine (with health monitor for IOPS tracking)
recording_engine = RecordingEngine(
    cameras=camera_manager.cameras,
    storage_path=storage_path,
    segment_duration_ms=config.getint('Recording', 'segment_duration_ms', fallback=3000),
    retention_days=config.getint('Recording', 'retention_days', fallback=30),
    health_monitor=health_monitor
)

# Link recording engine to health monitor for recovery tracking
health_monitor.recording_engine = recording_engine

# Start recording engine
recording_engine.start()

# Register Flask routes
# Register auth blueprint FIRST (before other routes)
app.register_blueprint(auth_bp)
print(f"Registered auth blueprint: {auth_bp.name} at {auth_bp.url_prefix}")

main_routes = create_blueprint(camera_manager, NVR_IP_ADDRESS, recording_engine)
app.register_blueprint(main_routes)
print(f"Registered main routes blueprint: {main_routes.name}")

app.register_blueprint(health_bp)
print(f"Registered health blueprint: {health_bp.name} at {health_bp.url_prefix}")

# Set recording engine BEFORE registering playback blueprint
set_recording_engine(recording_engine)
app.register_blueprint(playback_bp)
print(f"Registered playback blueprint: {playback_bp.name} at {playback_bp.url_prefix}")

# Set timeline manager BEFORE registering timeline blueprint
set_timeline_manager(timeline_manager)
app.register_blueprint(timeline_bp)
print(f"Registered timeline blueprint: {timeline_bp.name} at {timeline_bp.url_prefix}")

# Set detection service BEFORE registering detection blueprint
set_detection_service(detection_service, frame_extractors, db_path)
app.register_blueprint(detection_bp)
print(f"Registered detection blueprint: {detection_bp.name} at {detection_bp.url_prefix}")

# Set tracking service BEFORE registering tracking blueprint
set_tracking_service(tracking_service, frame_extractors, db_path)
app.register_blueprint(tracking_bp)
print(f"Registered tracking blueprint: {tracking_bp.name} at {tracking_bp.url_prefix}")

# Set zone service BEFORE registering zone blueprint (Vision 31)
set_zone_service(zone_service, tracking_service, db_path)
app.register_blueprint(zone_bp)
print(f"Registered zone blueprint: {zone_bp.name} at {zone_bp.url_prefix}")

# Initialize SocketIO AFTER all blueprints are registered
# This fixes the Flask-SocketIO routing issue where blueprints registered
# before SocketIO initialization may not be properly routed
print("\n🔧 Initializing SocketIO...")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
set_socketio(socketio)  # Set SocketIO instance for WebSocket support

# Register SocketIO handlers AFTER SocketIO is initialized
register_socketio_handlers(socketio)  # Register WebSocket event handlers
print("✅ WebSocket support enabled for real-time detections at /detections namespace")

# Debug: Print all registered routes
print("\nRegistered routes:")
for rule in app.url_map.iter_rules():
    if 'health' in rule.rule or 'api' in rule.rule:
        print(f"  {rule.rule} -> {rule.endpoint}")

# Force Flask to rebuild URL map (fix for Flask-SocketIO routing issue)
app.url_map.update()
print("\n✅ URL map updated and ready")

# --- Graceful Shutdown ---
import atexit

def shutdown():
    print("Shutting down detection-tracking integration...")
    integration.stop()
    print("Shutting down tracking service...")
    tracking_service.stop()
    print("Shutting down detection service...")
    detection_service.stop()
    print("Shutting down frame extractors...")
    for extractor in frame_extractors.values():
        extractor.stop()
    print("Shutting down MediaMTX index service...")
    mediamtx_index_service.stop()
    print("Shutting down health monitor...")
    health_monitor.stop()
    print("Shutting down recording engine...")
    recording_engine.stop()
    print("Shutting down recording index...")
    recording_index.stop()

atexit.register(shutdown)

# --- Main Execution ---
if __name__ == '__main__':
    # Use socketio.run instead of app.run for WebSocket support
    socketio.run(app, host='0.0.0.0', port=3000, debug=False, allow_unsafe_werkzeug=True)