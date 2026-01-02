"""
Cloud Connector Service
Maintains WebSocket connection to cloud server.
Sends detections, receives commands.
"""

import json
import time
import logging
import threading
from datetime import datetime
from typing import Callable, Optional, Dict, Any

import socketio

logger = logging.getLogger(__name__)


class CloudConnector:
    """
    Manages persistent WebSocket connection to cloud server.
    Handles reconnection, authentication, and message passing.
    """
    
    def __init__(
        self,
        cloud_url: str,
        edge_id: str,
        edge_secret: str,
        on_command: Optional[Callable[[Dict], Any]] = None,
        reconnect_interval: int = 5
    ):
        self.cloud_url = cloud_url
        self.edge_id = edge_id
        self.edge_secret = edge_secret
        self.on_command = on_command
        self.reconnect_interval = reconnect_interval
        
        self.sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=0,  # Infinite
            reconnection_delay=reconnect_interval,
            logger=False
        )
        
        self.is_connected = False
        self.is_authenticated = False
        self._stop_event = threading.Event()
        self._reconnect_thread = None
        self._pending_messages = []
        self._message_lock = threading.Lock()
        
        # Statistics
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'reconnections': 0,
            'last_connected': None,
            'last_disconnected': None
        }
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Set up SocketIO event handlers."""
        
        @self.sio.event
        def connect():
            logger.info("✅ Connected to cloud server")
            self.is_connected = True
            self.stats['last_connected'] = datetime.now().isoformat()
            self._authenticate()
        
        @self.sio.event
        def disconnect():
            logger.warning("❌ Disconnected from cloud server")
            self.is_connected = False
            self.is_authenticated = False
            self.stats['last_disconnected'] = datetime.now().isoformat()
        
        @self.sio.event
        def connect_error(error):
            logger.error(f"Connection error: {error}")
            self.is_connected = False
        
        @self.sio.on('authenticated')
        def on_authenticated(data):
            if data.get('success'):
                logger.info(f"✅ Authenticated with cloud as {self.edge_id}")
                self.is_authenticated = True
                self._flush_pending_messages()
            else:
                logger.error(f"❌ Authentication failed: {data.get('error')}")
                self.is_authenticated = False
        
        @self.sio.on('command')
        def on_command(data):
            """Handle command from cloud."""
            logger.info(f"📥 Command received: {data.get('type')}")
            self.stats['messages_received'] += 1
            
            if self.on_command:
                try:
                    response = self.on_command(data)
                    # Send response back to cloud
                    self.sio.emit('command_response', {
                        'command_id': data.get('command_id'),
                        'response': response
                    })
                except Exception as e:
                    logger.error(f"Error handling command: {e}")
                    self.sio.emit('command_response', {
                        'command_id': data.get('command_id'),
                        'error': str(e)
                    })
        
        @self.sio.on('ping')
        def on_ping():
            """Respond to keep-alive ping."""
            self.sio.emit('pong', {'timestamp': time.time()})
    
    def _authenticate(self):
        """Authenticate with cloud server."""
        logger.info("🔐 Authenticating with cloud...")
        self.sio.emit('authenticate', {
            'edge_id': self.edge_id,
            'edge_secret': self.edge_secret,
            'timestamp': datetime.now().isoformat()
        })
    
    def connect(self):
        """Connect to cloud server."""
        if self.is_connected:
            return
        
        def connect_worker():
            while not self._stop_event.is_set():
                try:
                    if not self.is_connected:
                        logger.info(f"🔌 Connecting to cloud: {self.cloud_url}")
                        self.sio.connect(
                            self.cloud_url,
                            namespaces=['/edge'],
                            transports=['websocket']
                        )
                        self.sio.wait()
                except Exception as e:
                    logger.error(f"Connection failed: {e}")
                    self.stats['reconnections'] += 1
                
                if not self._stop_event.is_set():
                    time.sleep(self.reconnect_interval)
        
        self._reconnect_thread = threading.Thread(target=connect_worker, daemon=True)
        self._reconnect_thread.start()
    
    def disconnect(self):
        """Disconnect from cloud server."""
        self._stop_event.set()
        if self.sio.connected:
            self.sio.disconnect()
        self.is_connected = False
        self.is_authenticated = False
    
    def send_detection(self, detection_event: Dict):
        """Send detection event to cloud."""
        message = {
            'type': 'detection',
            'edge_id': self.edge_id,
            'timestamp': datetime.now().isoformat(),
            'data': detection_event
        }
        self._send_message('detection', message)
    
    def send_alert(self, alert_data: Dict):
        """Send alert to cloud."""
        message = {
            'type': 'alert',
            'edge_id': self.edge_id,
            'timestamp': datetime.now().isoformat(),
            'data': alert_data
        }
        self._send_message('alert', message)
    
    def send_status(self, status_data: Dict):
        """Send status update to cloud."""
        message = {
            'type': 'status',
            'edge_id': self.edge_id,
            'timestamp': datetime.now().isoformat(),
            'data': status_data
        }
        self._send_message('status', message)
    
    def send_zone_event(self, zone_event: Dict):
        """Send zone event (enter/exit/dwell) to cloud."""
        message = {
            'type': 'zone_event',
            'edge_id': self.edge_id,
            'timestamp': datetime.now().isoformat(),
            'data': zone_event
        }
        self._send_message('zone_event', message)
    
    def _send_message(self, event: str, message: Dict):
        """Send message to cloud, queue if not connected."""
        if self.is_connected and self.is_authenticated:
            try:
                self.sio.emit(event, message, namespace='/edge')
                self.stats['messages_sent'] += 1
            except Exception as e:
                logger.error(f"Failed to send message: {e}")
                self._queue_message(event, message)
        else:
            self._queue_message(event, message)
    
    def _queue_message(self, event: str, message: Dict):
        """Queue message for later delivery."""
        with self._message_lock:
            # Limit queue size to prevent memory issues
            if len(self._pending_messages) < 1000:
                self._pending_messages.append((event, message))
            else:
                # Drop oldest messages
                self._pending_messages.pop(0)
                self._pending_messages.append((event, message))
    
    def _flush_pending_messages(self):
        """Send all queued messages."""
        with self._message_lock:
            pending = self._pending_messages.copy()
            self._pending_messages.clear()
        
        logger.info(f"📤 Flushing {len(pending)} pending messages")
        for event, message in pending:
            try:
                self.sio.emit(event, message, namespace='/edge')
                self.stats['messages_sent'] += 1
            except Exception as e:
                logger.error(f"Failed to flush message: {e}")
    
    def get_stats(self) -> Dict:
        """Get connection statistics."""
        return {
            **self.stats,
            'is_connected': self.is_connected,
            'is_authenticated': self.is_authenticated,
            'pending_messages': len(self._pending_messages)
        }
