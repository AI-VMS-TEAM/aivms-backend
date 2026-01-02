"""
Cloud Configuration
Manages all configuration for the cloud deployment.
"""

import os
import configparser
from pathlib import Path


class CloudConfig:
    """Configuration manager for cloud server."""
    
    def __init__(self, config_path='cloud_config.ini'):
        self.config = configparser.ConfigParser()
        
        # Load config file if exists
        if os.path.exists(config_path):
            self.config.read(config_path)
        
        # Server settings
        self.port = int(os.environ.get(
            'CLOUD_PORT',
            self.config.get('Server', 'port', fallback='3000')
        ))
        self.debug = os.environ.get(
            'DEBUG',
            self.config.get('Server', 'debug', fallback='false')
        ).lower() == 'true'
        self.secret_key = os.environ.get(
            'SECRET_KEY',
            self.config.get('Server', 'secret_key', fallback='change-me-in-production')
        )
        
        # Database
        self.db_path = os.environ.get(
            'DB_PATH',
            self.config.get('Database', 'path', fallback='./cloud.db')
        )
        
        # Storage
        self.clip_storage_path = os.environ.get(
            'CLIP_STORAGE_PATH',
            self.config.get('Storage', 'clips_path', fallback='./storage/clips')
        )
        self.max_clip_storage_gb = int(os.environ.get(
            'MAX_CLIP_STORAGE_GB',
            self.config.get('Storage', 'max_clip_storage_gb', fallback='100')
        ))
        self.clip_retention_days = int(os.environ.get(
            'CLIP_RETENTION_DAYS',
            self.config.get('Storage', 'clip_retention_days', fallback='30')
        ))
        
        # Authentication
        self.jwt_secret = os.environ.get(
            'JWT_SECRET',
            self.config.get('Auth', 'jwt_secret', fallback='jwt-secret-change-me')
        )
        self.jwt_expiry_hours = int(os.environ.get(
            'JWT_EXPIRY_HOURS',
            self.config.get('Auth', 'jwt_expiry_hours', fallback='24')
        ))
        
        # Alerts
        self.smtp_enabled = os.environ.get(
            'SMTP_ENABLED',
            self.config.get('Alerts', 'smtp_enabled', fallback='false')
        ).lower() == 'true'
        self.smtp_host = os.environ.get(
            'SMTP_HOST',
            self.config.get('Alerts', 'smtp_host', fallback='')
        )
        self.smtp_port = int(os.environ.get(
            'SMTP_PORT',
            self.config.get('Alerts', 'smtp_port', fallback='587')
        ))
        self.smtp_user = os.environ.get(
            'SMTP_USER',
            self.config.get('Alerts', 'smtp_user', fallback='')
        )
        self.smtp_password = os.environ.get(
            'SMTP_PASSWORD',
            self.config.get('Alerts', 'smtp_password', fallback='')
        )
        
        # Edge management
        self.edge_timeout_seconds = int(os.environ.get(
            'EDGE_TIMEOUT_SECONDS',
            self.config.get('Edge', 'timeout_seconds', fallback='60')
        ))
        self.edge_ping_interval = int(os.environ.get(
            'EDGE_PING_INTERVAL',
            self.config.get('Edge', 'ping_interval', fallback='30')
        ))
        
        # Ensure directories exist
        Path(self.clip_storage_path).mkdir(parents=True, exist_ok=True)
        Path(os.path.dirname(self.db_path)).mkdir(parents=True, exist_ok=True)
    
    def save(self, config_path='cloud_config.ini'):
        """Save current configuration to file."""
        self.config['Server'] = {
            'port': str(self.port),
            'debug': str(self.debug).lower(),
            'secret_key': self.secret_key
        }
        self.config['Database'] = {
            'path': self.db_path
        }
        self.config['Storage'] = {
            'clips_path': self.clip_storage_path,
            'max_clip_storage_gb': str(self.max_clip_storage_gb),
            'clip_retention_days': str(self.clip_retention_days)
        }
        self.config['Auth'] = {
            'jwt_secret': self.jwt_secret,
            'jwt_expiry_hours': str(self.jwt_expiry_hours)
        }
        self.config['Alerts'] = {
            'smtp_enabled': str(self.smtp_enabled).lower(),
            'smtp_host': self.smtp_host,
            'smtp_port': str(self.smtp_port),
            'smtp_user': self.smtp_user,
            'smtp_password': self.smtp_password
        }
        self.config['Edge'] = {
            'timeout_seconds': str(self.edge_timeout_seconds),
            'ping_interval': str(self.edge_ping_interval)
        }
        
        with open(config_path, 'w') as f:
            self.config.write(f)
