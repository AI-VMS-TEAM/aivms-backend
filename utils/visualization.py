"""
Visualization utilities for drawing detections, tracks, and zones on video frames.
Used for Vision 31 zone overlays and detection visualization.
"""

import cv2
import numpy as np
from typing import List, Dict, Optional, Tuple


def hex_to_bgr(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex color to BGR tuple for OpenCV."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (4, 2, 0))  # BGR order


def draw_zones(frame: np.ndarray, zones: List[Dict], opacity: float = 0.2) -> np.ndarray:
    """
    Draw zone polygons on frame.
    
    Args:
        frame: Video frame
        zones: List of zone dicts with 'polygon' and 'color' keys
        opacity: Zone fill opacity (0.0 - 1.0)
    
    Returns:
        Frame with zones drawn
    """
    overlay = frame.copy()
    
    for zone in zones:
        polygon = zone.get('polygon', [])
        color_hex = zone.get('color', '#FFFFFF')
        zone_name = zone.get('name', 'Zone')
        
        if not polygon:
            continue
        
        # Convert hex to BGR
        color = hex_to_bgr(color_hex)
        
        # Convert polygon to numpy array
        pts = np.array(polygon, dtype=np.int32)
        
        # Draw filled polygon with opacity
        cv2.polylines(overlay, [pts], True, color, 2)
        cv2.fillPoly(overlay, [pts], color, 1)
        
        # Draw zone label
        if polygon:
            label_pos = tuple(polygon[0])
            cv2.putText(overlay, zone_name, label_pos, 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    
    # Blend overlay with original frame
    cv2.addWeighted(overlay, opacity, frame, 1 - opacity, 0, frame)
    
    return frame


def draw_detections(frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
    """
    Draw bounding boxes for detections on frame.
    
    Args:
        frame: Video frame
        detections: List of detection dicts with 'bbox' and 'class' keys
    
    Returns:
        Frame with detections drawn
    """
    for detection in detections:
        bbox = detection.get('bbox', [])  # [x1, y1, x2, y2]
        class_name = detection.get('class', 'Unknown')
        confidence = detection.get('confidence', 0.0)
        
        if len(bbox) < 4:
            continue
        
        x1, y1, x2, y2 = [int(x) for x in bbox]
        
        # Draw bounding box (green)
        color = (0, 255, 0)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        # Draw label
        label = f"{class_name} {confidence:.2f}"
        cv2.putText(frame, label, (x1, y1 - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    
    return frame


def draw_tracks(frame: np.ndarray, tracks: List[Dict]) -> np.ndarray:
    """
    Draw tracking visualization on frame.
    
    Args:
        frame: Video frame
        tracks: List of track dicts with 'bbox', 'track_id', 'class', 'dwell_time'
    
    Returns:
        Frame with tracks drawn
    """
    for track in tracks:
        bbox = track.get('bbox', [])  # [x_center, y_center, width, height]
        track_id = track.get('track_id', 0)
        class_name = track.get('class', 'Unknown')
        dwell_time = track.get('dwell_time', 0.0)
        
        if len(bbox) < 4:
            continue
        
        # Convert from center format to corner format
        x_center, y_center, width, height = bbox
        x1 = int(x_center - width / 2)
        y1 = int(y_center - height / 2)
        x2 = int(x_center + width / 2)
        y2 = int(y_center + height / 2)
        
        # Draw bounding box (green)
        color = (0, 255, 0)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        # Draw track ID and dwell time
        label = f"ID:{track_id} {class_name} {dwell_time:.1f}s"
        cv2.putText(frame, label, (x1, y1 - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    
    return frame


def draw_zones_and_tracks(frame: np.ndarray, zones: List[Dict], 
                         tracks: List[Dict], opacity: float = 0.2) -> np.ndarray:
    """
    Draw both zones and tracks on frame (combined visualization).
    
    Args:
        frame: Video frame
        zones: List of zone dicts
        tracks: List of track dicts
        opacity: Zone fill opacity
    
    Returns:
        Frame with zones and tracks drawn
    """
    # Draw zones first (background)
    frame = draw_zones(frame, zones, opacity)
    
    # Draw tracks on top
    frame = draw_tracks(frame, tracks)
    
    return frame

