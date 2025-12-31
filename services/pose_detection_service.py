"""
Pose Detection Service using YOLO11-Pose

Detects human poses with 17 keypoints for skeleton visualization.
Integrates with detection service for person class detections.
"""

import logging
import numpy as np
from ultralytics import YOLO
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class PoseDetectionService:
    """
    Runs YOLO-Pose detection for person keypoints.
    Returns 17 keypoints per person for skeleton visualization.
    """
    
    # COCO 17 keypoints
    KEYPOINT_NAMES = [
        'nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
        'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
        'left_wrist', 'right_wrist', 'left_hip', 'right_hip',
        'left_knee', 'right_knee', 'left_ankle', 'right_ankle'
    ]
    
    # Skeleton connections (pairs of keypoint indices)
    SKELETON = [
        (0, 1), (0, 2),  # nose to eyes
        (1, 3), (2, 4),  # eyes to ears
        (0, 5), (0, 6),  # nose to shoulders
        (5, 6),  # shoulders
        (5, 7), (7, 9),  # left arm
        (6, 8), (8, 10),  # right arm
        (5, 11), (6, 12),  # shoulders to hips
        (11, 12),  # hips
        (11, 13), (13, 15),  # left leg
        (12, 14), (14, 16),  # right leg
    ]

    def __init__(self, model_name: str = "yolo11s-pose", 
                 confidence_threshold: float = 0.5,
                 gpu_enabled: bool = True):
        """
        Initialize pose detection service.
        
        Args:
            model_name: YOLO-Pose model name (yolo11n-pose, yolo11s-pose, etc.)
            confidence_threshold: Minimum confidence for pose detections
            gpu_enabled: Whether to use GPU for inference
        """
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.gpu_enabled = gpu_enabled
        
        # Load YOLO-Pose model
        logger.info(f"Loading YOLO-Pose model: {model_name}")
        try:
            import torch
            if gpu_enabled and torch.cuda.is_available():
                device = 0
                logger.info("✅ GPU detected for pose detection")
            else:
                device = "cpu"
                if gpu_enabled:
                    logger.warning("⚠️ GPU requested but not available for pose, using CPU")
                else:
                    logger.info("Using CPU for pose detection")
        except Exception as e:
            logger.warning(f"Error checking GPU: {e}, using CPU")
            device = "cpu"
        
        self.model = YOLO(f"{model_name}.pt")
        self.model.to(device)
        self.device = device
        logger.info(f"✅ Pose detection model loaded on {device}")

    def detect_poses(self, frame: np.ndarray) -> List[Dict]:
        """
        Detect poses in frame.
        
        Args:
            frame: Video frame (numpy array)
            
        Returns:
            List of pose detections with keypoints
            [
                {
                    'bbox': [x1, y1, x2, y2],
                    'confidence': 0.95,
                    'keypoints': [[x, y, conf], ...],  # 17 keypoints
                    'visible_keypoints': 15  # Number of visible keypoints
                },
                ...
            ]
        """
        results = self.model(frame, conf=self.confidence_threshold, verbose=False)
        
        poses = []
        for result in results:
            if result.keypoints is None:
                continue
                
            boxes = result.boxes
            keypoints = result.keypoints
            
            for i in range(len(boxes)):
                box = boxes[i]
                kpts = keypoints[i]
                
                # Extract bounding box
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                confidence = float(box.conf[0])
                
                # Extract keypoints (17 x 3: x, y, confidence)
                kpts_data = kpts.data[0].cpu().numpy()  # Shape: (17, 3)
                keypoints_list = []
                visible_count = 0
                
                for j in range(17):
                    x, y, conf = kpts_data[j]
                    keypoints_list.append([float(x), float(y), float(conf)])
                    if conf > 0.5:  # Keypoint is visible
                        visible_count += 1
                
                poses.append({
                    'bbox': [float(x1), float(y1), float(x2), float(y2)],
                    'confidence': confidence,
                    'keypoints': keypoints_list,
                    'visible_keypoints': visible_count
                })
        
        return poses

    def get_skeleton_lines(self, keypoints: List[List[float]], 
                          min_confidence: float = 0.5) -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
        """
        Get skeleton lines for visualization.
        
        Args:
            keypoints: List of 17 keypoints [[x, y, conf], ...]
            min_confidence: Minimum confidence for keypoint to be drawn
            
        Returns:
            List of line segments [(start_point, end_point), ...]
        """
        lines = []
        for start_idx, end_idx in self.SKELETON:
            start_kpt = keypoints[start_idx]
            end_kpt = keypoints[end_idx]
            
            # Only draw if both keypoints are visible
            if start_kpt[2] > min_confidence and end_kpt[2] > min_confidence:
                start_point = (int(start_kpt[0]), int(start_kpt[1]))
                end_point = (int(end_kpt[0]), int(end_kpt[1]))
                lines.append((start_point, end_point))
        
        return lines

