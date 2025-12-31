"""
Migration 004: Add users table for authentication

This migration creates:
1. users table - Store user accounts with hashed passwords
2. audit_logs table - Track user actions for security
3. Default admin account - Username: admin, Password: admin123
"""

import sqlite3
import logging
from datetime import datetime
import bcrypt

logger = logging.getLogger(__name__)


def migrate(db_path: str):
    """
    Create users and audit_logs tables, and create default admin account.
    
    Args:
        db_path: Path to SQLite database
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT,
                full_name TEXT,
                role TEXT NOT NULL DEFAULT 'viewer',
                is_active BOOLEAN DEFAULT 1,
                must_change_password BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                created_by INTEGER,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """)
        
        # Create indexes for users table
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_username
            ON users(username)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_role
            ON users(role)
        """)
        
        # Create audit_logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Create indexes for audit_logs table
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_user
            ON audit_logs(user_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_action
            ON audit_logs(action)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp
            ON audit_logs(timestamp)
        """)
        
        # Check if admin user already exists
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        admin_exists = cursor.fetchone()
        
        if not admin_exists:
            # Create default admin account
            # Password: admin123 (user must change on first login)
            password = "admin123"
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            cursor.execute("""
                INSERT INTO users (username, password_hash, email, full_name, role, is_active, must_change_password)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ('admin', password_hash, 'admin@aivms.local', 'System Administrator', 'admin', 1, 1))
            
            admin_id = cursor.lastrowid
            
            # Log admin account creation
            cursor.execute("""
                INSERT INTO audit_logs (user_id, username, action, details)
                VALUES (?, ?, ?, ?)
            """, (admin_id, 'admin', 'user_created', 'Default admin account created during migration'))
            
            logger.info("✅ Default admin account created (username: admin, password: admin123)")
        else:
            logger.info("ℹ️  Admin account already exists, skipping creation")
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Migration 004 complete: users and audit_logs tables created")
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration 004 failed: {e}", exc_info=True)
        return False


def rollback(db_path: str):
    """
    Rollback migration by dropping tables.
    
    Args:
        db_path: Path to SQLite database
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("DROP TABLE IF EXISTS audit_logs")
        cursor.execute("DROP TABLE IF EXISTS users")
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Rollback complete: users and audit_logs tables dropped")
        return True
        
    except Exception as e:
        logger.error(f"❌ Rollback failed: {e}", exc_info=True)
        return False

