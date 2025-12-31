"""
Kalman Filter Tracker for Smooth Bounding Box Tracking

Reduces jitter and flickering by predicting object positions between frames.
Similar to what Bosch IVA Pro does for smooth tracking.
"""

import numpy as np
import logging

logger = logging.getLogger(__name__)


class KalmanBoxTracker:
    """
    Kalman filter for tracking a single bounding box.
    
    State vector: [x_center, y_center, width, height, vx, vy, vw, vh]
    - Position: (x_center, y_center)
    - Size: (width, height)
    - Velocity: (vx, vy, vw, vh)
    """
    
    def __init__(self, bbox):
        """
        Initialize Kalman filter with initial bounding box.
        
        Args:
            bbox: [x1, y1, x2, y2] format
        """
        # Convert bbox to [x_center, y_center, width, height]
        x1, y1, x2, y2 = bbox
        x_center = (x1 + x2) / 2
        y_center = (y1 + y2) / 2
        width = x2 - x1
        height = y2 - y1
        
        # State dimension: 8 (position, size, velocity)
        # Measurement dimension: 4 (position, size)
        self.kf = self._init_kalman_filter()
        
        # Initialize state
        self.kf['x'] = np.array([x_center, y_center, width, height, 0, 0, 0, 0], dtype=np.float32)
        
        self.time_since_update = 0
        self.hits = 1
        self.age = 0
        
    def _init_kalman_filter(self):
        """Initialize Kalman filter matrices."""
        # State transition matrix (constant velocity model)
        F = np.eye(8, dtype=np.float32)
        F[0, 4] = 1  # x += vx
        F[1, 5] = 1  # y += vy
        F[2, 6] = 1  # w += vw
        F[3, 7] = 1  # h += vh
        
        # Measurement matrix (we only measure position and size)
        H = np.zeros((4, 8), dtype=np.float32)
        H[0, 0] = 1  # measure x
        H[1, 1] = 1  # measure y
        H[2, 2] = 1  # measure w
        H[3, 3] = 1  # measure h
        
        # Process noise covariance (how much we trust the model)
        Q = np.eye(8, dtype=np.float32)
        Q[0:4, 0:4] *= 1.0  # Position/size uncertainty
        Q[4:8, 4:8] *= 0.01  # Velocity uncertainty (small = smooth)
        
        # Measurement noise covariance (how much we trust measurements)
        R = np.eye(4, dtype=np.float32) * 10.0  # Higher = smoother but less responsive
        
        # State covariance (initial uncertainty)
        P = np.eye(8, dtype=np.float32) * 1000.0
        
        return {
            'x': None,  # State vector
            'P': P,     # State covariance
            'F': F,     # State transition
            'H': H,     # Measurement matrix
            'Q': Q,     # Process noise
            'R': R      # Measurement noise
        }
    
    def predict(self):
        """Predict next state using motion model."""
        kf = self.kf
        
        # Predict state: x = F * x
        kf['x'] = kf['F'] @ kf['x']
        
        # Predict covariance: P = F * P * F^T + Q
        kf['P'] = kf['F'] @ kf['P'] @ kf['F'].T + kf['Q']
        
        self.age += 1
        self.time_since_update += 1
        
        return self.get_bbox()
    
    def update(self, bbox):
        """
        Update Kalman filter with new measurement.
        
        Args:
            bbox: [x1, y1, x2, y2] format
        """
        # Convert bbox to measurement vector
        x1, y1, x2, y2 = bbox
        x_center = (x1 + x2) / 2
        y_center = (y1 + y2) / 2
        width = x2 - x1
        height = y2 - y1
        z = np.array([x_center, y_center, width, height], dtype=np.float32)
        
        kf = self.kf
        
        # Innovation: y = z - H * x
        y = z - (kf['H'] @ kf['x'])
        
        # Innovation covariance: S = H * P * H^T + R
        S = kf['H'] @ kf['P'] @ kf['H'].T + kf['R']
        
        # Kalman gain: K = P * H^T * S^-1
        K = kf['P'] @ kf['H'].T @ np.linalg.inv(S)
        
        # Update state: x = x + K * y
        kf['x'] = kf['x'] + K @ y
        
        # Update covariance: P = (I - K * H) * P
        I = np.eye(8, dtype=np.float32)
        kf['P'] = (I - K @ kf['H']) @ kf['P']
        
        self.time_since_update = 0
        self.hits += 1
    
    def get_bbox(self):
        """
        Get current bounding box in [x1, y1, x2, y2] format.
        
        Returns:
            bbox: [x1, y1, x2, y2]
        """
        x_center, y_center, width, height = self.kf['x'][0:4]
        
        x1 = x_center - width / 2
        y1 = y_center - height / 2
        x2 = x_center + width / 2
        y2 = y_center + height / 2
        
        return [float(x1), float(y1), float(x2), float(y2)]

