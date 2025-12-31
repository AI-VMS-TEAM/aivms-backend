"""
Object Tracking Service using ByteTrack

Maintains persistent track IDs for detected objects.
Tracks enter_time, last_seen_time, dwell_time for each object.
Handles occlusions and ID switches.
Integrates with Zone Service for zone-based tracking (Vision 31).
"""

import logging
import threading
import time
import queue
import sqlite3
import json
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class Track:
    """Represents a tracked object."""
    
    def __init__(self, track_id: int, camera_id: str, bbox: List[float], 
                 confidence: float, class_name: str, timestamp: float):
        self.track_id = track_id
        self.camera_id = camera_id
        self.class_name = class_name
        self.enter_time = timestamp
        self.last_seen_time = timestamp
        self.last_bbox = bbox
        self.last_confidence = confidence
        self.frames_seen = 1
        self.frames_missed = 0
        self.max_age = 30  # Max frames to keep track without detection
        
    def update(self, bbox: List[float], confidence: float, timestamp: float):
        """Update track with new detection."""
        self.last_bbox = bbox
        self.last_confidence = confidence
        self.last_seen_time = timestamp
        self.frames_seen += 1
        self.frames_missed = 0
        
    def mark_missed(self):
        """Mark frame as missed (no detection)."""
        self.frames_missed += 1
        
    def is_dead(self) -> bool:
        """Check if track should be terminated."""
        return self.frames_missed > self.max_age
    
    def get_dwell_time(self, current_time: float) -> float:
        """Get dwell time in seconds."""
        return current_time - self.enter_time
    
    def to_dict(self) -> dict:
        """Convert track to dictionary."""
        return {
            'track_id': self.track_id,
            'camera_id': self.camera_id,
            'class': self.class_name,
            'enter_time': self.enter_time,
            'last_seen_time': self.last_seen_time,
            'dwell_time': self.get_dwell_time(self.last_seen_time),
            'bbox': self.last_bbox,
            'confidence': self.last_confidence,
            'frames_seen': self.frames_seen
        }


class TrackingService:
    """
    Maintains persistent object tracking across frames.
    Uses ByteTrack for motion-based tracking with IoU matching.
    """

    def __init__(self, db_path: str, max_distance: float = 50.0, use_bytetrack_ids: bool = True,
                 zone_service=None):
        """
        Initialize tracking service.

        Args:
            db_path: Path to SQLite database
            max_distance: Max distance for centroid matching (pixels) - legacy parameter
            use_bytetrack_ids: Whether to use ByteTrack IDs from detection service
            zone_service: Optional ZoneService instance for zone-based tracking (Vision 31)
        """
        self.db_path = db_path
        self.max_distance = max_distance
        self.use_bytetrack_ids = use_bytetrack_ids
        self.zone_service = zone_service
        self.zone_event_callback = None  # Callback for zone events (Vision 31)

        # Active tracks per camera
        self.tracks: Dict[str, Dict[int, Track]] = defaultdict(dict)
        self.next_track_id: Dict[str, int] = defaultdict(int)

        # Track ID mapping for ID switch detection
        # Maps (camera_id, bbox_hash) -> track_id to detect when same bbox gets new ID
        self.bbox_to_track: Dict[str, Dict[str, int]] = defaultdict(dict)

        # Statistics
        self.total_tracks_created = 0
        self.total_tracks_closed = 0
        self.id_switches = 0
        self.total_detections = 0

        mode = "ByteTrack" if use_bytetrack_ids else "Centroid"
        zone_mode = " with Zone Tracking" if zone_service else ""
        logger.info(f"Tracking service initialized with {mode} tracking{zone_mode}")

    def set_zone_event_callback(self, callback):
        """Set callback for zone events (Vision 31)."""
        self.zone_event_callback = callback
    
    def update(self, camera_id: str, detections: List[dict], timestamp: float):
        """
        Update tracks with new detections.

        Args:
            camera_id: Camera identifier
            detections: List of detection dicts with bbox, confidence, class, and optionally track_id
            timestamp: Frame timestamp
        """
        if camera_id not in self.tracks:
            self.tracks[camera_id] = {}

        self.total_detections += len(detections)

        # Check if detections have ByteTrack IDs
        has_track_ids = self.use_bytetrack_ids and len(detections) > 0 and 'track_id' in detections[0]

        if has_track_ids:
            # Use ByteTrack IDs from detection service
            self._update_with_bytetrack_ids(camera_id, detections, timestamp)
        else:
            # Fall back to centroid-based tracking
            self._update_with_centroid_matching(camera_id, detections, timestamp)

    def _update_with_bytetrack_ids(self, camera_id: str, detections: List[dict], timestamp: float):
        """
        Update tracks using ByteTrack IDs from detection service.

        Args:
            camera_id: Camera identifier
            detections: List of detection dicts with track_id
            timestamp: Frame timestamp
        """
        active_track_ids = set()

        for detection in detections:
            track_id = detection['track_id']
            active_track_ids.add(track_id)

            # Use bbox_xywh if available, otherwise convert from bbox
            if 'bbox_xywh' in detection:
                bbox = detection['bbox_xywh']
            else:
                # Convert [x1, y1, x2, y2] to [x_center, y_center, width, height]
                x1, y1, x2, y2 = detection['bbox']
                bbox = [(x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1]

            if track_id in self.tracks[camera_id]:
                # Update existing track
                old_track = self.tracks[camera_id][track_id]

                # Detect ID switch: check if this bbox overlaps with a different track
                self._detect_id_switch(camera_id, track_id, bbox, old_track.last_bbox)

                # Update track
                old_track.update(bbox, detection['confidence'], timestamp)

                # Update zone tracking (Vision 31)
                if self.zone_service:
                    zone_event = self.zone_service.update_track_zone(
                        camera_id, track_id, bbox, timestamp
                    )
                    if zone_event:
                        self._handle_zone_event(zone_event)
            else:
                # Create new track with ByteTrack ID
                self._create_track_with_id(
                    camera_id,
                    track_id,
                    bbox,
                    detection['confidence'],
                    detection['class'],
                    timestamp
                )

                # Initialize zone tracking for new track (Vision 31)
                if self.zone_service:
                    zone_event = self.zone_service.update_track_zone(
                        camera_id, track_id, bbox, timestamp
                    )
                    if zone_event:
                        self._handle_zone_event(zone_event)

        # Mark tracks not seen in this frame as missed
        for track_id in list(self.tracks[camera_id].keys()):
            if track_id not in active_track_ids:
                self.tracks[camera_id][track_id].mark_missed()
                if self.tracks[camera_id][track_id].is_dead():
                    self._close_track(camera_id, track_id, timestamp)

    def _update_with_centroid_matching(self, camera_id: str, detections: List[dict], timestamp: float):
        """
        Update tracks using centroid-based matching (legacy method).

        Args:
            camera_id: Camera identifier
            detections: List of detection dicts
            timestamp: Frame timestamp
        """
        # Match detections to existing tracks
        matched_tracks = set()
        matched_detections = set()

        for det_idx, detection in enumerate(detections):
            best_track_id = None
            best_distance = self.max_distance

            # Find closest track
            for track_id, track in self.tracks[camera_id].items():
                if track_id in matched_tracks:
                    continue

                distance = self._centroid_distance(
                    track.last_bbox,
                    detection['bbox']
                )

                if distance < best_distance:
                    best_distance = distance
                    best_track_id = track_id

            if best_track_id is not None:
                # Update existing track
                self.tracks[camera_id][best_track_id].update(
                    detection['bbox'],
                    detection['confidence'],
                    timestamp
                )
                matched_tracks.add(best_track_id)
                matched_detections.add(det_idx)

        # Mark unmatched tracks as missed
        for track_id, track in list(self.tracks[camera_id].items()):
            if track_id not in matched_tracks:
                track.mark_missed()
                if track.is_dead():
                    self._close_track(camera_id, track_id, timestamp)

        # Create new tracks for unmatched detections
        for det_idx, detection in enumerate(detections):
            if det_idx not in matched_detections:
                self._create_track(
                    camera_id,
                    detection['bbox'],
                    detection['confidence'],
                    detection['class'],
                    timestamp
                )
    
    def _centroid_distance(self, bbox1: List[float], bbox2: List[float]) -> float:
        """Calculate distance between two bounding box centroids."""
        c1 = ((bbox1[0] + bbox1[2]) / 2, (bbox1[1] + bbox1[3]) / 2)
        c2 = ((bbox2[0] + bbox2[2]) / 2, (bbox2[1] + bbox2[3]) / 2)
        return ((c1[0] - c2[0])**2 + (c1[1] - c2[1])**2)**0.5
    
    def _detect_id_switch(self, camera_id: str, new_track_id: int,
                          new_bbox: List[float], old_bbox: List[float]) -> bool:
        """
        Detect if a track ID switch occurred.

        An ID switch is when a new track ID is assigned to a bbox that overlaps
        significantly with an existing track's bbox.

        Args:
            camera_id: Camera identifier
            new_track_id: New track ID
            new_bbox: New bounding box [x_center, y_center, width, height]
            old_bbox: Old bounding box [x_center, y_center, width, height]

        Returns:
            True if ID switch detected, False otherwise
        """
        # Calculate IoU between new and old bbox
        iou = self._calculate_iou(new_bbox, old_bbox)

        # If IoU is high (>0.5), it's likely the same object
        # But if track ID changed, it's an ID switch
        if iou > 0.5:
            # Check if there's another track with high overlap
            for track_id, track in self.tracks[camera_id].items():
                if track_id == new_track_id:
                    continue

                track_iou = self._calculate_iou(new_bbox, track.last_bbox)
                if track_iou > 0.5:
                    self.id_switches += 1
                    logger.warning(f"ID switch detected on {camera_id}: "
                                 f"Track {track_id} -> {new_track_id} (IoU: {track_iou:.2f})")
                    return True

        return False

    def _calculate_iou(self, bbox1: List[float], bbox2: List[float]) -> float:
        """
        Calculate Intersection over Union between two bounding boxes.

        Args:
            bbox1: Bounding box [x_center, y_center, width, height]
            bbox2: Bounding box [x_center, y_center, width, height]

        Returns:
            IoU value between 0.0 and 1.0
        """
        # Convert from [x_center, y_center, width, height] to [x1, y1, x2, y2]
        x1_1 = bbox1[0] - bbox1[2] / 2
        y1_1 = bbox1[1] - bbox1[3] / 2
        x2_1 = bbox1[0] + bbox1[2] / 2
        y2_1 = bbox1[1] + bbox1[3] / 2

        x1_2 = bbox2[0] - bbox2[2] / 2
        y1_2 = bbox2[1] - bbox2[3] / 2
        x2_2 = bbox2[0] + bbox2[2] / 2
        y2_2 = bbox2[1] + bbox2[3] / 2

        # Calculate intersection
        x1_i = max(x1_1, x1_2)
        y1_i = max(y1_1, y1_2)
        x2_i = min(x2_1, x2_2)
        y2_i = min(y2_1, y2_2)

        if x2_i < x1_i or y2_i < y1_i:
            return 0.0

        intersection = (x2_i - x1_i) * (y2_i - y1_i)

        # Calculate union
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection

        return intersection / union if union > 0 else 0.0

    def _handle_zone_event(self, zone_event):
        """
        Handle zone entry/exit event (Vision 31).

        Args:
            zone_event: ZoneEvent object from zone_service
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Store zone event in database
            cursor.execute("""
                INSERT INTO zone_events
                (track_id, camera_id, zone_id, event_type, timestamp, bbox)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                zone_event.track_id,
                zone_event.camera_id,
                zone_event.zone_id,
                zone_event.event_type,
                zone_event.timestamp,
                json.dumps(zone_event.bbox)
            ))

            conn.commit()
            conn.close()

            logger.debug(f"Zone {zone_event.event_type}: Track {zone_event.track_id} "
                        f"{'entered' if zone_event.event_type == 'enter' else 'exited'} "
                        f"zone {zone_event.zone_id}")

            # Broadcast zone event via WebSocket (Vision 31)
            if self.zone_event_callback:
                try:
                    self.zone_event_callback(zone_event)
                except Exception as e:
                    logger.error(f"Error broadcasting zone event: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error storing zone event: {e}", exc_info=True)

    def _create_track(self, camera_id: str, bbox: List[float],
                     confidence: float, class_name: str, timestamp: float):
        """Create a new track with auto-generated ID (legacy method)."""
        track_id = self.next_track_id[camera_id]
        self.next_track_id[camera_id] += 1

        track = Track(track_id, camera_id, bbox, confidence, class_name, timestamp)
        self.tracks[camera_id][track_id] = track
        self.total_tracks_created += 1

        logger.debug(f"Created track {track_id} for {camera_id}")

    def _create_track_with_id(self, camera_id: str, track_id: int, bbox: List[float],
                             confidence: float, class_name: str, timestamp: float):
        """Create a new track with ByteTrack ID."""
        track = Track(track_id, camera_id, bbox, confidence, class_name, timestamp)
        self.tracks[camera_id][track_id] = track
        self.total_tracks_created += 1

        logger.debug(f"Created ByteTrack track {track_id} for {camera_id}")
    
    def _close_track(self, camera_id: str, track_id: int, timestamp: float):
        """Close and store a track."""
        if track_id in self.tracks[camera_id]:
            track = self.tracks[camera_id][track_id]
            self._store_track(track)
            del self.tracks[camera_id][track_id]
            self.total_tracks_closed += 1

            # Cleanup zone data (Vision 31)
            if self.zone_service:
                self.zone_service.cleanup_track(camera_id, track_id)

            logger.debug(f"Closed track {track_id} for {camera_id}")
    
    def _store_track(self, track: Track):
        """Store closed track in database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO tracks 
                (track_id, camera_id, class, enter_time, exit_time, dwell_time, 
                 frames_seen, last_bbox, last_confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                track.track_id,
                track.camera_id,
                track.class_name,
                track.enter_time,
                track.last_seen_time,
                track.get_dwell_time(track.last_seen_time),
                track.frames_seen,
                json.dumps(track.last_bbox),
                track.last_confidence
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error storing track: {e}", exc_info=True)
    
    def get_active_tracks(self, camera_id: str) -> List[dict]:
        """Get all active tracks for a camera."""
        if camera_id not in self.tracks:
            return []

        return [
            track.to_dict()
            for track in self.tracks[camera_id].values()
        ]

    def get_active_tracks_with_dwell(self, camera_id: str, current_time: float) -> List[dict]:
        """
        Get active tracks with real-time dwell time calculation.

        Args:
            camera_id: Camera identifier
            current_time: Current timestamp for dwell time calculation

        Returns:
            List of track dicts with updated dwell_time
        """
        if camera_id not in self.tracks:
            return []

        tracks = []
        for track in self.tracks[camera_id].values():
            track_dict = track.to_dict()
            # Update dwell time to current time (not last_seen_time)
            track_dict['dwell_time'] = current_time - track.enter_time
            track_dict['is_active'] = True
            tracks.append(track_dict)

        return tracks

    def get_stats(self) -> dict:
        """Get tracking statistics."""
        total_active = sum(len(tracks) for tracks in self.tracks.values())

        # Calculate ID switch rate
        id_switch_rate = (self.id_switches / self.total_tracks_created * 100) if self.total_tracks_created > 0 else 0.0

        return {
            'total_tracks_created': self.total_tracks_created,
            'total_tracks_closed': self.total_tracks_closed,
            'active_tracks': total_active,
            'id_switches': self.id_switches,
            'id_switch_rate': round(id_switch_rate, 2),
            'total_detections': self.total_detections,
            'mode': 'ByteTrack' if self.use_bytetrack_ids else 'Centroid'
        }

