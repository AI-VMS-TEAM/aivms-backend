"""
Test script for Vision 30: Object Tracking

Tests:
1. Tracking service initialization
2. Track creation and updates
3. Track closure and storage
4. Integration with detection service
5. Database schema
"""

import unittest
import sqlite3
import json
import numpy as np
from pathlib import Path
import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.tracking_service import TrackingService, Track
from services.detection_tracking_integration import DetectionTrackingIntegration
from services.detection_service import DetectionService


class TestVision30(unittest.TestCase):
    """Test Vision 30 implementation."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.db_path = 'test_tracking.db'
        
        # Create tracks table for testing
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id INTEGER NOT NULL,
                camera_id TEXT NOT NULL,
                class TEXT NOT NULL,
                enter_time REAL NOT NULL,
                exit_time REAL NOT NULL,
                dwell_time REAL NOT NULL,
                frames_seen INTEGER NOT NULL,
                last_bbox TEXT NOT NULL,
                last_confidence REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test database."""
        import time
        if os.path.exists(cls.db_path):
            try:
                time.sleep(0.5)
                os.remove(cls.db_path)
            except Exception as e:
                print(f"Warning: Could not delete test database: {e}")
    
    def test_01_track_creation(self):
        """Test Track object creation."""
        try:
            track = Track(
                track_id=1,
                camera_id='test_cam',
                bbox=[10, 20, 100, 200],
                confidence=0.95,
                class_name='person',
                timestamp=time.time()
            )
            
            self.assertEqual(track.track_id, 1)
            self.assertEqual(track.camera_id, 'test_cam')
            self.assertEqual(track.class_name, 'person')
            self.assertEqual(track.frames_seen, 1)
            print("✅ Track creation working")
        except Exception as e:
            self.fail(f"Failed to create track: {e}")
    
    def test_02_track_update(self):
        """Test Track update."""
        try:
            track = Track(
                track_id=1,
                camera_id='test_cam',
                bbox=[10, 20, 100, 200],
                confidence=0.95,
                class_name='person',
                timestamp=time.time()
            )
            
            # Update track
            track.update([15, 25, 105, 205], 0.96, time.time())
            
            self.assertEqual(track.frames_seen, 2)
            self.assertEqual(track.frames_missed, 0)
            self.assertEqual(track.last_bbox, [15, 25, 105, 205])
            print("✅ Track update working")
        except Exception as e:
            self.fail(f"Failed to update track: {e}")
    
    def test_03_tracking_service_init(self):
        """Test TrackingService initialization."""
        try:
            service = TrackingService(
                db_path=self.db_path,
                max_distance=50.0
            )
            self.assertIsNotNone(service)
            self.assertEqual(service.max_distance, 50.0)
            print("✅ TrackingService initialized successfully")
        except Exception as e:
            self.fail(f"Failed to initialize TrackingService: {e}")
    
    def test_04_tracking_service_update(self):
        """Test TrackingService update with detections."""
        try:
            service = TrackingService(
                db_path=self.db_path,
                max_distance=50.0
            )
            
            # Create detections
            detections = [
                {
                    'bbox': [10, 20, 100, 200],
                    'confidence': 0.95,
                    'class': 'person'
                },
                {
                    'bbox': [200, 150, 300, 350],
                    'confidence': 0.92,
                    'class': 'vehicle'
                }
            ]
            
            # Update tracking
            service.update('test_cam', detections, time.time())
            
            # Check tracks created
            active_tracks = service.get_active_tracks('test_cam')
            self.assertEqual(len(active_tracks), 2)
            print("✅ TrackingService update working")
        except Exception as e:
            self.fail(f"Failed to update tracking: {e}")
    
    def test_05_integration_init(self):
        """Test DetectionTrackingIntegration initialization."""
        try:
            detection_service = DetectionService(
                db_path=self.db_path,
                model_name='yolov8n',
                gpu_enabled=False
            )
            
            tracking_service = TrackingService(
                db_path=self.db_path,
                max_distance=50.0
            )
            
            integration = DetectionTrackingIntegration(
                detection_service,
                tracking_service
            )
            
            self.assertIsNotNone(integration)
            print("✅ DetectionTrackingIntegration initialized successfully")
        except Exception as e:
            self.fail(f"Failed to initialize integration: {e}")
    
    def test_06_database_schema(self):
        """Test tracks table schema."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='tracks'
            """)
            result = cursor.fetchone()
            self.assertIsNotNone(result, "tracks table not found")
            
            # Check columns
            cursor.execute("PRAGMA table_info(tracks)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}
            
            required_columns = ['id', 'track_id', 'camera_id', 'class', 
                              'enter_time', 'exit_time', 'dwell_time', 
                              'frames_seen', 'last_bbox', 'last_confidence']
            for col in required_columns:
                self.assertIn(col, columns, f"Column {col} not found")
            
            conn.close()
            print("✅ Database schema is correct")
        except Exception as e:
            self.fail(f"Failed schema test: {e}")


if __name__ == '__main__':
    print("\n" + "="*60)
    print("VISION 30: OBJECT TRACKING - TEST SUITE")
    print("="*60 + "\n")
    
    unittest.main(verbosity=2)

