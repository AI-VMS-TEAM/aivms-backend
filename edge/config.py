"""
Edge Box Configuration
Manages all configuration for the edge deployment.
"""

import os
import uuid
import configparser
from pathlib import Path


class EdgeConfig:
    """Configuration manager for edge box."""
    
    def __init__(self, config_path='edge_config.ini'):
        self.config = configparser.ConfigParser()
        
        # Load config file if exists
        if os.path.exists(config_path):
            self.config.read(config_path)
        
        # Edge Identity
        self.edge_id = os.environ.get(
            'EDGE_ID',
            self.config.get('Edge', 'edge_id', fallback=self._generate_edge_id())
        )
        self.edge_secret = os.environ.get(
            'EDGE_SECRET',
            self.config.get('Edge', 'edge_secret', fallback='change-me-in-production')
        )
        self.edge_name = os.environ.get(
            'EDGE_NAME',
            self.config.get('Edge', 'edge_name', fallback='Edge Box 1')
        )
        self.edge_port = int(os.environ.get(
            'EDGE_PORT',
            self.config.get('Edge', 'port', fallback='3001')
        ))
        
        # Cloud Connection
        self.cloud_url = os.environ.get(
            'CLOUD_URL',
            self.config.get('Cloud', 'url', fallback='http://localhost:3000')
        )
        self.cloud_ws_url = os.environ.get(
            'CLOUD_WS_URL',
            self.config.get('Cloud', 'ws_url', fallback='ws://localhost:3000')
        )
        self.reconnect_interval = int(os.environ.get(
            'RECONNECT_INTERVAL',
            self.config.get('Cloud', 'reconnect_interval', fallback='5')
        ))
        
        # Storage
        self.storage_path = os.environ.get(
            'STORAGE_PATH',
            self.config.get('Storage', 'path', fallback='./storage/recordings')
        )
        self.db_path = os.environ.get(
            'DB_PATH',
            self.config.get('Storage', 'db_path', fallback='./edge.db')
        )
        self.clip_retention_days = int(os.environ.get(
            'CLIP_RETENTION_DAYS',
            self.config.get('Storage', 'clip_retention_days', fallback='7')
        ))
        
        # Detection
        self.detection_enabled = os.environ.get(
            'DETECTION_ENABLED', 
            self.config.get('Detection', 'enabled', fallback='true')
        ).lower() == 'true'
        self.detection_model = os.environ.get(
            'DETECTION_MODEL',
            self.config.get('Detection', 'model', fallback='yolo11m')
        )
        self.confidence_threshold = float(os.environ.get(
            'CONFIDENCE_THRESHOLD',
            self.config.get('Detection', 'confidence_threshold', fallback='0.5')
        ))
        self.detection_fps = float(os.environ.get(
            'DETECTION_FPS',
            self.config.get('Detection', 'fps', fallback='5.0')
        ))
        self.detection_classes = os.environ.get(
            'DETECTION_CLASSES',
            self.config.get('Detection', 'classes', fallback='person,vehicle,truck')
        ).split(',')
        self.use_gpu = os.environ.get(
            'USE_GPU',
            self.config.get('Detection', 'use_gpu', fallback='true')
        ).lower() == 'true'
        
        # Event Upload
        self.upload_enabled = os.environ.get(
            'UPLOAD_ENABLED',
            self.config.get('Upload', 'enabled', fallback='true')
        ).lower() == 'true'
        self.clip_pre_seconds = int(os.environ.get(
            'CLIP_PRE_SECONDS',
            self.config.get('Upload', 'clip_pre_seconds', fallback='5')
        ))
        self.clip_post_seconds = int(os.environ.get(
            'CLIP_POST_SECONDS',
            self.config.get('Upload', 'clip_post_seconds', fallback='10')
        ))
        self.max_clip_size_mb = int(os.environ.get(
            'MAX_CLIP_SIZE_MB',
            self.config.get('Upload', 'max_clip_size_mb', fallback='50')
        ))
        
        # MediaMTX
        self.mediamtx_host = os.environ.get(
            'MEDIAMTX_HOST',
            self.config.get('MediaMTX', 'host', fallback='localhost')
        )
        self.mediamtx_hls_port = int(os.environ.get(
            'MEDIAMTX_HLS_PORT',
            self.config.get('MediaMTX', 'hls_port', fallback='8888')
        ))
        self.mediamtx_rtsp_port = int(os.environ.get(
            'MEDIAMTX_RTSP_PORT',
            self.config.get('MediaMTX', 'rtsp_port', fallback='8554')
        ))
        
        # Ensure storage directories exist
        Path(self.storage_path).mkdir(parents=True, exist_ok=True)
    
    def _generate_edge_id(self):
        """Generate a unique edge ID."""
        # Try to use machine ID for consistency across restarts
        machine_id_path = '/etc/machine-id'
        if os.path.exists(machine_id_path):
            with open(machine_id_path, 'r') as f:
                return f'edge-{f.read().strip()[:12]}'
        return f'edge-{uuid.uuid4().hex[:12]}'
    
    def save(self, config_path='edge_config.ini'):
        """Save current configuration to file."""
        self.config['Edge'] = {
            'edge_id': self.edge_id,
            'edge_secret': self.edge_secret,
            'edge_name': self.edge_name,
            'port': str(self.edge_port)
        }
        self.config['Cloud'] = {
            'url': self.cloud_url,
            'ws_url': self.cloud_ws_url,
            'reconnect_interval': str(self.reconnect_interval)
        }
        self.config['Storage'] = {
            'path': self.storage_path,
            'db_path': self.db_path,
            'clip_retention_days': str(self.clip_retention_days)
        }
        self.config['Detection'] = {
            'enabled': str(self.detection_enabled).lower(),
            'model': self.detection_model,
            'confidence_threshold': str(self.confidence_threshold),
            'fps': str(self.detection_fps),
            'classes': ','.join(self.detection_classes),
            'use_gpu': str(self.use_gpu).lower()
        }
        self.config['Upload'] = {
            'enabled': str(self.upload_enabled).lower(),
            'clip_pre_seconds': str(self.clip_pre_seconds),
            'clip_post_seconds': str(self.clip_post_seconds),
            'max_clip_size_mb': str(self.max_clip_size_mb)
        }
        self.config['MediaMTX'] = {
            'host': self.mediamtx_host,
            'hls_port': str(self.mediamtx_hls_port),
            'rtsp_port': str(self.mediamtx_rtsp_port)
        }
        
        with open(config_path, 'w') as f:
            self.config.write(f)
    
    def to_dict(self):
        """Return configuration as dictionary."""
        return {
            'edge_id': self.edge_id,
            'edge_name': self.edge_name,
            'cloud_url': self.cloud_url,
            'detection_enabled': self.detection_enabled,
            'detection_model': self.detection_model,
            'storage_path': self.storage_path
        }
