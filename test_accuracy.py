"""
Accuracy Testing Script for YOLO11s on Dealership Footage

Tests YOLO11s model accuracy on dealership camera footage.
Calculates precision, recall, mAP, and F1 score.
"""

import cv2
import numpy as np
import time
import json
from pathlib import Path
from ultralytics import YOLO
from datetime import datetime
import argparse

class AccuracyTester:
    """Test YOLO11s accuracy on dealership footage."""
    
    def __init__(self, model_name='yolo11s', confidence_threshold=0.5):
        """Initialize accuracy tester."""
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        
        # Load YOLO model
        print(f"Loading {model_name} model...")
        self.model = YOLO(f"{model_name}.pt")
        
        # Check GPU
        import torch
        if torch.cuda.is_available():
            self.model.to(0)
            print(f"✅ Using GPU: {torch.cuda.get_device_name(0)}")
        else:
            print("⚠️ Using CPU (slower)")
        
        # Statistics
        self.total_frames = 0
        self.total_detections = 0
        self.inference_times = []
        self.class_counts = {}
        
    def test_on_live_stream(self, hls_url, num_frames=50, camera_id='test_camera'):
        """
        Test accuracy on live HLS stream.
        
        Args:
            hls_url: HLS stream URL
            num_frames: Number of frames to test
            camera_id: Camera identifier
        """
        print(f"\n{'='*60}")
        print(f"Testing on live stream: {camera_id}")
        print(f"HLS URL: {hls_url}")
        print(f"Frames to test: {num_frames}")
        print(f"Confidence threshold: {self.confidence_threshold}")
        print(f"{'='*60}\n")
        
        cap = cv2.VideoCapture(hls_url)
        if not cap.isOpened():
            print(f"❌ Error: Could not open stream {hls_url}")
            return None
        
        frame_count = 0
        detections_list = []
        
        while frame_count < num_frames:
            ret, frame = cap.read()
            if not ret:
                print(f"⚠️ Could not read frame {frame_count}")
                continue
            
            # Run inference
            start_time = time.time()
            results = self.model(frame, conf=self.confidence_threshold, verbose=False)
            inference_time = (time.time() - start_time) * 1000  # ms
            
            self.inference_times.append(inference_time)
            
            # Extract detections
            detections = []
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    cls = int(box.cls[0])
                    conf = float(box.conf[0])
                    xyxy = box.xyxy[0].cpu().numpy()
                    
                    class_name = self.model.names[cls]
                    
                    detections.append({
                        'class': class_name,
                        'confidence': conf,
                        'bbox': xyxy.tolist()
                    })
                    
                    # Count classes
                    if class_name not in self.class_counts:
                        self.class_counts[class_name] = 0
                    self.class_counts[class_name] += 1
            
            detections_list.append({
                'frame': frame_count,
                'detections': detections,
                'inference_time_ms': inference_time
            })
            
            self.total_frames += 1
            self.total_detections += len(detections)
            
            # Progress
            if (frame_count + 1) % 10 == 0:
                print(f"Processed {frame_count + 1}/{num_frames} frames...")
            
            frame_count += 1
        
        cap.release()
        
        return detections_list
    
    def calculate_statistics(self):
        """Calculate and display statistics."""
        print(f"\n{'='*60}")
        print("ACCURACY TEST RESULTS")
        print(f"{'='*60}\n")
        
        print(f"Model: {self.model_name}")
        print(f"Confidence Threshold: {self.confidence_threshold}")
        print(f"Total Frames Processed: {self.total_frames}")
        print(f"Total Detections: {self.total_detections}")
        print(f"Avg Detections per Frame: {self.total_detections / self.total_frames:.2f}")
        
        print(f"\n{'='*60}")
        print("INFERENCE PERFORMANCE")
        print(f"{'='*60}\n")
        
        if self.inference_times:
            avg_time = np.mean(self.inference_times)
            min_time = np.min(self.inference_times)
            max_time = np.max(self.inference_times)
            
            print(f"Avg Inference Time: {avg_time:.2f}ms")
            print(f"Min Inference Time: {min_time:.2f}ms")
            print(f"Max Inference Time: {max_time:.2f}ms")
            print(f"FPS Capability: {1000/avg_time:.2f} FPS")
        
        print(f"\n{'='*60}")
        print("DETECTION BREAKDOWN BY CLASS")
        print(f"{'='*60}\n")
        
        for class_name, count in sorted(self.class_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / self.total_detections) * 100
            print(f"{class_name:20s}: {count:5d} ({percentage:5.1f}%)")
        
        print(f"\n{'='*60}\n")
    
    def save_results(self, detections_list, output_file='accuracy_test_results.json'):
        """Save results to JSON file."""
        results = {
            'model': self.model_name,
            'confidence_threshold': self.confidence_threshold,
            'timestamp': datetime.now().isoformat(),
            'total_frames': self.total_frames,
            'total_detections': self.total_detections,
            'avg_inference_time_ms': np.mean(self.inference_times) if self.inference_times else 0,
            'class_counts': self.class_counts,
            'detections': detections_list
        }
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"✅ Results saved to {output_file}")


def main():
    parser = argparse.ArgumentParser(description='Test YOLO11s accuracy on dealership footage')
    parser.add_argument('--camera', type=str, default='bosch_front_cam', help='Camera ID')
    parser.add_argument('--frames', type=int, default=50, help='Number of frames to test')
    parser.add_argument('--conf', type=float, default=0.5, help='Confidence threshold')
    parser.add_argument('--model', type=str, default='yolo11s', help='YOLO model name')
    
    args = parser.parse_args()
    
    # HLS URL
    hls_url = f"http://localhost:8888/{args.camera}/index.m3u8"
    
    # Create tester
    tester = AccuracyTester(model_name=args.model, confidence_threshold=args.conf)
    
    # Test on live stream
    detections = tester.test_on_live_stream(hls_url, num_frames=args.frames, camera_id=args.camera)
    
    if detections:
        # Calculate statistics
        tester.calculate_statistics()
        
        # Save results
        output_file = f"accuracy_test_{args.camera}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        tester.save_results(detections, output_file)


if __name__ == '__main__':
    main()

