"""
Test script to verify YOLO11 upgrade and performance monitoring.

This script:
1. Downloads YOLO11s model if not present
2. Tests inference on a sample image
3. Measures performance metrics
4. Compares with YOLOv8s if available
"""

import time
import cv2
import numpy as np
from ultralytics import YOLO
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_model(model_name: str, test_image: np.ndarray, num_runs: int = 50):
    """Test a YOLO model and measure performance."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing {model_name}")
    logger.info(f"{'='*60}")
    
    # Load model
    logger.info(f"Loading {model_name}...")
    model = YOLO(f"{model_name}.pt")
    
    # Check device
    import torch
    device = 0 if torch.cuda.is_available() else "cpu"
    model.to(device)
    logger.info(f"Device: {'GPU' if device == 0 else 'CPU'}")
    
    # Warm-up run
    logger.info("Warming up...")
    _ = model(test_image, conf=0.5, verbose=False)
    
    # Performance test
    logger.info(f"Running {num_runs} inference tests...")
    inference_times = []
    total_detections = 0
    
    for i in range(num_runs):
        start = time.time()
        results = model(test_image, conf=0.5, verbose=False)
        inference_time = time.time() - start
        inference_times.append(inference_time)
        
        # Count detections
        for result in results:
            total_detections += len(result.boxes)
    
    # Calculate statistics
    avg_time = sum(inference_times) / len(inference_times)
    min_time = min(inference_times)
    max_time = max(inference_times)
    fps = 1.0 / avg_time
    
    # Results
    logger.info(f"\n📊 Performance Results for {model_name}:")
    logger.info(f"  Average Inference Time: {avg_time*1000:.2f}ms")
    logger.info(f"  Min Inference Time: {min_time*1000:.2f}ms")
    logger.info(f"  Max Inference Time: {max_time*1000:.2f}ms")
    logger.info(f"  FPS: {fps:.2f}")
    logger.info(f"  Total Detections: {total_detections}")
    logger.info(f"  Avg Detections per Frame: {total_detections/num_runs:.2f}")
    
    return {
        'model': model_name,
        'avg_time_ms': avg_time * 1000,
        'min_time_ms': min_time * 1000,
        'max_time_ms': max_time * 1000,
        'fps': fps,
        'total_detections': total_detections,
        'avg_detections': total_detections / num_runs
    }


def main():
    """Main test function."""
    logger.info("🚀 YOLO11 Upgrade Test")
    logger.info("=" * 60)
    
    # Create a test image (640x640 random noise for testing)
    # In production, you'd use actual camera footage
    logger.info("Creating test image (640x640)...")
    test_image = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
    
    # Test YOLO11s
    results_yolo11s = test_model("yolo11s", test_image, num_runs=50)
    
    # Try to test YOLOv8s for comparison (if available)
    try:
        results_yolov8s = test_model("yolov8s", test_image, num_runs=50)
        
        # Comparison
        logger.info(f"\n{'='*60}")
        logger.info("📈 COMPARISON: YOLO11s vs YOLOv8s")
        logger.info(f"{'='*60}")
        
        speed_improvement = ((results_yolov8s['avg_time_ms'] - results_yolo11s['avg_time_ms']) 
                            / results_yolov8s['avg_time_ms'] * 100)
        fps_improvement = ((results_yolo11s['fps'] - results_yolov8s['fps']) 
                          / results_yolov8s['fps'] * 100)
        
        logger.info(f"  YOLO11s Avg Time: {results_yolo11s['avg_time_ms']:.2f}ms")
        logger.info(f"  YOLOv8s Avg Time: {results_yolov8s['avg_time_ms']:.2f}ms")
        logger.info(f"  Speed Improvement: {speed_improvement:+.1f}%")
        logger.info(f"")
        logger.info(f"  YOLO11s FPS: {results_yolo11s['fps']:.2f}")
        logger.info(f"  YOLOv8s FPS: {results_yolov8s['fps']:.2f}")
        logger.info(f"  FPS Improvement: {fps_improvement:+.1f}%")
        
    except Exception as e:
        logger.info(f"\nℹ️  Could not test YOLOv8s for comparison: {e}")
    
    logger.info(f"\n{'='*60}")
    logger.info("✅ Test Complete!")
    logger.info(f"{'='*60}")
    logger.info("\nNext Steps:")
    logger.info("1. Run your Flask app with the updated config.ini")
    logger.info("2. Check /api/detection/status endpoint for real-time metrics")
    logger.info("3. Monitor logs for 'Detection Performance' messages every 5 seconds")
    logger.info("4. Verify FPS meets the 10+ FPS requirement")


if __name__ == "__main__":
    main()

