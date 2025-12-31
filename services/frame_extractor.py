"""
Frame Extractor Service

Extracts frames from HLS streams and sends them to detection service.
Runs at configurable FPS (e.g., 2 FPS for detection).
"""

import logging
import threading
import time
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class FrameExtractor:
    """
    Extracts frames from HLS streams at configurable rate.
    Sends frames to detection service for processing.
    """

    def __init__(self, hls_url: str, camera_id: str, detection_service,
                 extraction_fps: float = 2.0):
        """
        Initialize frame extractor.
        
        Args:
            hls_url: HLS stream URL (e.g., http://localhost:8888/camera_id/index.m3u8)
            camera_id: Camera identifier
            detection_service: DetectionService instance to send frames to
            extraction_fps: Frames per second to extract (e.g., 2 FPS)
        """
        self.hls_url = hls_url
        self.camera_id = camera_id
        self.detection_service = detection_service
        self.extraction_fps = extraction_fps
        self.frame_interval = 1.0 / extraction_fps  # seconds between frames
        
        self.is_running = False
        self.extraction_thread = None
        self.cap = None
        
        # Statistics
        self.frames_extracted = 0
        self.frames_sent = 0
        self.errors = 0
        
        logger.info(f"Frame extractor initialized for {camera_id} at {extraction_fps} FPS")

    def start(self):
        """Start frame extraction."""
        if self.is_running:
            logger.warning(f"Frame extractor for {self.camera_id} already running")
            return
        
        self.is_running = True
        self.extraction_thread = threading.Thread(
            target=self._extraction_loop,
            daemon=True,
            name=f"FrameExtractor-{self.camera_id}"
        )
        self.extraction_thread.start()
        logger.info(f"Frame extractor started for {self.camera_id}")

    def stop(self):
        """Stop frame extraction."""
        self.is_running = False
        if self.extraction_thread:
            self.extraction_thread.join(timeout=5)
        if self.cap:
            self.cap.release()
        logger.info(f"Frame extractor stopped for {self.camera_id}")

    def _extraction_loop(self):
        """Main extraction loop - runs in separate thread."""
        last_frame_time = time.time()
        
        while self.is_running:
            try:
                # Open HLS stream if not already open
                if self.cap is None:
                    logger.info(f"Opening HLS stream: {self.hls_url}")
                    self.cap = cv2.VideoCapture(self.hls_url)
                    if not self.cap.isOpened():
                        logger.error(f"Failed to open HLS stream: {self.hls_url}")
                        self.errors += 1
                        time.sleep(5)  # Retry after 5 seconds
                        continue
                
                # Read frame
                ret, frame = self.cap.read()
                if not ret:
                    logger.warning(f"Failed to read frame from {self.camera_id}")
                    self.cap.release()
                    self.cap = None
                    self.errors += 1
                    time.sleep(1)
                    continue
                
                self.frames_extracted += 1
                
                # Check if enough time has passed since last frame
                current_time = time.time()
                if current_time - last_frame_time >= self.frame_interval:
                    # Send frame to detection service
                    timestamp = current_time
                    self.detection_service.add_frame(self.camera_id, frame, timestamp)
                    self.frames_sent += 1
                    last_frame_time = current_time
                
            except Exception as e:
                logger.error(f"Error in frame extraction loop: {e}", exc_info=True)
                self.errors += 1
                if self.cap:
                    self.cap.release()
                    self.cap = None
                time.sleep(1)

    def get_stats(self) -> dict:
        """Get frame extractor statistics."""
        return {
            'camera_id': self.camera_id,
            'extraction_fps': self.extraction_fps,
            'frames_extracted': self.frames_extracted,
            'frames_sent': self.frames_sent,
            'errors': self.errors,
            'is_running': self.is_running
        }

