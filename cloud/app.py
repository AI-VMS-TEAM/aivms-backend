"""
AIVMS Cloud Application
Manages tenants, users, receives events from edge boxes.
"""

import os
import logging
from datetime import timedelta
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

from config import CloudConfig
from services.edge_manager import EdgeManager
from services.tenant_service import TenantService
from services.event_service import EventService
from services.alert_service import AlertService
from controllers.edge_routes import edge_bp, set_edge_manager
from controllers.tenant_routes import tenant_bp, set_tenant_service
from controllers.event_routes import event_bp, set_event_service
from controllers.auth_routes import auth_bp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app with static folder for web UI
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SECRET_KEY'] = os.environ.get('CLOUD_SECRET_KEY', 'cloud-secret-key-change-me')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
CORS(app)

# Initialize SocketIO for edge connections
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Load configuration
config = CloudConfig()

# Global services
edge_manager = None
tenant_service = None
event_service = None
alert_service = None


def initialize_services():
    """Initialize all cloud services."""
    global edge_manager, tenant_service, event_service, alert_service
    
    logger.info("🚀 Initializing Cloud services...")
    
    # Initialize tenant service
    tenant_service = TenantService(db_path=config.db_path)
    set_tenant_service(tenant_service)
    app.config['tenant_service'] = tenant_service
    logger.info("✅ Tenant service initialized")
    
    # Initialize event service
    event_service = EventService(db_path=config.db_path)
    set_event_service(event_service)
    app.config['event_service'] = event_service
    logger.info("✅ Event service initialized")
    
    # Initialize alert service
    alert_service = AlertService(
        db_path=config.db_path,
        event_service=event_service
    )
    app.config['alert_service'] = alert_service
    logger.info("✅ Alert service initialized")
    
    # Initialize edge manager (handles edge box connections)
    edge_manager = EdgeManager(
        socketio=socketio,
        tenant_service=tenant_service,
        event_service=event_service,
        alert_service=alert_service
    )
    set_edge_manager(edge_manager)
    app.config['edge_manager'] = edge_manager
    logger.info("✅ Edge manager initialized")
    
    logger.info("✅ Cloud initialization complete")


# Initialize services at module load (for gunicorn)
initialize_services()


# Register blueprints
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(tenant_bp, url_prefix='/api/tenants')
app.register_blueprint(edge_bp, url_prefix='/api/edge')
app.register_blueprint(event_bp, url_prefix='/api/events')


# ============================================
# SocketIO Events (Edge connections)
# ============================================

@socketio.on('connect', namespace='/edge')
def handle_edge_connect():
    """Handle edge box connection."""
    logger.info("Edge device connecting...")


@socketio.on('disconnect', namespace='/edge')
def handle_edge_disconnect():
    """Handle edge box disconnection."""
    if edge_manager:
        edge_manager.handle_disconnect()


@socketio.on('authenticate', namespace='/edge')
def handle_edge_auth(data):
    """Handle edge box authentication."""
    if edge_manager:
        return edge_manager.authenticate_edge(data)


@socketio.on('detection', namespace='/edge')
def handle_detection(data):
    """Handle detection event from edge."""
    if edge_manager:
        edge_manager.handle_detection(data)


@socketio.on('alert', namespace='/edge')
def handle_alert(data):
    """Handle alert from edge."""
    if edge_manager:
        edge_manager.handle_alert(data)


@socketio.on('status', namespace='/edge')
def handle_status(data):
    """Handle status update from edge."""
    if edge_manager:
        edge_manager.handle_status(data)


@socketio.on('zone_event', namespace='/edge')
def handle_zone_event(data):
    """Handle zone event from edge."""
    if edge_manager:
        edge_manager.handle_zone_event(data)


@socketio.on('pong', namespace='/edge')
def handle_pong(data):
    """Handle pong response from edge."""
    if edge_manager:
        edge_manager.handle_pong(data)


# ============================================
# SocketIO Events (Dashboard clients)
# ============================================

@socketio.on('connect')
def handle_client_connect():
    """Handle dashboard client connection."""
    logger.info("Dashboard client connected")


@socketio.on('subscribe_events')
def handle_subscribe_events(data):
    """Subscribe client to real-time events."""
    tenant_id = data.get('tenant_id')
    # Add to room for tenant-specific events
    from flask_socketio import join_room
    join_room(f'tenant_{tenant_id}')


# ============================================
# Health Check
# ============================================

@app.route('/health')
@app.route('/api/health')
def health_check():
    """Cloud health check endpoint."""
    return {
        'status': 'healthy',
        'service': 'aivms-cloud',
        'edge_connections': edge_manager.get_connected_count() if edge_manager else 0,
        'tenants': tenant_service.get_tenant_count() if tenant_service else 0
    }


@app.route('/')
def index():
    """Serve dashboard."""
    return app.send_static_file('index.html')


# ============================================
# Main Entry Point
# ============================================

def main():
    """Main entry point for cloud application."""
    logger.info("=" * 60)
    logger.info("  AIVMS Cloud Server Starting")
    logger.info(f"  Port: {config.port}")
    logger.info(f"  Database: {config.db_path}")
    logger.info("=" * 60)
    
    # Services already initialized at module load
    
    # Run with eventlet for better WebSocket performance
    socketio.run(
        app,
        host='0.0.0.0',
        port=config.port,
        debug=config.debug
    )


if __name__ == '__main__':
    main()
