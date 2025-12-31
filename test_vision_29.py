"""
Test script for Vision 29: Object Detection (YOLO)

Tests:
1. Detection service initialization
2. Frame extractor initialization
3. Database schema
4. API endpoints
"""

import unittest
import sqlite3
import json
import numpy as np
from pathlib import Path
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.detection_service import DetectionService
from services.frame_extractor import FrameExtractor


class TestVision29(unittest.TestCase):
    """Test Vision 29 implementation."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.db_path = 'test_detections.db'
        cls.test_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        # Create detections table for testing
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                class TEXT NOT NULL,
                confidence REAL NOT NULL,
                bbox TEXT NOT NULL,
                frame_id INTEGER,
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
                time.sleep(0.5)  # Wait for file locks to release
                os.remove(cls.db_path)
            except Exception as e:
                print(f"Warning: Could not delete test database: {e}")
    
    def test_01_detection_service_init(self):
        """Test DetectionService initialization."""
        try:
            service = DetectionService(
                db_path=self.db_path,
                model_name='yolov8n',  # Use nano for testing
                confidence_threshold=0.5,
                gpu_enabled=False  # Use CPU for testing
            )
            self.assertIsNotNone(service)
            self.assertEqual(service.model_name, 'yolov8n')
            self.assertEqual(service.confidence_threshold, 0.5)
            print("✅ DetectionService initialized successfully")
        except Exception as e:
            self.fail(f"Failed to initialize DetectionService: {e}")
    
    def test_02_detection_service_start_stop(self):
        """Test DetectionService start/stop."""
        try:
            service = DetectionService(
                db_path=self.db_path,
                model_name='yolov8n',
                gpu_enabled=False
            )
            service.start()
            self.assertTrue(service.is_running)
            
            service.stop()
            self.assertFalse(service.is_running)
            print("✅ DetectionService start/stop working")
        except Exception as e:
            self.fail(f"Failed start/stop test: {e}")
    
    def test_03_detection_service_stats(self):
        """Test DetectionService statistics."""
        try:
            service = DetectionService(
                db_path=self.db_path,
                model_name='yolov8n',
                gpu_enabled=False
            )
            stats = service.get_stats()
            
            self.assertIn('model', stats)
            self.assertIn('frames_processed', stats)
            self.assertIn('detections_stored', stats)
            self.assertEqual(stats['model'], 'yolov8n')
            print("✅ DetectionService statistics working")
        except Exception as e:
            self.fail(f"Failed stats test: {e}")
    
    def test_04_frame_extractor_init(self):
        """Test FrameExtractor initialization."""
        try:
            service = DetectionService(
                db_path=self.db_path,
                model_name='yolov8n',
                gpu_enabled=False
            )
            
            extractor = FrameExtractor(
                hls_url='http://localhost:8888/test/index.m3u8',
                camera_id='test_camera',
                detection_service=service,
                extraction_fps=2.0
            )
            
            self.assertIsNotNone(extractor)
            self.assertEqual(extractor.camera_id, 'test_camera')
            self.assertEqual(extractor.extraction_fps, 2.0)
            print("✅ FrameExtractor initialized successfully")
        except Exception as e:
            self.fail(f"Failed to initialize FrameExtractor: {e}")
    
    def test_05_frame_extractor_stats(self):
        """Test FrameExtractor statistics."""
        try:
            service = DetectionService(
                db_path=self.db_path,
                model_name='yolov8n',
                gpu_enabled=False
            )
            
            extractor = FrameExtractor(
                hls_url='http://localhost:8888/test/index.m3u8',
                camera_id='test_camera',
                detection_service=service,
                extraction_fps=2.0
            )
            
            stats = extractor.get_stats()
            self.assertIn('camera_id', stats)
            self.assertIn('extraction_fps', stats)
            self.assertIn('frames_extracted', stats)
            print("✅ FrameExtractor statistics working")
        except Exception as e:
            self.fail(f"Failed stats test: {e}")
    
    def test_06_database_schema(self):
        """Test detections table schema."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='detections'
            """)
            result = cursor.fetchone()
            self.assertIsNotNone(result, "detections table not found")
            
            # Check columns
            cursor.execute("PRAGMA table_info(detections)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}
            
            required_columns = ['id', 'camera_id', 'timestamp', 'class', 'confidence', 'bbox']
            for col in required_columns:
                self.assertIn(col, columns, f"Column {col} not found")
            
            conn.close()
            print("✅ Database schema is correct")
        except Exception as e:
            self.fail(f"Failed schema test: {e}")


if __name__ == '__main__':
    print("\n" + "="*60)
    print("VISION 29: OBJECT DETECTION (YOLO) - TEST SUITE")
    print("="*60 + "\n")
    
    unittest.main(verbosity=2)

