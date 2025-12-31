"""
Integration layer between Detection and Tracking services

Bridges DetectionService and TrackingService:
- Receives detections from DetectionService
- Passes them to TrackingService for tracking
- Maintains synchronized state
"""

import logging
import threading
import queue
from typing import Dict, List

logger = logging.getLogger(__name__)


class DetectionTrackingIntegration:
    """
    Integrates detection and tracking services.
    Processes detections and updates tracks in real-time.
    """
    
    def __init__(self, detection_service, tracking_service):
        """
        Initialize integration.
        
        Args:
            detection_service: DetectionService instance
            tracking_service: TrackingService instance
        """
        self.detection_service = detection_service
        self.tracking_service = tracking_service
        
        # Queue for detections from detection service
        self.detection_queue = queue.Queue(maxsize=100)
        
        # Integration thread
        self.is_running = False
        self.integration_thread = None
        
        # Statistics
        self.detections_processed = 0
        self.tracks_updated = 0
        
        logger.info("Detection-Tracking integration initialized")
    
    def start(self):
        """Start the integration service."""
        if self.is_running:
            logger.warning("Integration already running")
            return
        
        self.is_running = True
        self.integration_thread = threading.Thread(
            target=self._integration_loop,
            daemon=True,
            name="DetectionTrackingIntegrationThread"
        )
        self.integration_thread.start()
        logger.info("Detection-Tracking integration started")
    
    def stop(self):
        """Stop the integration service."""
        self.is_running = False
        if self.integration_thread:
            self.integration_thread.join(timeout=5)
        logger.info("Detection-Tracking integration stopped")
    
    def add_detections(self, camera_id: str, detections: List[dict], timestamp: float):
        """
        Add detections for tracking.
        
        Args:
            camera_id: Camera identifier
            detections: List of detection dicts
            timestamp: Frame timestamp
        """
        try:
            self.detection_queue.put_nowait((camera_id, detections, timestamp))
        except queue.Full:
            logger.debug("Detection queue full, dropping batch")
    
    def _integration_loop(self):
        """Main integration loop - runs in separate thread."""
        while self.is_running:
            try:
                # Get detections from queue
                camera_id, detections, timestamp = self.detection_queue.get(timeout=1)
                
                # Update tracking service
                self.tracking_service.update(camera_id, detections, timestamp)
                
                self.detections_processed += len(detections)
                self.tracks_updated += 1
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in integration loop: {e}", exc_info=True)
    
    def get_stats(self) -> dict:
        """Get integration statistics."""
        return {
            'detections_processed': self.detections_processed,
            'tracks_updated': self.tracks_updated,
            'queue_size': self.detection_queue.qsize(),
            'is_running': self.is_running
        }

