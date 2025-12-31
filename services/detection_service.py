"""
Object Detection Service using RT-DETR

Extracts frames from HLS streams and runs RT-DETR inference.
Stores detections in SQLite database.

RT-DETR (Real-Time DEtection TRansformer) by Baidu:
- Apache 2.0 License (100% commercial-friendly)
- Better accuracy than YOLO11 (54.8 mAP vs 52.0 mAP)
- No NMS required (faster post-processing)
- Transformer-based architecture
"""

import logging
import threading
import time
import queue
import cv2
import numpy as np
from datetime import datetime
from pathlib import Path
from ultralytics import RTDETR
import sqlite3
import json

logger = logging.getLogger(__name__)


class DetectionService:
    """
    Runs RT-DETR object detection on video frames.
    Processes frames from a queue and stores detections in database.

    RT-DETR is commercially safe (Apache 2.0 license) and provides:
    - Better accuracy than YOLO11 (54.8 mAP vs 52.0 mAP)
    - Faster post-processing (no NMS required)
    - Transformer-based architecture for better small object detection
    """

    def __init__(self, db_path: str, model_name: str = "rtdetr-l",
                 confidence_threshold: float = 0.5, gpu_enabled: bool = True,
                 tracking_enabled: bool = False, tracker_config: str = "bytetrack.yaml",
                 pose_enabled: bool = True, kalman_smoothing: bool = True):
        """
        Initialize detection service.

        Args:
            db_path: Path to SQLite database
            model_name: RT-DETR model name (rtdetr-l, rtdetr-x, etc.)
            confidence_threshold: Minimum confidence for detections
            gpu_enabled: Whether to use GPU for inference
            tracking_enabled: Whether to enable ByteTrack tracking
            tracker_config: Path to tracker configuration file
            pose_enabled: Whether to enable pose detection for persons (uses YOLO11s-pose)
            kalman_smoothing: Whether to enable Kalman smoothing for stable boxes
        """
        self.db_path = db_path
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.gpu_enabled = gpu_enabled
        self.tracking_enabled = tracking_enabled
        self.tracker_config = tracker_config
        self.pose_enabled = pose_enabled
        self.kalman_smoothing = kalman_smoothing

        # Load RT-DETR model with GPU fallback
        logger.info(f"Loading RT-DETR model: {model_name}")
        try:
            import torch
            # Check if GPU is actually available
            if gpu_enabled and torch.cuda.is_available():
                device = 0
                logger.info("✅ GPU detected and enabled for RT-DETR")
            else:
                device = "cpu"
                if gpu_enabled:
                    logger.warning("⚠️ GPU requested but not available, falling back to CPU")
                else:
                    logger.info("Using CPU for inference")
        except Exception as e:
            logger.warning(f"Error checking GPU availability: {e}, using CPU")
            device = "cpu"

        self.model = RTDETR(f"{model_name}.pt")
        self.model.to(device)
        self.device = device

        # Initialize pose detection if enabled (uses YOLO11s-pose for pose keypoints)
        # Note: RT-DETR is for object detection only, pose detection still uses YOLO
        self.pose_service = None
        if pose_enabled:
            try:
                from services.pose_detection_service import PoseDetectionService
                # Use YOLO11s-pose for pose detection (RT-DETR doesn't have pose variant)
                pose_model = 'yolo11s-pose'
                self.pose_service = PoseDetectionService(
                    model_name=pose_model,
                    confidence_threshold=confidence_threshold,
                    gpu_enabled=gpu_enabled
                )
                logger.info("✅ Pose detection enabled (using YOLO11s-pose)")
            except Exception as e:
                logger.warning(f"⚠️ Failed to initialize pose detection: {e}")
                self.pose_service = None

        # Initialize Kalman smoothing if enabled
        self.smooth_tracker = None
        if kalman_smoothing and tracking_enabled:
            try:
                from services.smooth_tracker import SmoothTracker
                self.smooth_tracker = SmoothTracker(max_age=30)
                logger.info("✅ Kalman smoothing enabled for stable tracking")
            except Exception as e:
                logger.warning(f"⚠️ Failed to initialize Kalman smoothing: {e}")
                self.smooth_tracker = None

        # Initialize camera calibration service
        self.calibration_service = None
        try:
            from services.camera_calibration_service import CameraCalibrationService
            self.calibration_service = CameraCalibrationService()
            logger.info("✅ Camera calibration service initialized")
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize calibration service: {e}")
            self.calibration_service = None

        # Frame queue for processing
        self.frame_queue = queue.Queue(maxsize=30)
        self.is_running = False
        self.detection_thread = None

        # Integration callback (for tracking)
        self.on_detections_callback = None

        # WebSocket callback (for real-time streaming)
        self.on_detections_websocket_callback = None

        # Statistics
        self.frames_processed = 0
        self.detections_stored = 0

        # Performance metrics
        self.inference_times = []  # Store last 100 inference times
        self.max_inference_times = 100
        self.last_fps_calculation = time.time()
        self.frames_since_last_fps = 0
        self.current_fps = 0.0
        self.total_inference_time = 0.0

        logger.info(f"RT-DETR detection service initialized with {model_name} on {'GPU' if gpu_enabled else 'CPU'}")
        logger.info(f"📜 License: Apache 2.0 (100% commercial-friendly)")

    def start(self):
        """Start the detection service."""
        if self.is_running:
            logger.warning("Detection service already running")
            return
        
        self.is_running = True
        self.detection_thread = threading.Thread(
            target=self._detection_loop,
            daemon=True,
            name="DetectionThread"
        )
        self.detection_thread.start()
        logger.info("Detection service started")

    def stop(self):
        """Stop the detection service."""
        self.is_running = False
        if self.detection_thread:
            self.detection_thread.join(timeout=5)
        logger.info("Detection service stopped")

    def add_frame(self, camera_id: str, frame: np.ndarray, timestamp: float):
        """
        Add a frame for detection.
        
        Args:
            camera_id: Camera identifier
            frame: Video frame (numpy array)
            timestamp: Frame timestamp (seconds since epoch)
        """
        try:
            self.frame_queue.put_nowait((camera_id, frame, timestamp))
        except queue.Full:
            logger.debug("Frame queue full, dropping frame")

    def _detection_loop(self):
        """Main detection loop - runs in separate thread."""
        while self.is_running:
            try:
                # Get frame from queue with timeout
                camera_id, frame, timestamp = self.frame_queue.get(timeout=1)

                # Measure inference time
                inference_start = time.time()

                # Run YOLO inference with or without tracking
                if self.tracking_enabled:
                    # Use ByteTrack tracking
                    results = self.model.track(
                        frame,
                        conf=self.confidence_threshold,
                        persist=True,
                        tracker=self.tracker_config,
                        verbose=False
                    )
                else:
                    # Standard detection without tracking
                    results = self.model(frame, conf=self.confidence_threshold, verbose=False)

                # Calculate inference time
                inference_time = time.time() - inference_start
                self.total_inference_time += inference_time

                # Store inference time for statistics (keep last 100)
                self.inference_times.append(inference_time)
                if len(self.inference_times) > self.max_inference_times:
                    self.inference_times.pop(0)

                # Run pose detection for persons if enabled
                poses = []
                if self.pose_service:
                    try:
                        poses = self.pose_service.detect_poses(frame)
                    except Exception as e:
                        logger.warning(f"Pose detection failed: {e}")

                # Process detections (with or without track IDs)
                detections = []
                tracks = []
                for result in results:
                    boxes = result.boxes

                    # Check if tracking is enabled and track IDs are available
                    has_track_ids = self.tracking_enabled and boxes.is_track if hasattr(boxes, 'is_track') else False

                    for i in range(len(boxes)):
                        class_name = self.model.names[int(boxes.cls[i])]
                        detection = {
                            'camera_id': camera_id,
                            'timestamp': timestamp,
                            'class': class_name,
                            'confidence': float(boxes.conf[i]),
                            'bbox': [float(x) for x in boxes.xyxy[i].tolist()],  # [x1, y1, x2, y2]
                            'bbox_xywh': [float(x) for x in boxes.xywh[i].tolist()]  # [x_center, y_center, width, height]
                        }

                        # Add pose keypoints if this is a person
                        if class_name == 'person' and poses:
                            # Find matching pose by bbox overlap
                            det_bbox = detection['bbox']
                            best_match = None
                            best_iou = 0.3  # Minimum IoU threshold

                            for pose in poses:
                                iou = self._calculate_iou(det_bbox, pose['bbox'])
                                if iou > best_iou:
                                    best_iou = iou
                                    best_match = pose

                            if best_match:
                                detection['pose'] = {
                                    'keypoints': best_match['keypoints'],
                                    'visible_keypoints': best_match['visible_keypoints']
                                }

                        # Add track ID if available
                        if has_track_ids:
                            detection['track_id'] = int(boxes.id[i])
                            tracks.append(detection)

                        detections.append(detection)

                # Apply camera calibration filtering
                if self.calibration_service and detections:
                    try:
                        original_count = len(detections)
                        detections = self.calibration_service.filter_detections(camera_id, detections)
                        tracks = [d for d in detections if 'track_id' in d]
                        filtered_count = original_count - len(detections)
                        if filtered_count > 0:
                            logger.debug(f"🎯 [{camera_id}] Calibration filtered {filtered_count} detections")
                    except Exception as e:
                        logger.warning(f"Calibration filtering failed: {e}")

                # Apply Kalman smoothing to tracks if enabled
                smoothed_tracks = tracks
                if self.smooth_tracker and tracks:
                    try:
                        smoothed_tracks = self.smooth_tracker.update(tracks)
                        logger.debug(f"Applied Kalman smoothing to {len(smoothed_tracks)} tracks")
                    except Exception as e:
                        logger.warning(f"Kalman smoothing failed: {e}")
                        smoothed_tracks = tracks

                # Store detections in database
                if detections:
                    self._store_detections(detections)
                    self.detections_stored += len(detections)

                    # Emit to tracking service via callback (with track IDs if available)
                    if self.on_detections_callback:
                        if self.tracking_enabled and smoothed_tracks:
                            self.on_detections_callback(camera_id, smoothed_tracks, timestamp)
                        else:
                            self.on_detections_callback(camera_id, detections, timestamp)

                    # Emit to WebSocket clients for real-time streaming (use smoothed tracks)
                    if self.on_detections_websocket_callback:
                        self.on_detections_websocket_callback(camera_id, detections, timestamp, smoothed_tracks if self.tracking_enabled else None)

                self.frames_processed += 1
                self.frames_since_last_fps += 1

                # Calculate FPS every 5 seconds
                current_time = time.time()
                time_elapsed = current_time - self.last_fps_calculation
                if time_elapsed >= 5.0:
                    self.current_fps = self.frames_since_last_fps / time_elapsed
                    self.frames_since_last_fps = 0
                    self.last_fps_calculation = current_time

                    # Log performance metrics
                    avg_inference_time = sum(self.inference_times) / len(self.inference_times) if self.inference_times else 0
                    mode = "Tracking" if self.tracking_enabled else "Detection"
                    logger.info(f"{mode} Performance: {self.current_fps:.2f} FPS, "
                              f"Avg Inference: {avg_inference_time*1000:.1f}ms, "
                              f"Queue: {self.frame_queue.qsize()}/{self.frame_queue.maxsize}")

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in detection loop: {e}", exc_info=True)

    def _calculate_iou(self, bbox1: list, bbox2: list) -> float:
        """
        Calculate Intersection over Union (IoU) between two bounding boxes.

        Args:
            bbox1: [x1, y1, x2, y2]
            bbox2: [x1, y1, x2, y2]

        Returns:
            IoU score (0.0 - 1.0)
        """
        x1_min, y1_min, x1_max, y1_max = bbox1
        x2_min, y2_min, x2_max, y2_max = bbox2

        # Calculate intersection
        inter_x_min = max(x1_min, x2_min)
        inter_y_min = max(y1_min, y2_min)
        inter_x_max = min(x1_max, x2_max)
        inter_y_max = min(y1_max, y2_max)

        if inter_x_max < inter_x_min or inter_y_max < inter_y_min:
            return 0.0

        inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)

        # Calculate union
        bbox1_area = (x1_max - x1_min) * (y1_max - y1_min)
        bbox2_area = (x2_max - x2_min) * (y2_max - y2_min)
        union_area = bbox1_area + bbox2_area - inter_area

        if union_area == 0:
            return 0.0

        return inter_area / union_area

    def _store_detections(self, detections: list):
        """Store detections in SQLite database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for det in detections:
                cursor.execute("""
                    INSERT INTO detections 
                    (camera_id, timestamp, class, confidence, bbox)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    det['camera_id'],
                    det['timestamp'],
                    det['class'],
                    det['confidence'],
                    json.dumps(det['bbox'])
                ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error storing detections: {e}", exc_info=True)

    def set_detections_callback(self, callback):
        """Set callback for when detections are made (for tracking service)."""
        self.on_detections_callback = callback

    def set_websocket_callback(self, callback):
        """Set callback for WebSocket broadcasting of detections."""
        self.on_detections_websocket_callback = callback

    def get_stats(self) -> dict:
        """Get detection service statistics."""
        avg_inference_time = sum(self.inference_times) / len(self.inference_times) if self.inference_times else 0
        min_inference_time = min(self.inference_times) if self.inference_times else 0
        max_inference_time = max(self.inference_times) if self.inference_times else 0

        return {
            'model': self.model_name,
            'device': str(self.device),
            'frames_processed': self.frames_processed,
            'detections_stored': self.detections_stored,
            'queue_size': self.frame_queue.qsize(),
            'queue_max_size': self.frame_queue.maxsize,
            'is_running': self.is_running,
            'current_fps': round(self.current_fps, 2),
            'avg_inference_time_ms': round(avg_inference_time * 1000, 2),
            'min_inference_time_ms': round(min_inference_time * 1000, 2),
            'max_inference_time_ms': round(max_inference_time * 1000, 2),
            'total_inference_time_sec': round(self.total_inference_time, 2)
        }

