"""
Continuous Recording Engine for AIVMS
Records video from HLS streams into fMP4 segments with indexing and retention
"""

import os
import threading
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
import requests
from urllib.parse import urljoin

from services.recording_index import RecordingIndex
from services.segment_processor import SegmentProcessor
from services.retention_manager import RetentionManager
from services.recovery_manager import RecoveryManager
from services.recovery_tracker import RecoveryTracker
from services.emergency_cleanup_manager import EmergencyCleanupManager
from services.timeline_manager import TimelineManager
from services.playback_manager import PlaybackManager
from config.storage_config import RECORDINGS_BASE_PATH, get_camera_path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RecordingEngine:
    """
    Main recording engine that manages continuous recording for all cameras.
    
    Features:
    - Continuous HLS stream recording
    - fMP4 segment creation with keyframe detection
    - SQLite indexing for fast lookups
    - Automatic retention and cleanup
    - Crash recovery and file verification
    """
    
    def __init__(self, cameras, storage_path=None,
                 segment_duration_ms=3000, retention_days=30, health_monitor=None):
        """
        Initialize the recording engine.

        Args:
            cameras: List of camera configurations
            storage_path: Base path for storing recordings (uses D:\\recordings by default)
            segment_duration_ms: Target segment duration (2000-4000ms)
            retention_days: Days to keep recordings (7-90)
            health_monitor: Optional HealthMonitor instance for IOPS tracking
        """
        self.cameras = cameras
        # Use provided path or default to configured D drive location
        self.storage_path = Path(storage_path or RECORDINGS_BASE_PATH)
        self.segment_duration_ms = segment_duration_ms
        self.retention_days = retention_days
        self.health_monitor = health_monitor

        # Create storage directory
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.index_db = RecordingIndex(str(self.storage_path / "recordings.db"))
        self.segment_processor = SegmentProcessor(segment_duration_ms)
        self.retention_manager = RetentionManager(self.index_db, self.storage_path, retention_days)
        self.recovery_manager = RecoveryManager(self.index_db, self.storage_path)
        self.timeline_manager = TimelineManager(self.index_db)
        self.playback_manager = PlaybackManager(self.index_db, self.storage_path)

        # Initialize emergency cleanup manager
        self.emergency_cleanup_manager = EmergencyCleanupManager(
            health_monitor,
            self.retention_manager,
            self.retention_manager.policy_manager,
            self.index_db
        )

        # Extract camera IDs for recovery tracker (normalize names like app.py does)
        camera_ids = [cam.get('name', '').lower().replace(' ', '_').replace('-', '_') for cam in cameras]
        self.recovery_tracker = RecoveryTracker(health_monitor=health_monitor, camera_ids=camera_ids)

        # Recording state
        self.recording_threads = {}
        self.is_running = False
        self.camera_states = {}

        # Cache for init segments (one per camera)
        self.init_segments = {}
        
        logger.info(f"RecordingEngine initialized with {len(cameras)} camera(s)")
        logger.info(f"Storage path: {self.storage_path}")
        logger.info(f"Segment duration: {segment_duration_ms}ms")
        logger.info(f"Retention: {retention_days} days")
    
    def start(self):
        """Start recording for all cameras."""
        if self.is_running:
            logger.warning("Recording engine already running")
            return

        logger.info("Starting recording engine...")

        # Start retention manager
        self.retention_manager.start_cleanup_thread()

        # Start emergency cleanup manager
        self.emergency_cleanup_manager.start()

        # Start recording thread for each camera
        self.is_running = True
        for camera in self.cameras:
            camera_id = camera.get('name', '').lower().replace(' ', '_').replace('-', '_')
            camera_name = camera.get('name', 'Unknown')
            
            # Initialize camera state
            self.camera_states[camera_id] = {
                'name': camera_name,
                'is_recording': False,
                'last_segment_time': None,
                'segments_recorded': 0,
                'bytes_written': 0,
                'errors': 0
            }
            
            # Create and start recording thread
            thread = threading.Thread(
                target=self._record_camera,
                args=(camera_id, camera_name),
                daemon=True,
                name=f"RecordingThread-{camera_id}"
            )
            thread.start()
            self.recording_threads[camera_id] = thread
            logger.info(f"Started recording thread for {camera_name}")

        logger.info("Recording engine started successfully")

        # Note: Recovery check is disabled during active recording to prevent database locks
        # Recovery will be run manually or on next startup when recording is not active
        logger.info("Recovery check deferred (will run on next startup)")
    
    def stop(self):
        """Stop recording for all cameras."""
        logger.info("Stopping recording engine...")
        self.is_running = False

        # Stop retention manager
        self.retention_manager.stop_cleanup_thread()

        # Stop emergency cleanup manager
        self.emergency_cleanup_manager.stop()

        # Wait for threads to finish
        for camera_id, thread in self.recording_threads.items():
            thread.join(timeout=5)
            logger.info(f"Stopped recording for {camera_id}")

        logger.info("Recording engine stopped")
    
    def _record_camera(self, camera_id, camera_name):
        """
        Record video for a single camera.
        Runs in a separate thread for each camera.
        Includes error detection and auto-recovery.
        """
        mediamtx_host = os.environ.get('MEDIAMTX_HOST', 'localhost')
        hls_url = f"http://{mediamtx_host}:8888/{camera_id}/index.m3u8"
        camera_storage = self.storage_path / camera_id
        camera_storage.mkdir(parents=True, exist_ok=True)

        logger.info(f"[{camera_name}] Starting recording from {hls_url}")

        retry_count = 0
        max_retries = 3
        consecutive_errors = 0

        while self.is_running:
            try:
                # Update state
                self.camera_states[camera_id]['is_recording'] = True

                # Download and process HLS stream
                self._process_hls_stream(
                    camera_id, camera_name, hls_url, camera_storage
                )

                # Reset error tracking on successful stream processing
                retry_count = 0
                consecutive_errors = 0
                self.recovery_tracker.mark_recovered(camera_id)

            except (OSError, IOError, PermissionError) as e:
                # File system errors (write failures, file locks, permission denied)
                error_msg = f"File system error: {str(e)}"
                logger.error(f"[{camera_name}] {error_msg}")
                self.camera_states[camera_id]['errors'] += 1
                consecutive_errors += 1

                # Record error and check if recovery needed
                should_recover = self.recovery_tracker.record_error(
                    camera_id, 'write_failure', error_msg
                )

                if should_recover:
                    logger.warning(f"[{camera_name}] Triggering auto-recovery from write failure")
                    self._attempt_recovery(camera_id, camera_name, 'write_failure')
                    consecutive_errors = 0
                else:
                    time.sleep(1)

            except requests.Timeout as e:
                # Network timeout errors
                error_msg = f"Stream timeout: {str(e)}"
                logger.warning(f"[{camera_name}] {error_msg}")
                self.camera_states[camera_id]['errors'] += 1
                consecutive_errors += 1

                should_recover = self.recovery_tracker.record_error(
                    camera_id, 'timeout', error_msg
                )

                if should_recover:
                    logger.warning(f"[{camera_name}] Triggering auto-recovery from timeout")
                    self._attempt_recovery(camera_id, camera_name, 'timeout')
                    consecutive_errors = 0
                else:
                    time.sleep(2)

            except requests.ConnectionError as e:
                # Network connection errors (stream disconnected)
                error_msg = f"Stream disconnected: {str(e)}"
                logger.warning(f"[{camera_name}] {error_msg}")
                self.camera_states[camera_id]['errors'] += 1
                consecutive_errors += 1

                should_recover = self.recovery_tracker.record_error(
                    camera_id, 'stream_disconnect', error_msg
                )

                if should_recover:
                    logger.warning(f"[{camera_name}] Triggering auto-recovery from stream disconnect")
                    self._attempt_recovery(camera_id, camera_name, 'stream_disconnect')
                    consecutive_errors = 0
                else:
                    time.sleep(3)

            except Exception as e:
                # Generic errors
                error_msg = f"Unexpected error: {str(e)}"
                logger.error(f"[{camera_name}] {error_msg}")
                self.camera_states[camera_id]['errors'] += 1
                consecutive_errors += 1

                should_recover = self.recovery_tracker.record_error(
                    camera_id, 'unknown', error_msg
                )

                if should_recover:
                    logger.warning(f"[{camera_name}] Triggering auto-recovery from unknown error")
                    self._attempt_recovery(camera_id, camera_name, 'unknown')
                    consecutive_errors = 0
                else:
                    time.sleep(1)

        self.camera_states[camera_id]['is_recording'] = False
        logger.info(f"[{camera_name}] Recording stopped")
    
    def _attempt_recovery(self, camera_id: str, camera_name: str, error_type: str):
        """
        Attempt to recover from a transient error by reinitializing the recorder.

        Args:
            camera_id: Camera identifier
            camera_name: Camera display name
            error_type: Type of error that triggered recovery
        """
        logger.warning(f"[{camera_name}] Attempting recovery from {error_type}...")

        try:
            # Step 1: Clear init segment cache to force re-download
            if camera_id in self.init_segments:
                del self.init_segments[camera_id]
                logger.info(f"[{camera_name}] Cleared init segment cache")

            # Step 2: Wait a brief period before retrying
            time.sleep(5)

            # Step 3: Log recovery attempt
            logger.info(f"[{camera_name}] Recovery attempt completed, resuming recording")

        except Exception as e:
            logger.error(f"[{camera_name}] Recovery attempt failed: {e}")

    def _process_hls_stream(self, camera_id, camera_name, hls_url, storage_path):
        """
        Download and process HLS stream segments.
        Handles both master playlists and segment playlists.
        Handles media sequence resets/recycling by tracking segment URLs instead of just sequence numbers.
        """
        last_segment_urls = set()  # Track segment URLs to detect new segments
        segment_playlist_url = None
        init_segment_downloaded = False

        while self.is_running:
            try:
                # Fetch master playlist
                response = requests.get(hls_url, timeout=5)
                response.raise_for_status()
                playlist_content = response.text

                # Check if this is a master playlist (contains #EXT-X-STREAM-INF)
                if '#EXT-X-STREAM-INF' in playlist_content:
                    # Extract the segment playlist URL from master playlist
                    segment_playlist_url = self._extract_segment_playlist_url(
                        playlist_content, hls_url
                    )
                    if not segment_playlist_url:
                        logger.warning(f"[{camera_name}] Could not extract segment playlist URL")
                        time.sleep(2)
                        continue
                    logger.info(f"[{camera_name}] Using segment playlist: {segment_playlist_url}")
                else:
                    # This is already a segment playlist
                    segment_playlist_url = hls_url

                # Download init segment once
                if not init_segment_downloaded:
                    self._download_init_segment(camera_id, camera_name, segment_playlist_url)
                    init_segment_downloaded = True

                # Fetch segment playlist
                response = requests.get(segment_playlist_url, timeout=5)
                response.raise_for_status()
                playlist_content = response.text

                # Parse media sequence and segments
                media_sequence, segments = self._parse_segment_playlist(
                    playlist_content, segment_playlist_url
                )

                # Process new segments by comparing URLs (handles media sequence resets)
                current_segment_urls = set(segments)
                new_segments = current_segment_urls - last_segment_urls

                if new_segments:
                    for segment_url in segments:
                        if segment_url in new_segments:
                            # Download and process segment
                            self._download_and_process_segment(
                                camera_id, camera_name, segment_url, storage_path
                            )
                    last_segment_urls = current_segment_urls

                time.sleep(0.5)  # Poll every 500ms

            except requests.RequestException as e:
                logger.warning(f"[{camera_name}] Failed to fetch playlist: {e}")
                time.sleep(2)
    
    def _extract_segment_playlist_url(self, master_playlist_content, base_url):
        """Extract segment playlist URL from master playlist."""
        for line in master_playlist_content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                # This should be the segment playlist URL
                return urljoin(base_url, line)
        return None

    def _extract_init_segment_url(self, playlist_content, base_url):
        """Extract initialization segment URL from HLS playlist."""
        for line in playlist_content.split('\n'):
            line = line.strip()
            if line.startswith('#EXT-X-MAP:'):
                # Extract URI from #EXT-X-MAP:URI="..."
                uri_start = line.find('URI="') + 5
                uri_end = line.find('"', uri_start)
                if uri_start > 4 and uri_end > uri_start:
                    init_url = urljoin(base_url, line[uri_start:uri_end])
                    return init_url
        return None

    def _download_init_segment(self, camera_id, camera_name, playlist_url):
        """Download and cache the initialization segment for a camera."""
        try:
            # Check if already cached
            if camera_id in self.init_segments:
                return self.init_segments[camera_id]

            # Fetch playlist to get init segment URL
            response = requests.get(playlist_url, timeout=5)
            response.raise_for_status()
            playlist_content = response.text

            # Extract init segment URL
            init_url = self._extract_init_segment_url(playlist_content, playlist_url)
            if not init_url:
                logger.warning(f"[{camera_name}] Could not find init segment in playlist")
                return None

            # Download init segment
            response = requests.get(init_url, timeout=10)
            response.raise_for_status()
            init_data = response.content

            # Cache it
            self.init_segments[camera_id] = init_data
            logger.info(f"[{camera_name}] Downloaded init segment: {len(init_data)} bytes")

            return init_data

        except Exception as e:
            logger.error(f"[{camera_name}] Failed to download init segment: {e}")
            return None

    def _parse_segment_playlist(self, playlist_content, base_url):
        """
        Parse segment playlist and extract media sequence and segment URLs.
        Returns: (media_sequence, [segment_urls])
        """
        media_sequence = 0
        segments = []

        for line in playlist_content.split('\n'):
            line = line.strip()

            # Extract media sequence
            if line.startswith('#EXT-X-MEDIA-SEQUENCE:'):
                media_sequence = int(line.split(':')[1])

            # Extract segment URLs (lines that don't start with #)
            # Only get full segments (those with _seg in the name), skip parts and init
            elif line and not line.startswith('#'):
                if '_seg' in line and '_part' not in line and '_init' not in line:
                    segment_url = urljoin(base_url, line)
                    segments.append(segment_url)

        return media_sequence, segments
    
    def _download_and_process_segment(self, camera_id, camera_name, segment_url, storage_path):
        """Download HLS segment and create playable fMP4 file."""
        try:
            # Download segment
            response = requests.get(segment_url, timeout=10)
            response.raise_for_status()
            segment_data = response.content

            # Get init segment (needed to make fMP4 playable)
            init_data = self.init_segments.get(camera_id)
            if not init_data:
                logger.warning(f"[{camera_name}] Init segment not available, segment may not be playable")
                init_data = b''

            # Create playable MP4 by prepending init segment to fragment
            # Init segment contains ftyp + moov boxes needed for playback
            playable_mp4_data = init_data + segment_data

            # Process into fMP4 chunk
            timestamp_ms = int(time.time() * 1000)

            # Extract segment name from URL to use as unique identifier
            # This handles media sequence resets properly
            segment_name = segment_url.split('/')[-1].replace('.mp4', '')

            # Create date-based folder structure: YYYY-MM-DD
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            date_folder = storage_path / today
            date_folder.mkdir(parents=True, exist_ok=True)

            # Create human-readable filename: HH-MM-SS-mmm_SEGNAME.mp4
            # Example: 17-02-23-387_seg1234.mp4 (5:02:23 PM and 387 milliseconds, segment name from HLS)
            time_str = now.strftime("%H-%M-%S")
            ms_str = f"{now.microsecond // 1000:03d}"
            segment_filename = f"{time_str}-{ms_str}_{segment_name}.mp4"
            segment_path = date_folder / segment_filename

            # Write playable MP4 file (init + segment)
            with open(segment_path, 'wb') as f:
                f.write(playable_mp4_data)

            file_size = len(playable_mp4_data)

            # Track IOPS if health monitor is available
            if self.health_monitor:
                self.health_monitor.record_write_operation(camera_id, file_size)

            # Index in database with millisecond precision
            success = self.index_db.add_recording(
                camera_id=camera_id,
                camera_name=camera_name,
                segment_path=str(segment_path),
                start_time=datetime.fromtimestamp(timestamp_ms / 1000),
                start_time_ms=timestamp_ms,
                duration_ms=self.segment_duration_ms,
                file_size=file_size
            )

            if not success:
                logger.error(f"[{camera_name}] Failed to index segment: {segment_filename}")
                return False

            # Update timeline index for scrubber
            segment_data = {
                'start_time': datetime.fromtimestamp(timestamp_ms / 1000),
                'duration_ms': self.segment_duration_ms,
                'file_size': file_size
            }
            self.timeline_manager.update_timeline(camera_id, segment_data)

            # Update state
            self.camera_states[camera_id]['segments_recorded'] += 1
            self.camera_states[camera_id]['bytes_written'] += file_size
            self.camera_states[camera_id]['last_segment_time'] = datetime.now()

            logger.info(f"[{camera_name}] Recorded segment: {segment_filename} ({file_size} bytes) - Total: {self.camera_states[camera_id]['segments_recorded']}")

        except Exception as e:
            logger.error(f"[{camera_name}] Failed to process segment: {e}", exc_info=True)
    
    def get_status(self, camera_id=None):
        """Get recording status for camera(s)."""
        # Convert datetime objects to ISO format strings for JSON serialization
        def format_status(status):
            formatted = status.copy()
            if formatted.get('last_segment_time') and isinstance(formatted['last_segment_time'], datetime):
                formatted['last_segment_time'] = formatted['last_segment_time'].isoformat()
            return formatted

        if camera_id:
            status = self.camera_states.get(camera_id, {})
            return format_status(status)

        # Format all camera statuses
        return {cam_id: format_status(status) for cam_id, status in self.camera_states.items()}
    
    def get_segments(self, camera_id, start_time=None, end_time=None):
        """Get segments for a camera in time range."""
        return self.index_db.get_segments(camera_id, start_time, end_time)

