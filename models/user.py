"""
User model for authentication and user management
"""

import sqlite3
import bcrypt
from datetime import datetime
from typing import Optional, Dict, List
import logging

logger = logging.getLogger(__name__)


class User:
    """User model for authentication"""
    
    def __init__(self, user_id: int, username: str, email: Optional[str], 
                 full_name: Optional[str], role: str, is_active: bool,
                 must_change_password: bool, created_at: str, last_login: Optional[str]):
        self.id = user_id
        self.username = username
        self.email = email
        self.full_name = full_name
        self.role = role
        self.is_active = is_active
        self.must_change_password = must_change_password
        self.created_at = created_at
        self.last_login = last_login
    
    def to_dict(self) -> Dict:
        """Convert user to dictionary"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'role': self.role,
            'is_active': self.is_active,
            'must_change_password': self.must_change_password,
            'created_at': self.created_at,
            'last_login': self.last_login
        }
    
    @staticmethod
    def get_by_id(db_path: str, user_id: int) -> Optional['User']:
        """Get user by ID"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, username, email, full_name, role, is_active, 
                       must_change_password, created_at, last_login
                FROM users WHERE id = ?
            """, (user_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return User(*row)
            return None
            
        except Exception as e:
            logger.error(f"Error getting user by ID {user_id}: {e}")
            return None
    
    @staticmethod
    def get_by_username(db_path: str, username: str) -> Optional['User']:
        """Get user by username"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, username, email, full_name, role, is_active, 
                       must_change_password, created_at, last_login
                FROM users WHERE username = ?
            """, (username,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return User(*row)
            return None
            
        except Exception as e:
            logger.error(f"Error getting user by username {username}: {e}")
            return None
    
    @staticmethod
    def verify_password(db_path: str, username: str, password: str) -> Optional['User']:
        """Verify username and password, return User if valid"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, username, email, full_name, role, is_active, 
                       must_change_password, created_at, last_login, password_hash
                FROM users WHERE username = ?
            """, (username,))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
            
            # Extract password hash (last column)
            password_hash = row[9]
            user_data = row[:9]
            
            # Verify password
            if bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
                return User(*user_data)
            
            return None
            
        except Exception as e:
            logger.error(f"Error verifying password for {username}: {e}")
            return None
    
    @staticmethod
    def update_last_login(db_path: str, user_id: int):
        """Update user's last login timestamp"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE users SET last_login = ? WHERE id = ?
            """, (datetime.now().isoformat(), user_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error updating last login for user {user_id}: {e}")
    
    @staticmethod
    def get_all(db_path: str) -> List['User']:
        """Get all users"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, username, email, full_name, role, is_active, 
                       must_change_password, created_at, last_login
                FROM users ORDER BY created_at DESC
            """)
            
            rows = cursor.fetchall()
            conn.close()
            
            return [User(*row) for row in rows]
            
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []

