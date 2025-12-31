"""
Segment validation service
Validates file integrity using checksums and detects corrupted segments
"""

import hashlib
import logging
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of segment validation"""
    file_path: str
    is_valid: bool
    file_size: int
    checksum: str
    error_message: Optional[str] = None
    
    def to_dict(self):
        return {
            'file_path': self.file_path,
            'is_valid': self.is_valid,
            'file_size': self.file_size,
            'checksum': self.checksum,
            'error_message': self.error_message,
        }


class SegmentValidator:
    """
    Validates segment file integrity using checksums.
    Detects corrupted files and maintains validation history.
    """
    
    def __init__(self, storage_path: str, history_size: int = 1000):
        """
        Initialize segment validator.

        Args:
            storage_path: Path to recordings directory
            history_size: Number of validation results to keep
        """
        self.storage_path = Path(storage_path)
        self.history_size = history_size
        self.lock = threading.Lock()

        # Validation history
        self.validation_history = deque(maxlen=history_size)
        self.corrupted_files = {}  # file_path -> ValidationResult

        # Statistics
        self.total_validated = 0
        self.total_corrupted = 0
        self.last_validation_time = None

        # Background validation tracking
        self.validated_files: Set[str] = set()  # Track validated file paths
        self.is_running = False
        self.validation_thread = None
        self.validation_interval_seconds = 300  # Validate every 5 minutes

        logger.info(f"SegmentValidator initialized for {storage_path}")
    
    def validate_segment(self, file_path: str, fast_mode: bool = False) -> ValidationResult:
        """
        Validate a single segment file.

        Args:
            file_path: Path to segment file
            fast_mode: If True, skip checksum calculation for speed (default: False)

        Returns:
            ValidationResult with validation status
        """
        # Debug logging
        if fast_mode:
            logger.debug(f"validate_segment called with fast_mode=True for {file_path}")
        try:
            path = Path(file_path)
            
            # Check if file exists
            if not path.exists():
                result = ValidationResult(
                    file_path=file_path,
                    is_valid=False,
                    file_size=0,
                    checksum='',
                    error_message='File does not exist'
                )
                self._record_validation(result)
                return result
            
            # Check if file is readable
            if not path.is_file():
                result = ValidationResult(
                    file_path=file_path,
                    is_valid=False,
                    file_size=0,
                    checksum='',
                    error_message='Path is not a file'
                )
                self._record_validation(result)
                return result
            
            # Get file size
            file_size = path.stat().st_size

            # Validate file has content
            if file_size == 0:
                result = ValidationResult(
                    file_path=file_path,
                    is_valid=False,
                    file_size=0,
                    checksum='',
                    error_message='File is empty'
                )
                self._record_validation(result)
                return result

            # In fast mode, skip checksum calculation
            if fast_mode:
                result = ValidationResult(
                    file_path=file_path,
                    is_valid=True,
                    file_size=file_size,
                    checksum='',  # Skip checksum in fast mode
                )
                self._record_validation(result)
                return result

            # Calculate checksum (full validation)
            try:
                checksum = self._calculate_checksum(file_path)
                result = ValidationResult(
                    file_path=file_path,
                    is_valid=True,
                    file_size=file_size,
                    checksum=checksum,
                )
                self._record_validation(result)
                return result

            except Exception as e:
                result = ValidationResult(
                    file_path=file_path,
                    is_valid=False,
                    file_size=0,
                    checksum='',
                    error_message=f'Checksum calculation failed: {str(e)}'
                )
                self._record_validation(result)
                return result
                
        except Exception as e:
            result = ValidationResult(
                file_path=file_path,
                is_valid=False,
                file_size=0,
                checksum='',
                error_message=f'Validation error: {str(e)}'
            )
            self._record_validation(result)
            return result
    
    def _calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA256 checksum of file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for byte_block in iter(lambda: f.read(4096), b''):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def _record_validation(self, result: ValidationResult):
        """Record validation result."""
        with self.lock:
            self.validation_history.append(result)
            self.total_validated += 1

            if not result.is_valid:
                self.total_corrupted += 1
                self.corrupted_files[result.file_path] = result
            else:
                # Remove from corrupted if it was previously corrupted
                self.corrupted_files.pop(result.file_path, None)

            self.last_validation_time = time.time()

            # Debug logging every 1000 validations
            if self.total_validated % 1000 == 0:
                logger.info(f"_record_validation: total_validated={self.total_validated}, last_validation_time={self.last_validation_time}")
    
    def validate_directory(self, directory_path: str, pattern: str = '*.mp4') -> Dict:
        """
        Validate all segments in a directory.
        
        Args:
            directory_path: Path to directory
            pattern: File pattern to match (default: *.mp4)
            
        Returns:
            Dictionary with validation summary
        """
        try:
            dir_path = Path(directory_path)
            if not dir_path.exists():
                return {
                    'total_files': 0,
                    'valid_files': 0,
                    'corrupted_files': 0,
                    'percent_valid': 0.0,
                    'error': f'Directory does not exist: {directory_path}'
                }
            
            # Find all matching files
            files = list(dir_path.glob(f'**/{pattern}'))
            
            valid_count = 0
            corrupted_count = 0
            
            for file_path in files:
                result = self.validate_segment(str(file_path))
                if result.is_valid:
                    valid_count += 1
                else:
                    corrupted_count += 1
            
            total = len(files)
            percent_valid = (valid_count / total * 100) if total > 0 else 0
            
            return {
                'total_files': total,
                'valid_files': valid_count,
                'corrupted_files': corrupted_count,
                'percent_valid': round(percent_valid, 2),
                'directory': directory_path,
            }
            
        except Exception as e:
            logger.error(f"Error validating directory {directory_path}: {e}")
            return {
                'total_files': 0,
                'valid_files': 0,
                'corrupted_files': 0,
                'percent_valid': 0.0,
                'error': str(e)
            }
    
    def get_corrupted_files(self) -> List[Dict]:
        """Get list of corrupted files."""
        with self.lock:
            return [result.to_dict() for result in self.corrupted_files.values()]
    
    def get_validation_stats(self) -> Dict:
        """Get validation statistics."""
        with self.lock:
            stats = {
                'total_validated': self.total_validated,
                'total_corrupted': self.total_corrupted,
                'percent_valid': round(
                    ((self.total_validated - self.total_corrupted) / self.total_validated * 100)
                    if self.total_validated > 0 else 0,
                    2
                ),
                'last_validation_time': self.last_validation_time,
                'corrupted_files_count': len(self.corrupted_files),
            }
            logger.info(f"get_validation_stats called: total_validated={stats['total_validated']}, total_corrupted={stats['total_corrupted']}")
            return stats
    
    def get_validation_history(self, limit: int = 100) -> List[Dict]:
        """Get recent validation results."""
        with self.lock:
            history = list(self.validation_history)[-limit:]
            return [r.to_dict() for r in history]

    def start_background_validation(self, interval_seconds: int = 300):
        """
        Start background validation thread.

        Args:
            interval_seconds: How often to validate new segments (default 5 minutes)
        """
        if self.is_running:
            logger.warning("Background validation already running")
            return

        self.validation_interval_seconds = interval_seconds
        self.is_running = True
        self.validation_thread = threading.Thread(
            target=self._background_validation_loop,
            daemon=True,
            name="SegmentValidationThread"
        )
        self.validation_thread.start()
        logger.info(f"Background validation started (interval: {interval_seconds}s)")

    def stop_background_validation(self):
        """Stop background validation thread."""
        self.is_running = False
        if self.validation_thread:
            self.validation_thread.join(timeout=5)
        logger.info("Background validation stopped")

    def _background_validation_loop(self):
        """Main background validation loop."""
        # Run validation immediately on startup
        try:
            self._validate_new_segments()
        except Exception as e:
            logger.error(f"Error in initial background validation: {e}")

        # Then run periodically
        while self.is_running:
            try:
                time.sleep(self.validation_interval_seconds)
                self._validate_new_segments()
            except Exception as e:
                logger.error(f"Error in background validation loop: {e}")

    def _validate_new_segments(self):
        """Find and validate new segments that haven't been validated yet."""
        try:
            if not self.storage_path.exists():
                logger.warning(f"Storage path does not exist: {self.storage_path}")
                return

            # Find all MP4 files in storage
            all_files = list(self.storage_path.glob('**/*.mp4'))
            logger.info(f"Background validation: Found {len(all_files)} total MP4 files")

            # Find files that haven't been validated yet
            new_files = []
            with self.lock:
                for file_path in all_files:
                    file_str = str(file_path)
                    if file_str not in self.validated_files:
                        new_files.append(file_str)
                logger.info(f"Background validation: {len(self.validated_files)} already validated, {len(new_files)} new files to validate")

            # Validate new files in batches with progress logging
            # Use fast_mode=True to skip checksum calculation for speed
            if new_files:
                logger.info(f"Found {len(new_files)} new segments to validate (using fast mode)")
                batch_size = 500  # Larger batch size for fast mode
                for i, file_path in enumerate(new_files):
                    try:
                        # Use fast_mode=True to skip checksum calculation
                        # validate_segment() calls _record_validation() internally
                        result = self.validate_segment(file_path, fast_mode=True)
                        # Track that we've validated this file
                        with self.lock:
                            self.validated_files.add(file_path)

                        # Log progress every 500 files
                        if (i + 1) % batch_size == 0:
                            with self.lock:
                                logger.info(f"Background validation progress: {i + 1}/{len(new_files)} files validated. Total validated: {self.total_validated}")
                    except Exception as e:
                        logger.error(f"Error validating segment {file_path}: {e}")
                        # Still mark as validated to avoid re-trying
                        with self.lock:
                            self.validated_files.add(file_path)

                # Log final completion
                with self.lock:
                    logger.info(f"Background validation batch complete: {len(new_files)} files processed. Total validated: {self.total_validated}")
            else:
                logger.info(f"Background validation: No new files to validate. Total validated so far: {self.total_validated}")

        except Exception as e:
            logger.error(f"Error in _validate_new_segments: {e}")

