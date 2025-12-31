"""
MediaMTX Recording Index Service

Scans MediaMTX recordings directory and indexes them in SQLite database.
MediaMTX creates recordings in format: YYYY-MM-DD/HH-MM-SS-mmm_SEQ.mp4
"""

import os
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import subprocess
import json

logger = logging.getLogger(__name__)


class MediaMTXIndexService:
    """
    Indexes MediaMTX recordings from disk into SQLite database.
    Runs as a background thread to continuously discover new recordings.
    """
    
    def __init__(self, mediamtx_base_path, recording_index, scan_interval_seconds=30):
        """
        Initialize MediaMTX index service.

        Args:
            mediamtx_base_path: Base path where MediaMTX stores recordings (e.g., D:\recordings)
            recording_index: RecordingIndex instance for database operations
            scan_interval_seconds: How often to scan for new recordings
        """
        self.mediamtx_base_path = Path(mediamtx_base_path)
        self.recording_index = recording_index
        self.scan_interval_seconds = scan_interval_seconds

        self.is_running = False
        self.scan_thread = None
        self.indexed_files = set()  # Track which files we've already indexed

        logger.info(f"MediaMTX Index Service initialized: {self.mediamtx_base_path}")
    
    def start(self):
        """Start the background scanning thread."""
        if self.is_running:
            logger.warning("MediaMTX Index Service already running")
            return
        
        self.is_running = True
        self.scan_thread = threading.Thread(
            target=self._scan_loop,
            daemon=True,
            name="MediaMTXIndexThread"
        )
        self.scan_thread.start()
        logger.info("MediaMTX Index Service started")
    
    def stop(self):
        """Stop the background scanning thread."""
        self.is_running = False
        if self.scan_thread:
            self.scan_thread.join(timeout=5)
        logger.info("MediaMTX Index Service stopped")
    
    def _scan_loop(self):
        """Main scanning loop that runs periodically."""
        logger.info("MediaMTX scan loop started")
        
        while self.is_running:
            try:
                self._scan_recordings()
                
                # Sleep for configured interval
                for _ in range(self.scan_interval_seconds):
                    if not self.is_running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error in MediaMTX scan loop: {e}", exc_info=True)
                time.sleep(5)
    
    def _scan_recordings(self):
        """Scan MediaMTX directory for new recordings."""
        if not self.mediamtx_base_path.exists():
            logger.warning(f"MediaMTX path does not exist: {self.mediamtx_base_path}")
            return
        
        try:
            # Scan each camera directory
            for camera_dir in self.mediamtx_base_path.iterdir():
                if not camera_dir.is_dir():
                    continue
                
                camera_id = camera_dir.name
                self._scan_camera_recordings(camera_id, camera_dir)
                
        except Exception as e:
            logger.error(f"Error scanning MediaMTX directory: {e}", exc_info=True)
    
    def _scan_camera_recordings(self, camera_id, camera_path):
        """Scan recordings for a specific camera."""
        try:
            # Scan date directories (YYYY-MM-DD)
            for date_dir in camera_path.iterdir():
                if not date_dir.is_dir():
                    continue
                
                # Scan MP4 files in date directory
                for mp4_file in date_dir.glob("*.mp4"):
                    file_path = str(mp4_file)
                    
                    # Skip if already indexed
                    if file_path in self.indexed_files:
                        continue
                    
                    # Try to index this file
                    if self._index_recording_file(camera_id, file_path):
                        self.indexed_files.add(file_path)
                        
        except Exception as e:
            logger.error(f"Error scanning camera {camera_id}: {e}", exc_info=True)
    
    def _get_mp4_duration_ms(self, file_path):
        """
        Get duration of MP4 file.

        MediaMTX creates fMP4 files that accumulate segments over time.
        ffprobe reads the TOTAL duration of all segments in the file,
        which is incorrect for individual segment indexing.

        Therefore, we use a fixed 3-second duration for all segments,
        which matches MediaMTX's default segment duration.

        Args:
            file_path: Path to MP4 file

        Returns:
            Duration in milliseconds (always 3000ms for MediaMTX segments)
        """
        # MediaMTX segments are approximately 3 seconds each
        # This is the default segment duration in MediaMTX
        # Using ffprobe would give incorrect results because MediaMTX
        # creates fMP4 files that accumulate multiple segments
        logger.debug(f"Using fixed 3000ms duration for MediaMTX segment: {file_path.name}")
        return 3000

    def _index_recording_file(self, camera_id, file_path):
        """
        Index a single recording file.

        Filename format: HH-MM-SS-mmm_SEQ.mp4
        Example: 14-30-45-123_001.mp4
        """
        try:
            file_path = Path(file_path)

            # Extract timestamp from filename
            filename = file_path.stem  # Remove .mp4
            parts = filename.split('_')

            if len(parts) < 2:
                logger.warning(f"Invalid filename format: {filename}")
                return False

            time_part = parts[0]  # HH-MM-SS-mmm
            time_components = time_part.split('-')

            if len(time_components) != 4:
                logger.warning(f"Invalid time format in filename: {time_part}")
                return False

            try:
                hour = int(time_components[0])
                minute = int(time_components[1])
                second = int(time_components[2])
                millisecond = int(time_components[3])
            except ValueError:
                logger.warning(f"Invalid time components: {time_part}")
                return False

            # Get date from parent directory (YYYY-MM-DD)
            date_str = file_path.parent.name

            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                logger.warning(f"Invalid date format: {date_str}")
                return False

            # Construct full start time
            start_time = date_obj.replace(
                hour=hour,
                minute=minute,
                second=second,
                microsecond=millisecond * 1000
            )

            # Get file size
            file_size = file_path.stat().st_size

            # Get actual duration from MP4 file (or use default)
            duration_ms = self._get_mp4_duration_ms(file_path)

            # Index the recording
            camera_name = camera_id.replace('_', ' ').title()

            success = self.recording_index.add_recording(
                camera_id=camera_id,
                camera_name=camera_name,
                segment_path=str(file_path),
                start_time=start_time,
                duration_ms=duration_ms,
                file_size=file_size,
                codec='h264',
                resolution='unknown',
                bitrate=None,
                keyframe_count=None,
                start_time_ms=int(start_time.timestamp() * 1000)
            )

            if success:
                logger.debug(f"Indexed MediaMTX recording: {camera_id} - {file_path.name} ({duration_ms}ms)")
            else:
                logger.warning(f"Failed to index MediaMTX recording: {file_path}")

            return success

        except Exception as e:
            logger.error(f"Error indexing recording file {file_path}: {e}", exc_info=True)
            return False
    
    def get_indexed_count(self):
        """Get count of indexed files."""
        return len(self.indexed_files)
    
    def clear_indexed_cache(self):
        """Clear the indexed files cache (useful for re-indexing)."""
        self.indexed_files.clear()
        logger.info("Cleared MediaMTX indexed files cache")

