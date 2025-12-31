"""
Smooth Tracking Service with Kalman Filtering

Wraps ByteTrack detections with Kalman smoothing for stable bounding boxes.
"""

import logging
from services.kalman_tracker import KalmanBoxTracker

logger = logging.getLogger(__name__)


class SmoothTracker:
    """
    Manages Kalman filters for all tracked objects.
    Smooths bounding boxes to eliminate flickering.
    """
    
    def __init__(self, max_age=30):
        """
        Initialize smooth tracker.
        
        Args:
            max_age: Maximum frames to keep Kalman filter without update
        """
        self.max_age = max_age
        self.trackers = {}  # track_id -> KalmanBoxTracker
        
    def update(self, detections):
        """
        Update Kalman filters with new detections.
        
        Args:
            detections: List of detection dicts with 'track_id' and 'bbox'
        
        Returns:
            smoothed_detections: List of detections with smoothed bboxes
        """
        # Get current track IDs
        current_track_ids = set()
        
        smoothed_detections = []
        
        for det in detections:
            track_id = det.get('track_id')
            if track_id is None:
                # No track ID, pass through unchanged
                smoothed_detections.append(det)
                continue
            
            current_track_ids.add(track_id)
            bbox = det['bbox']  # [x1, y1, x2, y2]
            
            # Create or update Kalman filter for this track
            if track_id not in self.trackers:
                # New track - initialize Kalman filter
                self.trackers[track_id] = KalmanBoxTracker(bbox)
                logger.debug(f"Created Kalman filter for track {track_id}")
            else:
                # Existing track - predict then update
                self.trackers[track_id].predict()
            
            # Update with measurement
            self.trackers[track_id].update(bbox)
            
            # Get smoothed bbox
            smoothed_bbox = self.trackers[track_id].get_bbox()
            
            # Create smoothed detection
            smoothed_det = det.copy()
            smoothed_det['bbox'] = smoothed_bbox
            smoothed_det['bbox_smoothed'] = True
            
            smoothed_detections.append(smoothed_det)
        
        # Remove old trackers
        self._cleanup_old_trackers(current_track_ids)
        
        return smoothed_detections
    
    def _cleanup_old_trackers(self, current_track_ids):
        """Remove Kalman filters for tracks that haven't been seen."""
        to_remove = []
        
        for track_id, tracker in self.trackers.items():
            if track_id not in current_track_ids:
                tracker.time_since_update += 1
                
                if tracker.time_since_update > self.max_age:
                    to_remove.append(track_id)
        
        for track_id in to_remove:
            del self.trackers[track_id]
            logger.debug(f"Removed Kalman filter for track {track_id}")
    
    def predict_all(self):
        """
        Predict positions for all tracks (for frames without detections).
        
        Returns:
            predictions: List of predicted bboxes with track_ids
        """
        predictions = []
        
        for track_id, tracker in self.trackers.items():
            predicted_bbox = tracker.predict()
            predictions.append({
                'track_id': track_id,
                'bbox': predicted_bbox,
                'predicted': True
            })
        
        return predictions
    
    def reset(self):
        """Reset all Kalman filters."""
        self.trackers.clear()
        logger.info("Reset all Kalman filters")

