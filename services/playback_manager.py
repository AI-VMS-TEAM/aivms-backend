"""
Playback Manager - Handles video playback and HLS playlist generation
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class PlaybackManager:
    """Manages video playback and HLS playlist generation"""
    
    def __init__(self, index_db, storage_path):
        """
        Initialize PlaybackManager
        
        Args:
            index_db: RecordingIndex instance
            storage_path: Base path for recordings
        """
        self.index_db = index_db
        self.storage_path = Path(storage_path)
        logger.info("PlaybackManager initialized")
    
    def get_segments_for_playback(self, camera_id: str, start_time: datetime,
                                  end_time: datetime) -> List[Dict]:
        """
        Get segments for playback in time range

        Args:
            camera_id: Camera identifier
            start_time: Start time for playback
            end_time: End time for playback

        Returns:
            List of segment dicts with path, start_time, duration_ms, file_size
        """
        try:
            # Query segments from index
            segments = self.index_db.get_segments(camera_id, start_time, end_time)

            if not segments:
                logger.warning(f"No segments found for {camera_id} between {start_time} and {end_time}")
                return []

            # Convert to playback format
            playback_segments = []
            for segment in segments:
                playback_segments.append({
                    'segment_path': segment.get('segment_path'),
                    'start_time': segment.get('start_time'),
                    'duration_ms': segment.get('duration_ms', 3000),
                    'file_size': segment.get('file_size', 0),
                    'codec': segment.get('codec', 'h264'),
                    'resolution': segment.get('resolution', '1920x1080')
                })

            logger.info(f"Found {len(playback_segments)} segments for {camera_id}")
            return playback_segments

        except Exception as e:
            logger.error(f"Failed to get segments for playback: {e}", exc_info=True)
            return []
    
    def generate_hls_playlist(self, camera_id: str, segments: List[Dict],
                             base_url: str = "http://localhost:3000") -> str:
        """
        Generate HLS M3U8 playlist from segments

        Args:
            camera_id: Camera identifier
            segments: List of segment dicts
            base_url: Base URL for segment paths

        Returns:
            M3U8 playlist content
        """
        try:
            if not segments:
                logger.warning(f"No segments to generate playlist for {camera_id}")
                return ""

            # Calculate actual total duration (accounting for overlapping segments)
            first_segment_start = datetime.fromisoformat(segments[0].get('start_time', ''))
            last_segment = segments[-1]
            last_segment_start = datetime.fromisoformat(last_segment.get('start_time', ''))
            last_segment_duration_ms = last_segment.get('duration_ms', 3000)
            last_segment_end = last_segment_start + timedelta(milliseconds=last_segment_duration_ms)
            total_duration_sec = (last_segment_end - first_segment_start).total_seconds()

            # HLS playlist header
            playlist = "#EXTM3U\n"
            playlist += "#EXT-X-VERSION:3\n"
            playlist += "#EXT-X-TARGETDURATION:4\n"
            playlist += "#EXT-X-MEDIA-SEQUENCE:0\n"
            playlist += "#EXT-X-PLAYLIST-TYPE:VOD\n"

            # Add all segments with their actual durations based on gaps between segments
            for i, segment in enumerate(segments):
                segment_path = segment.get('segment_path', '')
                segment_start = datetime.fromisoformat(segment.get('start_time', ''))

                # Calculate duration based on gap to next segment (or use segment duration for last segment)
                if i < len(segments) - 1:
                    next_segment_start = datetime.fromisoformat(segments[i + 1].get('start_time', ''))
                    duration_sec = (next_segment_start - segment_start).total_seconds()
                else:
                    # For last segment, use its actual duration
                    duration_sec = segment.get('duration_ms', 3000) / 1000.0

                # Convert absolute path to relative URL
                if segment_path.startswith('D:\\') or segment_path.startswith('/'):
                    # Extract relative path from storage
                    try:
                        rel_path = Path(segment_path).relative_to(self.storage_path)
                        rel_path_parts = rel_path.parts
                        if len(rel_path_parts) > 1 and rel_path_parts[0] == camera_id:
                            rel_path_without_camera = Path(*rel_path_parts[1:])
                        else:
                            rel_path_without_camera = rel_path

                        rel_path_url = str(rel_path_without_camera).replace('\\', '/')
                        segment_url = f"{base_url}/api/playback/segment/{camera_id}/{rel_path_url}"
                    except ValueError:
                        segment_url = f"{base_url}/api/playback/segment/{camera_id}/{Path(segment_path).name}"
                else:
                    segment_url = f"{base_url}/api/playback/segment/{camera_id}/{segment_path}"

                playlist += f"#EXTINF:{duration_sec:.3f},\n"
                playlist += f"{segment_url}\n"

            playlist += f"#EXT-X-ENDLIST\n"

            logger.info(f"Generated HLS playlist with {len(segments)} segments, total duration: {total_duration_sec:.1f}s")
            return playlist

        except Exception as e:
            logger.error(f"Failed to generate HLS playlist: {e}", exc_info=True)
            return ""
    
    def get_segment_file(self, camera_id: str, segment_path: str) -> Optional[bytes]:
        """
        Get segment file content

        Args:
            camera_id: Camera identifier
            segment_path: Relative path to segment (URL format with forward slashes)
                         e.g., "2025-11-11/00-00-00-042_xxx.mp4"

        Returns:
            File content as bytes, or None if not found
        """
        try:
            # Convert URL path (forward slashes) to OS path (backslashes on Windows)
            os_segment_path = segment_path.replace('/', os.sep)

            # Construct full path: storage_path / camera_id / date / filename
            full_path = self.storage_path / camera_id / os_segment_path

            # Security: prevent path traversal
            if not str(full_path).startswith(str(self.storage_path)):
                logger.error(f"Security: Attempted path traversal: {full_path}")
                return None

            # Check if file exists
            if not full_path.exists():
                logger.warning(f"Segment file not found: {full_path}")
                return None

            # Read and return the segment file
            # Duration is handled by the API (playback_info.total_duration_ms)
            # and custom player controls, not by MP4 file metadata
            with open(full_path, 'rb') as f:
                content = f.read()
            logger.debug(f"Served segment: {full_path} ({len(content)} bytes)")
            return content

        except Exception as e:
            logger.error(f"Failed to read segment file: {e}", exc_info=True)
            return None
    
    def validate_time_range(self, start_time: datetime, end_time: datetime,
                           max_duration_hours: int = 24) -> bool:
        """
        Validate time range for playback

        Args:
            start_time: Start time
            end_time: End time
            max_duration_hours: Maximum allowed duration

        Returns:
            True if valid, False otherwise
        """
        try:
            # Check if times are in correct order
            if start_time >= end_time:
                logger.warning(f"Invalid time range: start >= end ({start_time} >= {end_time})")
                return False

            # Check if duration is within limits
            duration = end_time - start_time
            max_duration = timedelta(hours=max_duration_hours)

            if duration > max_duration:
                logger.warning(f"Time range too large: {duration} > {max_duration}")
                return False

            # Note: We allow querying for times in the future (e.g., "last hour" preset)
            # The database will simply return no segments if there are no recordings in that time range
            # This is the expected behavior - not an error

            logger.debug(f"Time range valid: {start_time} to {end_time} (duration: {duration})")
            return True

        except Exception as e:
            logger.error(f"Failed to validate time range: {e}")
            return False
    
    def get_playback_info(self, camera_id: str, start_time: datetime,
                         end_time: datetime) -> Dict:
        """
        Get complete playback information

        Args:
            camera_id: Camera identifier
            start_time: Start time
            end_time: End time

        Returns:
            Dict with playback info (segments, playlist, metadata)
        """
        try:
            logger.info(f"Getting playback info for {camera_id}: {start_time} to {end_time}")

            # Validate time range
            if not self.validate_time_range(start_time, end_time):
                logger.warning(f"Time range validation failed for {camera_id}")
                return {'error': 'Invalid time range'}

            # Get segments
            logger.debug(f"Fetching segments for {camera_id}")
            segments = self.get_segments_for_playback(camera_id, start_time, end_time)
            
            if not segments:
                return {
                    'camera_id': camera_id,
                    'start_time': start_time.isoformat(),
                    'end_time': end_time.isoformat(),
                    'segments': [],
                    'error': 'No segments found for time range'
                }
            
            # Generate playlist
            playlist = self.generate_hls_playlist(camera_id, segments)

            # Calculate total duration based on actual time span (not sum of segment durations)
            # This accounts for overlapping segments from multiple streams
            if segments:
                first_segment_start = datetime.fromisoformat(segments[0].get('start_time', ''))
                last_segment = segments[-1]
                last_segment_start = datetime.fromisoformat(last_segment.get('start_time', ''))
                last_segment_duration_ms = last_segment.get('duration_ms', 3000)
                last_segment_end = last_segment_start + timedelta(milliseconds=last_segment_duration_ms)

                # Total duration = last segment end - first segment start
                total_duration_ms = int((last_segment_end - first_segment_start).total_seconds() * 1000)
            else:
                total_duration_ms = 0

            return {
                'camera_id': camera_id,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'segment_count': len(segments),
                'total_duration_ms': total_duration_ms,
                'total_size_bytes': sum(s.get('file_size', 0) for s in segments),
                'segments': segments,
                'playlist_url': f'/api/playback/{camera_id}/playlist.m3u8?start_time={start_time.isoformat()}&end_time={end_time.isoformat()}'
            }
            
        except Exception as e:
            logger.error(f"Failed to get playback info: {e}", exc_info=True)
            return {'error': str(e)}

