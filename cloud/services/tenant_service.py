"""
Tenant Service
Manages tenants (accounts), users, and permissions.
"""

import os
import sqlite3
import logging
import bcrypt
import secrets
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class TenantService:
    """
    Manages multi-tenant functionality.
    - Tenant (account) CRUD
    - User management
    - Edge device registration
    - Permissions
    """
    
    def __init__(self, db_path: str = './cloud.db'):
        self.db_path = db_path
        self._init_database()
        logger.info("✅ Tenant service initialized")
    
    @contextmanager
    def _get_db(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    
    def _init_database(self):
        """Initialize database schema."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            
            # Tenants table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tenants (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    plan TEXT DEFAULT 'free',
                    max_edges INTEGER DEFAULT 5,
                    max_users INTEGER DEFAULT 10,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1
                )
            ''')
            
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT DEFAULT 'viewer',
                    created_at TEXT NOT NULL,
                    last_login TEXT,
                    is_active INTEGER DEFAULT 1,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
                )
            ''')
            
            # Edge devices table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS edge_devices (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    secret_hash TEXT NOT NULL,
                    location TEXT,
                    created_at TEXT NOT NULL,
                    last_seen TEXT,
                    is_active INTEGER DEFAULT 1,
                    config TEXT,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
                )
            ''')
            
            # API keys table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    permissions TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    is_active INTEGER DEFAULT 1,
                    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
                )
            ''')
            
            logger.info("✅ Tenant database schema initialized")
    
    # ==========================================
    # Tenant Management
    # ==========================================
    
    def create_tenant(self, name: str, email: str, plan: str = 'free') -> Optional[Dict]:
        """Create a new tenant."""
        tenant_id = f"tenant_{secrets.token_hex(8)}"
        now = datetime.now().isoformat()
        
        try:
            with self._get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO tenants (id, name, email, plan, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (tenant_id, name, email, plan, now, now))
            
            logger.info(f"✅ Created tenant: {name} ({tenant_id})")
            return self.get_tenant(tenant_id)
        except sqlite3.IntegrityError:
            logger.error(f"Tenant with email {email} already exists")
            return None
    
    def get_tenant(self, tenant_id: str) -> Optional[Dict]:
        """Get tenant by ID."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tenants WHERE id = ?', (tenant_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_tenant_by_email(self, email: str) -> Optional[Dict]:
        """Get tenant by email."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tenants WHERE email = ?', (email,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def list_tenants(self, include_inactive: bool = False) -> List[Dict]:
        """List all tenants."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            if include_inactive:
                cursor.execute('SELECT * FROM tenants ORDER BY created_at DESC')
            else:
                cursor.execute('SELECT * FROM tenants WHERE is_active = 1 ORDER BY created_at DESC')
            return [dict(row) for row in cursor.fetchall()]
    
    def update_tenant(self, tenant_id: str, updates: Dict) -> bool:
        """Update tenant details."""
        allowed_fields = ['name', 'plan', 'max_edges', 'max_users', 'is_active']
        set_clauses = []
        values = []
        
        for field, value in updates.items():
            if field in allowed_fields:
                set_clauses.append(f"{field} = ?")
                values.append(value)
        
        if not set_clauses:
            return False
        
        set_clauses.append("updated_at = ?")
        values.append(datetime.now().isoformat())
        values.append(tenant_id)
        
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(f'''
                UPDATE tenants SET {', '.join(set_clauses)} WHERE id = ?
            ''', values)
            return cursor.rowcount > 0
    
    def get_tenant_count(self) -> int:
        """Get total tenant count."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM tenants WHERE is_active = 1')
            return cursor.fetchone()[0]
    
    # ==========================================
    # User Management
    # ==========================================
    
    def create_user(
        self,
        tenant_id: str,
        email: str,
        password: str,
        name: str,
        role: str = 'viewer'
    ) -> Optional[Dict]:
        """Create a new user."""
        user_id = f"user_{secrets.token_hex(8)}"
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        now = datetime.now().isoformat()
        
        try:
            with self._get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO users (id, tenant_id, email, password_hash, name, role, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, tenant_id, email, password_hash, name, role, now))
            
            logger.info(f"✅ Created user: {email} ({user_id})")
            return self.get_user(user_id)
        except sqlite3.IntegrityError:
            logger.error(f"User with email {email} already exists")
            return None
    
    def get_user(self, user_id: str) -> Optional[Dict]:
        """Get user by ID."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            if row:
                user = dict(row)
                del user['password_hash']  # Don't expose password hash
                return user
            return None
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Get user by email."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
            row = cursor.fetchone()
            if row:
                user = dict(row)
                return user  # Keep password_hash for auth
            return None
    
    def authenticate_user(self, email: str, password: str) -> Optional[Dict]:
        """Authenticate user with email/password."""
        user = self.get_user_by_email(email)
        
        if not user:
            return None
        
        if not user.get('is_active'):
            return None
        
        if bcrypt.checkpw(password.encode(), user['password_hash'].encode()):
            # Update last login
            with self._get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users SET last_login = ? WHERE id = ?
                ''', (datetime.now().isoformat(), user['id']))
            
            # Remove password hash from returned user
            del user['password_hash']
            return user
        
        return None
    
    def list_users(self, tenant_id: str) -> List[Dict]:
        """List users for a tenant."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, tenant_id, email, name, role, created_at, last_login, is_active
                FROM users WHERE tenant_id = ? ORDER BY created_at DESC
            ''', (tenant_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    # ==========================================
    # Edge Device Management
    # ==========================================
    
    def register_edge_device(
        self,
        tenant_id: str,
        name: str,
        location: str = None
    ) -> Optional[Dict]:
        """Register a new edge device and return credentials."""
        edge_id = f"edge_{secrets.token_hex(8)}"
        edge_secret = secrets.token_hex(32)  # 64 char secret
        secret_hash = bcrypt.hashpw(edge_secret.encode(), bcrypt.gensalt()).decode()
        now = datetime.now().isoformat()
        
        try:
            with self._get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO edge_devices (id, tenant_id, name, secret_hash, location, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (edge_id, tenant_id, name, secret_hash, location, now))
            
            logger.info(f"✅ Registered edge device: {name} ({edge_id})")
            
            # Return credentials (secret shown only once)
            return {
                'edge_id': edge_id,
                'edge_secret': edge_secret,  # Only returned on creation
                'name': name,
                'tenant_id': tenant_id,
                'created_at': now
            }
        except Exception as e:
            logger.error(f"Failed to register edge device: {e}")
            return None
    
    def verify_edge_device(self, edge_id: str, edge_secret: str) -> Optional[Dict]:
        """Verify edge device credentials."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM edge_devices WHERE id = ? AND is_active = 1
            ''', (edge_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            edge = dict(row)
            
            if bcrypt.checkpw(edge_secret.encode(), edge['secret_hash'].encode()):
                # Update last seen
                cursor.execute('''
                    UPDATE edge_devices SET last_seen = ? WHERE id = ?
                ''', (datetime.now().isoformat(), edge_id))
                conn.commit()
                
                return {
                    'edge_id': edge['id'],
                    'tenant_id': edge['tenant_id'],
                    'name': edge['name'],
                    'location': edge['location']
                }
            
            return None
    
    def list_edge_devices(self, tenant_id: str) -> List[Dict]:
        """List edge devices for a tenant."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, tenant_id, name, location, created_at, last_seen, is_active, config
                FROM edge_devices WHERE tenant_id = ? ORDER BY created_at DESC
            ''', (tenant_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def update_edge_device(self, edge_id: str, updates: Dict) -> bool:
        """Update edge device."""
        allowed_fields = ['name', 'location', 'is_active', 'config']
        set_clauses = []
        values = []
        
        for field, value in updates.items():
            if field in allowed_fields:
                set_clauses.append(f"{field} = ?")
                values.append(value)
        
        if not set_clauses:
            return False
        
        values.append(edge_id)
        
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(f'''
                UPDATE edge_devices SET {', '.join(set_clauses)} WHERE id = ?
            ''', values)
            return cursor.rowcount > 0
    
    def regenerate_edge_secret(self, edge_id: str) -> Optional[str]:
        """Regenerate secret for an edge device."""
        edge_secret = secrets.token_hex(32)
        secret_hash = bcrypt.hashpw(edge_secret.encode(), bcrypt.gensalt()).decode()
        
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE edge_devices SET secret_hash = ? WHERE id = ?
            ''', (secret_hash, edge_id))
            
            if cursor.rowcount > 0:
                logger.info(f"✅ Regenerated secret for edge: {edge_id}")
                return edge_secret
            return None
