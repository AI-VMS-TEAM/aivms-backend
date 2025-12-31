"""
Storage Configuration Module
Centralized management of recording storage paths
"""

import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Get recordings path from environment variable or use default
# Priority: Environment variable > Default D drive
RECORDINGS_BASE_PATH = os.getenv(
    'RECORDINGS_PATH',
    'D:\\recordings'  # Default to D drive (dedicated recordings partition)
)

# Ensure base path exists
try:
    Path(RECORDINGS_BASE_PATH).mkdir(parents=True, exist_ok=True)
    logger.info(f"✅ Recordings storage configured at: {RECORDINGS_BASE_PATH}")
except Exception as e:
    logger.error(f"❌ Failed to create recordings directory: {e}")
    raise

# Database path
RECORDINGS_DB_PATH = os.path.join(RECORDINGS_BASE_PATH, "recordings.db")

# Camera-specific paths
CAMERA_PATHS = {
    'wisenet_front': os.path.join(RECORDINGS_BASE_PATH, 'wisenet_front'),
    'dahua_front_cam': os.path.join(RECORDINGS_BASE_PATH, 'dahua_front_cam'),
    'bosch_front_cam': os.path.join(RECORDINGS_BASE_PATH, 'bosch_front_cam'),
    'axis_front_cam': os.path.join(RECORDINGS_BASE_PATH, 'axis_front_cam'),
}

# Ensure all camera paths exist
for camera_name, path in CAMERA_PATHS.items():
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        logger.debug(f"✅ Camera path ready: {camera_name} -> {path}")
    except Exception as e:
        logger.error(f"❌ Failed to create camera path for {camera_name}: {e}")
        raise


def get_camera_path(camera_name):
    """
    Get the storage path for a specific camera.
    
    Args:
        camera_name: Name of the camera
        
    Returns:
        Path to the camera's recording directory
    """
    path = CAMERA_PATHS.get(camera_name)
    if not path:
        # Fallback: create path dynamically
        path = os.path.join(RECORDINGS_BASE_PATH, camera_name)
        Path(path).mkdir(parents=True, exist_ok=True)
    return path


def get_disk_usage():
    """
    Get disk usage statistics for the recordings drive.
    
    Returns:
        Dictionary with usage information
    """
    try:
        import shutil
        stat = shutil.disk_usage(RECORDINGS_BASE_PATH)
        return {
            'total': stat.total,
            'used': stat.used,
            'free': stat.free,
            'percent_used': (stat.used / stat.total * 100) if stat.total > 0 else 0,
            'percent_free': (stat.free / stat.total * 100) if stat.total > 0 else 0,
        }
    except Exception as e:
        logger.error(f"Failed to get disk usage: {e}")
        return None


def get_storage_info():
    """
    Get comprehensive storage information.
    
    Returns:
        Dictionary with storage details
    """
    usage = get_disk_usage()
    if not usage:
        return None
    
    return {
        'base_path': RECORDINGS_BASE_PATH,
        'db_path': RECORDINGS_DB_PATH,
        'total_gb': usage['total'] / (1024**3),
        'used_gb': usage['used'] / (1024**3),
        'free_gb': usage['free'] / (1024**3),
        'percent_used': usage['percent_used'],
        'percent_free': usage['percent_free'],
        'cameras': CAMERA_PATHS,
    }


# Log storage configuration on module load
logger.info("=" * 60)
logger.info("STORAGE CONFIGURATION LOADED")
logger.info("=" * 60)
logger.info(f"Base Path: {RECORDINGS_BASE_PATH}")
logger.info(f"Database: {RECORDINGS_DB_PATH}")
logger.info(f"Cameras: {len(CAMERA_PATHS)}")
for camera_name, path in CAMERA_PATHS.items():
    logger.info(f"  - {camera_name}: {path}")

# Log disk usage
usage = get_disk_usage()
if usage:
    logger.info(f"Disk Usage: {usage['used'] / (1024**3):.1f} GB / {usage['total'] / (1024**3):.1f} GB ({usage['percent_used']:.1f}%)")
logger.info("=" * 60)

