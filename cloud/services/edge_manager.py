"""
Edge Manager Service
Manages connections from edge boxes.
"""

import time
import logging
import threading
from datetime import datetime
from typing import Dict, Optional, Callable
from flask import request
from flask_socketio import SocketIO, emit

logger = logging.getLogger(__name__)


class EdgeConnection:
    """Represents a connected edge box."""
    
    def __init__(self, edge_id: str, sid: str, tenant_id: str):
        self.edge_id = edge_id
        self.sid = sid
        self.tenant_id = tenant_id
        self.connected_at = datetime.now()
        self.last_seen = datetime.now()
        self.last_status = {}
        self.detection_count = 0
        self.alert_count = 0


class EdgeManager:
    """
    Manages edge box WebSocket connections.
    - Authenticates edge devices
    - Routes events to appropriate services
    - Sends commands to edge devices
    - Monitors edge health
    """
    
    def __init__(
        self,
        socketio: SocketIO,
        tenant_service,
        event_service,
        alert_service,
        ping_interval: int = 30,
        timeout_seconds: int = 60
    ):
        self.socketio = socketio
        self.tenant_service = tenant_service
        self.event_service = event_service
        self.alert_service = alert_service
        self.ping_interval = ping_interval
        self.timeout_seconds = timeout_seconds
        
        # Connected edges: sid -> EdgeConnection
        self.connections: Dict[str, EdgeConnection] = {}
        # Edge ID to SID mapping
        self.edge_to_sid: Dict[str, str] = {}
        
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        
        # Start health check thread
        self._health_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True
        )
        self._health_thread.start()
        
        logger.info("✅ Edge manager initialized")
    
    def authenticate_edge(self, data: Dict) -> Dict:
        """Authenticate an edge device."""
        edge_id = data.get('edge_id')
        edge_secret = data.get('edge_secret')
        
        if not edge_id or not edge_secret:
            logger.warning("Edge authentication failed: missing credentials")
            emit('authenticated', {'success': False, 'error': 'Missing credentials'})
            return {'success': False}
        
        # Verify edge device with tenant service
        edge_info = self.tenant_service.verify_edge_device(edge_id, edge_secret)
        
        if not edge_info:
            logger.warning(f"Edge authentication failed: invalid credentials for {edge_id}")
            emit('authenticated', {'success': False, 'error': 'Invalid credentials'})
            return {'success': False}
        
        # Register connection
        sid = request.sid
        tenant_id = edge_info['tenant_id']
        
        with self._lock:
            # Remove old connection if exists
            if edge_id in self.edge_to_sid:
                old_sid = self.edge_to_sid[edge_id]
                if old_sid in self.connections:
                    del self.connections[old_sid]
            
            # Create new connection
            connection = EdgeConnection(edge_id, sid, tenant_id)
            self.connections[sid] = connection
            self.edge_to_sid[edge_id] = sid
        
        logger.info(f"✅ Edge authenticated: {edge_id} (tenant: {tenant_id})")
        
        emit('authenticated', {
            'success': True,
            'edge_id': edge_id,
            'tenant_id': tenant_id
        })
        
        # Notify tenant dashboard of edge connection
        self.socketio.emit(
            'edge_connected',
            {'edge_id': edge_id, 'timestamp': datetime.now().isoformat()},
            room=f'tenant_{tenant_id}'
        )
        
        return {'success': True}
    
    def handle_disconnect(self):
        """Handle edge disconnection."""
        sid = request.sid
        
        with self._lock:
            if sid in self.connections:
                connection = self.connections[sid]
                edge_id = connection.edge_id
                tenant_id = connection.tenant_id
                
                del self.connections[sid]
                if edge_id in self.edge_to_sid:
                    del self.edge_to_sid[edge_id]
                
                logger.warning(f"❌ Edge disconnected: {edge_id}")
                
                # Notify tenant dashboard
                self.socketio.emit(
                    'edge_disconnected',
                    {'edge_id': edge_id, 'timestamp': datetime.now().isoformat()},
                    room=f'tenant_{tenant_id}'
                )
    
    def handle_detection(self, data: Dict):
        """Handle detection event from edge."""
        sid = request.sid
        
        with self._lock:
            if sid not in self.connections:
                logger.warning("Detection from unauthenticated edge")
                return
            
            connection = self.connections[sid]
            connection.last_seen = datetime.now()
            connection.detection_count += 1
        
        edge_id = data.get('edge_id')
        detection_data = data.get('data', {})
        
        # Store detection in event service
        self.event_service.store_detection(
            edge_id=edge_id,
            tenant_id=connection.tenant_id,
            detection=detection_data
        )
        
        # Forward to tenant dashboard in real-time
        self.socketio.emit(
            'detection',
            {
                'edge_id': edge_id,
                'detection': detection_data,
                'timestamp': data.get('timestamp')
            },
            room=f'tenant_{connection.tenant_id}'
        )
        
        # Check if alert should be triggered
        self.alert_service.process_detection(
            edge_id=edge_id,
            tenant_id=connection.tenant_id,
            detection=detection_data
        )
    
    def handle_alert(self, data: Dict):
        """Handle alert from edge."""
        sid = request.sid
        
        with self._lock:
            if sid not in self.connections:
                return
            
            connection = self.connections[sid]
            connection.last_seen = datetime.now()
            connection.alert_count += 1
        
        edge_id = data.get('edge_id')
        alert_data = data.get('data', {})
        
        # Process alert
        self.alert_service.process_alert(
            edge_id=edge_id,
            tenant_id=connection.tenant_id,
            alert=alert_data
        )
        
        # Forward to tenant dashboard
        self.socketio.emit(
            'alert',
            {
                'edge_id': edge_id,
                'alert': alert_data,
                'timestamp': data.get('timestamp')
            },
            room=f'tenant_{connection.tenant_id}'
        )
    
    def handle_status(self, data: Dict):
        """Handle status update from edge."""
        sid = request.sid
        
        with self._lock:
            if sid not in self.connections:
                return
            
            connection = self.connections[sid]
            connection.last_seen = datetime.now()
            connection.last_status = data.get('data', {})
        
        # Forward to tenant dashboard
        self.socketio.emit(
            'edge_status',
            {
                'edge_id': data.get('edge_id'),
                'status': data.get('data'),
                'timestamp': data.get('timestamp')
            },
            room=f'tenant_{connection.tenant_id}'
        )
    
    def handle_zone_event(self, data: Dict):
        """Handle zone event from edge."""
        sid = request.sid
        
        with self._lock:
            if sid not in self.connections:
                return
            
            connection = self.connections[sid]
            connection.last_seen = datetime.now()
        
        edge_id = data.get('edge_id')
        zone_data = data.get('data', {})
        
        # Store zone event
        self.event_service.store_zone_event(
            edge_id=edge_id,
            tenant_id=connection.tenant_id,
            zone_event=zone_data
        )
        
        # Forward to tenant dashboard
        self.socketio.emit(
            'zone_event',
            {
                'edge_id': edge_id,
                'zone_event': zone_data,
                'timestamp': data.get('timestamp')
            },
            room=f'tenant_{connection.tenant_id}'
        )
        
        # Check if zone event triggers alert
        self.alert_service.process_zone_event(
            edge_id=edge_id,
            tenant_id=connection.tenant_id,
            zone_event=zone_data
        )
    
    def handle_pong(self, data: Dict):
        """Handle pong response from edge."""
        sid = request.sid
        
        with self._lock:
            if sid in self.connections:
                self.connections[sid].last_seen = datetime.now()
    
    def send_command(self, edge_id: str, command: Dict) -> bool:
        """Send command to an edge device."""
        with self._lock:
            if edge_id not in self.edge_to_sid:
                logger.warning(f"Cannot send command: edge {edge_id} not connected")
                return False
            
            sid = self.edge_to_sid[edge_id]
        
        self.socketio.emit('command', command, room=sid, namespace='/edge')
        logger.info(f"📤 Sent command to {edge_id}: {command.get('type')}")
        return True
    
    def get_connected_edges(self, tenant_id: Optional[str] = None) -> list:
        """Get list of connected edges."""
        with self._lock:
            edges = []
            for sid, conn in self.connections.items():
                if tenant_id is None or conn.tenant_id == tenant_id:
                    edges.append({
                        'edge_id': conn.edge_id,
                        'tenant_id': conn.tenant_id,
                        'connected_at': conn.connected_at.isoformat(),
                        'last_seen': conn.last_seen.isoformat(),
                        'detection_count': conn.detection_count,
                        'alert_count': conn.alert_count,
                        'status': conn.last_status
                    })
            return edges
    
    def get_connected_count(self) -> int:
        """Get number of connected edges."""
        with self._lock:
            return len(self.connections)
    
    def is_edge_connected(self, edge_id: str) -> bool:
        """Check if an edge is connected."""
        with self._lock:
            return edge_id in self.edge_to_sid
    
    def _health_check_loop(self):
        """Periodically ping edges and remove stale connections."""
        while not self._stop_event.is_set():
            time.sleep(self.ping_interval)
            
            now = datetime.now()
            stale_sids = []
            
            with self._lock:
                for sid, conn in self.connections.items():
                    # Check for stale connections
                    elapsed = (now - conn.last_seen).total_seconds()
                    if elapsed > self.timeout_seconds:
                        stale_sids.append(sid)
                    else:
                        # Send ping
                        self.socketio.emit('ping', room=sid, namespace='/edge')
            
            # Remove stale connections
            for sid in stale_sids:
                with self._lock:
                    if sid in self.connections:
                        conn = self.connections[sid]
                        logger.warning(f"⚠️ Edge {conn.edge_id} timed out, removing")
                        
                        # Notify tenant
                        self.socketio.emit(
                            'edge_timeout',
                            {'edge_id': conn.edge_id},
                            room=f'tenant_{conn.tenant_id}'
                        )
                        
                        del self.connections[sid]
                        if conn.edge_id in self.edge_to_sid:
                            del self.edge_to_sid[conn.edge_id]
    
    def stop(self):
        """Stop the edge manager."""
        self._stop_event.set()
        self._health_thread.join(timeout=5)
