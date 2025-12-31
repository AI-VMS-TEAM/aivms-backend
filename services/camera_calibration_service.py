"""
Camera Calibration Service for 3D Scene Understanding

Implements perspective transform and real-world size filtering.
Similar to Bosch IVA Pro's 3D calibration feature.
"""

import cv2
import numpy as np
import yaml
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class CameraCalibration:
    """
    Handles 3D calibration for a single camera.
    Converts pixel coordinates to real-world coordinates.
    """
    
    def __init__(self, camera_id, config):
        """
        Initialize camera calibration.
        
        Args:
            camera_id: Camera identifier
            config: Calibration config dict for this camera
        """
        self.camera_id = camera_id
        self.config = config
        self.enabled = config.get('enabled', False)
        
        if not self.enabled:
            logger.info(f"📷 [{camera_id}] Calibration disabled")
            return
        
        # Physical parameters
        self.camera_height = config.get('camera_height_meters', 3.0)
        self.camera_angle = config.get('camera_angle_degrees', 30)
        
        # Perspective transform
        self.perspective_matrix = None
        self.inverse_perspective_matrix = None
        self._init_perspective_transform()
        
        # Object filters
        self.object_filters = config.get('object_filters', {})
        self.min_detection_area = config.get('min_detection_area_pixels', 400)
        
        logger.info(f"✅ [{camera_id}] Calibration enabled (height={self.camera_height}m, angle={self.camera_angle}°)")
    
    def _init_perspective_transform(self):
        """Initialize perspective transform matrix."""
        perspective_config = self.config.get('perspective_points', {})
        
        if not perspective_config:
            logger.warning(f"⚠️ [{self.camera_id}] No perspective points configured")
            return
        
        # Get pixel coordinates (4 points forming a quadrilateral)
        pixel_coords = perspective_config.get('pixel_coords', [])
        if len(pixel_coords) != 4:
            logger.warning(f"⚠️ [{self.camera_id}] Need exactly 4 perspective points, got {len(pixel_coords)}")
            return
        
        # Get real-world dimensions
        real_width = perspective_config.get('real_world_width_meters', 10.0)
        real_height = perspective_config.get('real_world_height_meters', 8.0)
        
        # Source points (pixel coordinates)
        src_points = np.float32(pixel_coords)
        
        # Destination points (real-world coordinates in meters, scaled to pixels for visualization)
        # We use a scale factor to keep numbers manageable
        scale = 100  # 1 meter = 100 pixels in bird's eye view
        dst_points = np.float32([
            [0, 0],
            [real_width * scale, 0],
            [real_width * scale, real_height * scale],
            [0, real_height * scale]
        ])
        
        # Calculate perspective transform matrix
        self.perspective_matrix = cv2.getPerspectiveTransform(src_points, dst_points)
        self.inverse_perspective_matrix = cv2.getPerspectiveTransform(dst_points, src_points)
        
        self.real_world_scale = scale  # pixels per meter in bird's eye view
        
        logger.info(f"✅ [{self.camera_id}] Perspective transform initialized ({real_width}m x {real_height}m)")
    
    def pixel_to_real_world(self, x_pixel, y_pixel):
        """
        Convert pixel coordinates to real-world coordinates.
        
        Args:
            x_pixel: X coordinate in pixels
            y_pixel: Y coordinate in pixels
        
        Returns:
            (x_meters, y_meters): Real-world coordinates in meters
        """
        if self.perspective_matrix is None:
            return None, None
        
        # Transform point
        point = np.array([[[x_pixel, y_pixel]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(point, self.perspective_matrix)
        
        # Convert from scaled pixels to meters
        x_meters = transformed[0][0][0] / self.real_world_scale
        y_meters = transformed[0][0][1] / self.real_world_scale
        
        return x_meters, y_meters
    
    def bbox_to_real_world_size(self, bbox):
        """
        Calculate real-world size of bounding box.
        
        Args:
            bbox: [x1, y1, x2, y2] in pixels
        
        Returns:
            (width_meters, height_meters): Real-world dimensions
        """
        if self.perspective_matrix is None:
            return None, None
        
        x1, y1, x2, y2 = bbox
        
        # Get bottom-center point (object touching ground)
        bottom_center_x = (x1 + x2) / 2
        bottom_center_y = y2
        
        # Transform to real-world
        center_x_m, center_y_m = self.pixel_to_real_world(bottom_center_x, bottom_center_y)
        
        if center_x_m is None:
            return None, None
        
        # Transform bbox corners to estimate size
        top_left_x_m, top_left_y_m = self.pixel_to_real_world(x1, y1)
        bottom_right_x_m, bottom_right_y_m = self.pixel_to_real_world(x2, y2)
        
        if top_left_x_m is None or bottom_right_x_m is None:
            return None, None
        
        width_meters = abs(bottom_right_x_m - top_left_x_m)
        height_meters = abs(bottom_right_y_m - top_left_y_m)

        return width_meters, height_meters

    def is_valid_detection(self, detection):
        """
        Check if detection is valid based on real-world size filters.

        Args:
            detection: Detection dict with 'bbox' and 'class'

        Returns:
            (is_valid, reason): Tuple of (bool, str)
        """
        if not self.enabled:
            return True, "calibration_disabled"

        bbox = detection.get('bbox')
        class_name = detection.get('class')

        if not bbox or not class_name:
            return True, "missing_data"

        # Check minimum pixel area
        x1, y1, x2, y2 = bbox
        pixel_area = (x2 - x1) * (y2 - y1)

        if pixel_area < self.min_detection_area:
            return False, f"too_small_pixels ({pixel_area:.0f} < {self.min_detection_area})"

        # Check real-world size if perspective transform is available
        if self.perspective_matrix is not None:
            width_m, height_m = self.bbox_to_real_world_size(bbox)

            if width_m is None or height_m is None:
                return True, "transform_failed"

            # Get size filters for this class
            class_filters = self.object_filters.get(class_name, {})

            if not class_filters:
                return True, "no_filters"

            min_width = class_filters.get('min_width', 0)
            max_width = class_filters.get('max_width', 999)
            min_height = class_filters.get('min_height', 0)
            max_height = class_filters.get('max_height', 999)

            # Check if size is within valid range
            if width_m < min_width or width_m > max_width:
                return False, f"invalid_width ({width_m:.2f}m not in [{min_width}, {max_width}])"

            if height_m < min_height or height_m > max_height:
                return False, f"invalid_height ({height_m:.2f}m not in [{min_height}, {max_height}])"

            return True, f"valid ({width_m:.2f}m x {height_m:.2f}m)"

        return True, "no_transform"


class CameraCalibrationService:
    """
    Manages calibration for all cameras.
    """

    def __init__(self, config_path='config/camera_calibration.yaml'):
        """
        Initialize calibration service.

        Args:
            config_path: Path to calibration config file
        """
        self.config_path = Path(config_path)
        self.calibrations = {}

        self._load_config()

    def _load_config(self):
        """Load calibration config from YAML file."""
        if not self.config_path.exists():
            logger.warning(f"⚠️ Calibration config not found: {self.config_path}")
            return

        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Create calibration for each camera
            for camera_id, camera_config in config.items():
                if isinstance(camera_config, dict):
                    self.calibrations[camera_id] = CameraCalibration(camera_id, camera_config)

            logger.info(f"✅ Loaded calibration for {len(self.calibrations)} cameras")

        except Exception as e:
            logger.error(f"❌ Failed to load calibration config: {e}")

    def get_calibration(self, camera_id):
        """
        Get calibration for a specific camera.

        Args:
            camera_id: Camera identifier

        Returns:
            CameraCalibration or None
        """
        return self.calibrations.get(camera_id)

    def filter_detections(self, camera_id, detections):
        """
        Filter detections based on calibration rules.

        Args:
            camera_id: Camera identifier
            detections: List of detection dicts

        Returns:
            filtered_detections: List of valid detections
        """
        calibration = self.get_calibration(camera_id)

        if calibration is None or not calibration.enabled:
            return detections

        filtered = []
        filtered_count = 0

        for det in detections:
            is_valid, reason = calibration.is_valid_detection(det)

            if is_valid:
                filtered.append(det)
            else:
                filtered_count += 1
                logger.debug(f"🚫 [{camera_id}] Filtered {det.get('class')} detection: {reason}")

        if filtered_count > 0:
            logger.debug(f"📊 [{camera_id}] Filtered {filtered_count}/{len(detections)} detections")

        return filtered


