"""
Event Uploader Service
Handles uploading event clips from edge to cloud.
"""

import os
import time
import logging
import threading
import queue
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional
import requests

logger = logging.getLogger(__name__)


class EventUploader:
    """
    Manages uploading event clips to cloud.
    - Queues clip requests
    - Extracts clips from recordings
    - Uploads with retry logic
    """
    
    def __init__(
        self,
        cloud_url: str,
        edge_id: str,
        edge_secret: str,
        storage_path: str = './storage/recordings',
        max_queue_size: int = 100,
        upload_workers: int = 2
    ):
        self.cloud_url = cloud_url.rstrip('/')
        self.edge_id = edge_id
        self.edge_secret = edge_secret
        self.storage_path = storage_path
        
        self.upload_queue = queue.Queue(maxsize=max_queue_size)
        self._stop_event = threading.Event()
        self._workers = []
        
        # Statistics
        self.stats = {
            'clips_uploaded': 0,
            'clips_failed': 0,
            'bytes_uploaded': 0,
            'queue_size': 0
        }
        
        # Start upload workers
        for i in range(upload_workers):
            worker = threading.Thread(
                target=self._upload_worker,
                name=f'UploadWorker-{i}',
                daemon=True
            )
            worker.start()
            self._workers.append(worker)
        
        logger.info(f"✅ Event uploader initialized with {upload_workers} workers")
    
    def queue_clip(self, detection_event: Dict):
        """Queue a clip for upload based on detection event."""
        camera_id = detection_event.get('camera_id')
        timestamp = detection_event.get('timestamp')
        
        if not camera_id or not timestamp:
            logger.warning("Invalid detection event for clip upload")
            return False
        
        # Calculate clip time range
        event_time = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp
        start_time = event_time - timedelta(seconds=5)  # 5 seconds before
        end_time = event_time + timedelta(seconds=10)   # 10 seconds after
        
        clip_request = {
            'type': 'detection_clip',
            'camera_id': camera_id,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'event': detection_event,
            'priority': self._calculate_priority(detection_event)
        }
        
        try:
            self.upload_queue.put_nowait(clip_request)
            self.stats['queue_size'] = self.upload_queue.qsize()
            logger.info(f"📎 Queued clip for {camera_id} ({start_time} - {end_time})")
            return True
        except queue.Full:
            logger.warning("Upload queue full, dropping clip request")
            return False
    
    def queue_clip_request(self, camera_id: str, start_time: str, end_time: str):
        """Queue a clip request from cloud."""
        clip_request = {
            'type': 'requested_clip',
            'camera_id': camera_id,
            'start_time': start_time,
            'end_time': end_time,
            'priority': 10  # High priority for cloud requests
        }
        
        try:
            self.upload_queue.put_nowait(clip_request)
            self.stats['queue_size'] = self.upload_queue.qsize()
            logger.info(f"📎 Queued requested clip for {camera_id}")
            return True
        except queue.Full:
            logger.warning("Upload queue full")
            return False
    
    def _calculate_priority(self, detection_event: Dict) -> int:
        """Calculate upload priority (higher = more urgent)."""
        priority = 1
        
        detections = detection_event.get('detections', [])
        for detection in detections:
            class_name = detection.get('class_name', '')
            confidence = detection.get('confidence', 0)
            
            # Higher priority for persons
            if class_name == 'person':
                priority += 3
            elif class_name in ['vehicle', 'truck', 'car']:
                priority += 2
            
            # Higher priority for high confidence
            if confidence > 0.8:
                priority += 2
            elif confidence > 0.6:
                priority += 1
            
            # Zone violations are urgent
            if detection.get('zone_violation'):
                priority += 5
        
        return min(priority, 10)  # Cap at 10
    
    def _upload_worker(self):
        """Worker thread that processes upload queue."""
        while not self._stop_event.is_set():
            try:
                # Get next clip request (with timeout for clean shutdown)
                clip_request = self.upload_queue.get(timeout=1.0)
                self.stats['queue_size'] = self.upload_queue.qsize()
                
                # Extract and upload clip
                self._process_clip_request(clip_request)
                
                self.upload_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Upload worker error: {e}")
    
    def _process_clip_request(self, clip_request: Dict):
        """Process a single clip request."""
        camera_id = clip_request['camera_id']
        start_time = clip_request['start_time']
        end_time = clip_request['end_time']
        
        logger.info(f"📹 Processing clip: {camera_id} ({start_time} - {end_time})")
        
        # Extract clip from recordings
        clip_path = self._extract_clip(camera_id, start_time, end_time)
        
        if not clip_path or not os.path.exists(clip_path):
            logger.error(f"Failed to extract clip for {camera_id}")
            self.stats['clips_failed'] += 1
            return
        
        # Upload to cloud
        success = self._upload_clip(clip_path, clip_request)
        
        if success:
            self.stats['clips_uploaded'] += 1
            logger.info(f"✅ Uploaded clip: {camera_id}")
        else:
            self.stats['clips_failed'] += 1
            logger.error(f"❌ Failed to upload clip: {camera_id}")
        
        # Clean up temporary clip file
        try:
            os.remove(clip_path)
        except Exception as e:
            logger.warning(f"Failed to clean up clip file: {e}")
    
    def _extract_clip(
        self,
        camera_id: str,
        start_time: str,
        end_time: str
    ) -> Optional[str]:
        """Extract a clip from recorded segments."""
        try:
            import subprocess
            
            # Parse times
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
            duration = (end_dt - start_dt).total_seconds()
            
            # Find relevant segment files
            date_str = start_dt.strftime('%Y-%m-%d')
            camera_path = os.path.join(self.storage_path, camera_id, date_str)
            
            if not os.path.exists(camera_path):
                logger.warning(f"No recordings found for {camera_id} on {date_str}")
                return None
            
            # Find segments in time range
            segment_files = []
            for f in sorted(os.listdir(camera_path)):
                if f.endswith('.mp4'):
                    segment_files.append(os.path.join(camera_path, f))
            
            if not segment_files:
                logger.warning(f"No segments found for {camera_id}")
                return None
            
            # Create output clip
            output_dir = os.path.join(self.storage_path, 'clips')
            os.makedirs(output_dir, exist_ok=True)
            
            clip_filename = f"{camera_id}_{start_dt.strftime('%Y%m%d_%H%M%S')}.mp4"
            clip_path = os.path.join(output_dir, clip_filename)
            
            # Use FFmpeg to extract clip
            # For simplicity, concatenate segments and trim
            # In production, you'd use more sophisticated segment selection
            
            # Create file list for FFmpeg
            list_file = os.path.join(output_dir, 'concat_list.txt')
            with open(list_file, 'w') as f:
                for seg in segment_files[:10]:  # Limit to avoid huge clips
                    f.write(f"file '{seg}'\n")
            
            # FFmpeg command to extract clip
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat', '-safe', '0',
                '-i', list_file,
                '-t', str(min(duration, 30)),  # Max 30 seconds
                '-c', 'copy',
                clip_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=60)
            
            # Clean up list file
            os.remove(list_file)
            
            if result.returncode == 0 and os.path.exists(clip_path):
                return clip_path
            else:
                logger.error(f"FFmpeg failed: {result.stderr.decode()}")
                return None
            
        except Exception as e:
            logger.error(f"Clip extraction failed: {e}")
            return None
    
    def _upload_clip(self, clip_path: str, clip_request: Dict) -> bool:
        """Upload clip to cloud server."""
        try:
            file_size = os.path.getsize(clip_path)
            
            # Prepare upload
            upload_url = f"{self.cloud_url}/api/edge/clips"
            
            headers = {
                'X-Edge-ID': self.edge_id,
                'X-Edge-Secret': self.edge_secret
            }
            
            metadata = {
                'camera_id': clip_request['camera_id'],
                'start_time': clip_request['start_time'],
                'end_time': clip_request['end_time'],
                'event_type': clip_request.get('type', 'detection_clip'),
                'file_size': file_size
            }
            
            # Add event data if present
            if 'event' in clip_request:
                metadata['event'] = clip_request['event']
            
            # Upload with retries
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    with open(clip_path, 'rb') as f:
                        files = {'clip': (os.path.basename(clip_path), f, 'video/mp4')}
                        data = {'metadata': str(metadata)}
                        
                        response = requests.post(
                            upload_url,
                            headers=headers,
                            files=files,
                            data=data,
                            timeout=120
                        )
                    
                    if response.status_code == 200:
                        self.stats['bytes_uploaded'] += file_size
                        return True
                    elif response.status_code == 401:
                        logger.error("Authentication failed with cloud")
                        return False
                    else:
                        logger.warning(f"Upload failed (attempt {attempt+1}): {response.status_code}")
                
                except requests.Timeout:
                    logger.warning(f"Upload timeout (attempt {attempt+1})")
                except requests.RequestException as e:
                    logger.warning(f"Upload error (attempt {attempt+1}): {e}")
                
                # Wait before retry
                time.sleep(2 ** attempt)
            
            return False
            
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return False
    
    def stop(self):
        """Stop the uploader."""
        self._stop_event.set()
        for worker in self._workers:
            worker.join(timeout=5)
    
    def get_stats(self) -> Dict:
        """Get upload statistics."""
        return {
            **self.stats,
            'queue_size': self.upload_queue.qsize()
        }
