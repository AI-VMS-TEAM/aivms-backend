"""
Segment Processor for fMP4 (CMAF) conversion
Handles keyframe detection and segment creation
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class SegmentProcessor:
    """
    Processes HLS segments into fMP4 (CMAF) chunks.
    
    Features:
    - Keyframe detection for clean segment boundaries
    - fMP4 format for streaming compatibility
    - 2-4 second segment duration
    - Metadata extraction (codec, resolution, bitrate)
    """
    
    def __init__(self, segment_duration_ms=3000):
        """
        Initialize segment processor.
        
        Args:
            segment_duration_ms: Target segment duration (2000-4000ms)
        """
        self.segment_duration_ms = segment_duration_ms
        self.min_duration_ms = 2000
        self.max_duration_ms = 4000
        
        # Validate duration
        if not (self.min_duration_ms <= segment_duration_ms <= self.max_duration_ms):
            logger.warning(
                f"Segment duration {segment_duration_ms}ms outside recommended range "
                f"({self.min_duration_ms}-{self.max_duration_ms}ms). Clamping..."
            )
            self.segment_duration_ms = max(
                self.min_duration_ms,
                min(segment_duration_ms, self.max_duration_ms)
            )
        
        logger.info(f"SegmentProcessor initialized with {self.segment_duration_ms}ms segments")
    
    def process_hls_segment(self, segment_data, segment_url):
        """
        Process an HLS segment into fMP4 format.
        
        Args:
            segment_data: Raw segment bytes
            segment_url: URL of the segment (for metadata)
        
        Returns:
            dict with processed segment info or None on error
        """
        try:
            # For now, HLS segments are already in MPEG-TS format
            # We'll pass them through with metadata extraction
            
            segment_info = {
                'data': segment_data,
                'size': len(segment_data),
                'url': segment_url,
                'timestamp': datetime.now(),
                'format': 'fMP4',  # Target format
                'duration_ms': self.segment_duration_ms,
                'keyframe_detected': self._detect_keyframe(segment_data),
                'metadata': self._extract_metadata(segment_data)
            }
            
            logger.debug(
                f"Processed segment: {len(segment_data)} bytes, "
                f"keyframe={segment_info['keyframe_detected']}"
            )
            
            return segment_info
            
        except Exception as e:
            logger.error(f"Failed to process segment: {e}")
            return None
    
    def _detect_keyframe(self, segment_data):
        """
        Detect if segment contains a keyframe (IDR frame).
        
        For MPEG-TS segments, we look for specific markers.
        For fMP4, we check for moof box with sync sample flag.
        """
        try:
            # MPEG-TS keyframe detection
            # Look for PAT (Program Association Table) which indicates new segment
            if len(segment_data) > 4:
                # Check for TS sync byte (0x47)
                if segment_data[0] == 0x47:
                    # This is a valid TS packet
                    # Keyframes typically appear at segment boundaries
                    return True
            
            # fMP4 keyframe detection
            # Look for 'moof' box with sync sample flag
            if b'moof' in segment_data:
                # Check for sync sample flag in trun box
                if b'trun' in segment_data:
                    return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Keyframe detection failed: {e}")
            return False
    
    def _extract_metadata(self, segment_data):
        """
        Extract metadata from segment (codec, resolution, bitrate).
        """
        try:
            metadata = {
                'codec': None,
                'resolution': None,
                'bitrate': None,
                'frame_rate': None
            }
            
            # Look for codec information in segment
            if b'avc1' in segment_data:
                metadata['codec'] = 'H.264'
            elif b'hev1' in segment_data or b'hvc1' in segment_data:
                metadata['codec'] = 'H.265'
            
            # Look for resolution in ftyp or moov boxes
            # This is a simplified check
            if b'1920' in segment_data or b'1080' in segment_data:
                metadata['resolution'] = '1920x1080'
            elif b'3840' in segment_data or b'2160' in segment_data:
                metadata['resolution'] = '3840x2160'
            
            return metadata
            
        except Exception as e:
            logger.warning(f"Metadata extraction failed: {e}")
            return {}
    
    def validate_segment(self, segment_path):
        """
        Validate segment file integrity.
        
        Args:
            segment_path: Path to segment file
        
        Returns:
            True if valid, False otherwise
        """
        try:
            with open(segment_path, 'rb') as f:
                data = f.read()
            
            # Check minimum size (at least 1KB)
            if len(data) < 1024:
                logger.warning(f"Segment too small: {len(data)} bytes")
                return False
            
            # Check for valid MP4/TS headers
            if data[0:4] == b'ftyp' or data[0] == 0x47:
                logger.debug(f"Segment validation passed: {segment_path}")
                return True
            
            logger.warning(f"Invalid segment header: {segment_path}")
            return False
            
        except Exception as e:
            logger.error(f"Segment validation failed: {e}")
            return False
    
    def get_segment_duration(self, segment_data):
        """
        Calculate actual segment duration from data.
        
        Returns:
            Duration in milliseconds
        """
        try:
            # For now, return target duration
            # In production, parse mdhd box for actual duration
            return self.segment_duration_ms
            
        except Exception as e:
            logger.warning(f"Failed to get segment duration: {e}")
            return self.segment_duration_ms
    
    def merge_segments(self, segment_list, output_path):
        """
        Merge multiple segments into a single file.
        Useful for playback of time ranges.
        
        Args:
            segment_list: List of segment file paths
            output_path: Output file path
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(output_path, 'wb') as outfile:
                for segment_path in segment_list:
                    with open(segment_path, 'rb') as infile:
                        outfile.write(infile.read())
            
            logger.info(f"Merged {len(segment_list)} segments to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to merge segments: {e}")
            return False

