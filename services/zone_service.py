"""
Zone Detection Service for Vision 31: Structured Metadata & Context System

Detects when tracked objects enter/exit defined zones using point-in-polygon algorithm.
Calculates per-zone dwell time and tracks zone transitions.
"""

import logging
import yaml
import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Zone:
    """Represents a defined zone in the camera view."""
    id: str
    name: str
    description: str
    polygon: List[Tuple[float, float]]
    color: str
    type: str
    camera_id: str


@dataclass
class ZoneEvent:
    """Represents a zone entry/exit event."""
    track_id: int
    camera_id: str
    zone_id: str
    event_type: str  # 'enter' or 'exit'
    timestamp: float
    bbox: List[float]


class ZoneService:
    """
    Manages zone detection and tracking.
    Uses point-in-polygon algorithm to detect zone entry/exit.
    """

    def __init__(self, config_path: str = "config/zones.yaml"):
        """
        Initialize zone service.

        Args:
            config_path: Path to zone configuration YAML file
        """
        self.config_path = config_path
        self.zones: Dict[str, List[Zone]] = {}  # camera_id -> list of zones
        self.track_zones: Dict[Tuple[str, int], Optional[str]] = {}  # (camera_id, track_id) -> current zone_id
        self.zone_enter_times: Dict[Tuple[str, int, str], float] = {}  # (camera_id, track_id, zone_id) -> enter_time
        self.transition_cooldown: float = 2.0  # seconds
        self.last_transition: Dict[Tuple[str, int], float] = {}  # (camera_id, track_id) -> last_transition_time
        
        self._load_zones()

    def _load_zones(self):
        """Load zone configuration from YAML file."""
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                logger.warning(f"Zone config file not found: {self.config_path}")
                return

            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            if not config or 'cameras' not in config:
                logger.warning("No cameras defined in zone config")
                return

            # Load zones for each camera
            for camera_id, camera_config in config['cameras'].items():
                zones = []
                for zone_config in camera_config.get('zones', []):
                    # Convert polygon coordinates to tuples
                    polygon = [tuple(point) for point in zone_config['polygon']]
                    
                    zone = Zone(
                        id=zone_config['id'],
                        name=zone_config['name'],
                        description=zone_config.get('description', ''),
                        polygon=polygon,
                        color=zone_config.get('color', '#FFFFFF'),
                        type=zone_config.get('type', 'unknown'),
                        camera_id=camera_id
                    )
                    zones.append(zone)

                self.zones[camera_id] = zones
                logger.info(f"Loaded {len(zones)} zones for camera {camera_id}")

            # Load analytics config
            if 'analytics' in config:
                self.transition_cooldown = config['analytics'].get('transition_cooldown', 2.0)

            logger.info(f"✅ Zone service initialized with {sum(len(z) for z in self.zones.values())} total zones")

        except Exception as e:
            logger.error(f"Error loading zone config: {e}", exc_info=True)

    def point_in_polygon(self, point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
        """
        Check if a point is inside a polygon using ray casting algorithm.

        Args:
            point: (x, y) coordinates
            polygon: List of (x, y) coordinates defining the polygon

        Returns:
            True if point is inside polygon, False otherwise
        """
        x, y = point
        n = len(polygon)
        inside = False

        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y

        return inside

    def get_bbox_center(self, bbox: List[float]) -> Tuple[float, float]:
        """
        Get center point of bounding box.

        Args:
            bbox: Bounding box in [x_center, y_center, width, height] format

        Returns:
            (x, y) center coordinates
        """
        # bbox is already in [x_center, y_center, width, height] format
        return (bbox[0], bbox[1])

    def get_zone_for_track(self, camera_id: str, bbox: List[float]) -> Optional[Zone]:
        """
        Get the zone that contains the track's bounding box center.

        Args:
            camera_id: Camera identifier
            bbox: Bounding box in [x_center, y_center, width, height] format

        Returns:
            Zone object if track is in a zone, None otherwise
        """
        if camera_id not in self.zones:
            return None

        center = self.get_bbox_center(bbox)

        # Check each zone for this camera
        for zone in self.zones[camera_id]:
            if self.point_in_polygon(center, zone.polygon):
                return zone

        return None

    def update_track_zone(self, camera_id: str, track_id: int, bbox: List[float], 
                         timestamp: float) -> Optional[ZoneEvent]:
        """
        Update track's current zone and detect zone transitions.

        Args:
            camera_id: Camera identifier
            track_id: Track identifier
            bbox: Bounding box in [x_center, y_center, width, height] format
            timestamp: Current timestamp

        Returns:
            ZoneEvent if a zone transition occurred, None otherwise
        """
        track_key = (camera_id, track_id)
        
        # Check transition cooldown
        if track_key in self.last_transition:
            if timestamp - self.last_transition[track_key] < self.transition_cooldown:
                return None

        # Get current zone
        current_zone = self.get_zone_for_track(camera_id, bbox)
        current_zone_id = current_zone.id if current_zone else None

        # Get previous zone
        previous_zone_id = self.track_zones.get(track_key)

        # Check for zone transition
        if current_zone_id != previous_zone_id:
            # Update track zone
            self.track_zones[track_key] = current_zone_id
            self.last_transition[track_key] = timestamp

            # Handle zone exit
            if previous_zone_id is not None:
                # Calculate zone dwell time
                enter_key = (camera_id, track_id, previous_zone_id)
                if enter_key in self.zone_enter_times:
                    enter_time = self.zone_enter_times[enter_key]
                    dwell_time = timestamp - enter_time
                    del self.zone_enter_times[enter_key]
                    logger.debug(f"Track {track_id} exited zone {previous_zone_id} after {dwell_time:.1f}s")

                # Create exit event
                exit_event = ZoneEvent(
                    track_id=track_id,
                    camera_id=camera_id,
                    zone_id=previous_zone_id,
                    event_type='exit',
                    timestamp=timestamp,
                    bbox=bbox
                )

            # Handle zone entry
            if current_zone_id is not None:
                # Record enter time
                enter_key = (camera_id, track_id, current_zone_id)
                self.zone_enter_times[enter_key] = timestamp
                logger.debug(f"Track {track_id} entered zone {current_zone_id}")

                # Create entry event
                return ZoneEvent(
                    track_id=track_id,
                    camera_id=camera_id,
                    zone_id=current_zone_id,
                    event_type='enter',
                    timestamp=timestamp,
                    bbox=bbox
                )

        return None

    def get_zone_dwell_time(self, camera_id: str, track_id: int, zone_id: str, 
                           current_time: float) -> Optional[float]:
        """
        Get dwell time for a track in a specific zone.

        Args:
            camera_id: Camera identifier
            track_id: Track identifier
            zone_id: Zone identifier
            current_time: Current timestamp

        Returns:
            Dwell time in seconds, or None if track not in zone
        """
        enter_key = (camera_id, track_id, zone_id)
        if enter_key in self.zone_enter_times:
            return current_time - self.zone_enter_times[enter_key]
        return None

    def get_current_zone(self, camera_id: str, track_id: int) -> Optional[str]:
        """
        Get current zone for a track.

        Args:
            camera_id: Camera identifier
            track_id: Track identifier

        Returns:
            Zone ID if track is in a zone, None otherwise
        """
        track_key = (camera_id, track_id)
        return self.track_zones.get(track_key)

    def get_zones_for_camera(self, camera_id: str) -> List[Zone]:
        """
        Get all zones for a camera.

        Args:
            camera_id: Camera identifier

        Returns:
            List of Zone objects
        """
        return self.zones.get(camera_id, [])

    def cleanup_track(self, camera_id: str, track_id: int):
        """
        Clean up zone data for a closed track.

        Args:
            camera_id: Camera identifier
            track_id: Track identifier
        """
        track_key = (camera_id, track_id)
        
        # Remove from track_zones
        if track_key in self.track_zones:
            del self.track_zones[track_key]
        
        # Remove from last_transition
        if track_key in self.last_transition:
            del self.last_transition[track_key]
        
        # Remove from zone_enter_times
        keys_to_remove = [k for k in self.zone_enter_times.keys() if k[0] == camera_id and k[1] == track_id]
        for key in keys_to_remove:
            del self.zone_enter_times[key]

