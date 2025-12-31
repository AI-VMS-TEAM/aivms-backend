"""
Advanced Accuracy Testing with Ground Truth Comparison

Tests YOLO11s against COCO validation dataset or custom annotations.
Calculates precision, recall, mAP@0.5, mAP@0.5:0.95, and F1 score.
"""

import cv2
import numpy as np
import time
import json
from pathlib import Path
from ultralytics import YOLO
from datetime import datetime
import argparse

class AdvancedAccuracyTester:
    """Advanced accuracy testing with ground truth comparison."""
    
    def __init__(self, model_name='yolo11s', confidence_threshold=0.5, iou_threshold=0.5):
        """Initialize advanced accuracy tester."""
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        
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
        
        # Metrics
        self.true_positives = 0
        self.false_positives = 0
        self.false_negatives = 0
        self.inference_times = []
        
    def calculate_iou(self, box1, box2):
        """Calculate IoU between two bounding boxes."""
        x1_min, y1_min, x1_max, y1_max = box1
        x2_min, y2_min, x2_max, y2_max = box2
        
        # Intersection
        inter_x_min = max(x1_min, x2_min)
        inter_y_min = max(y1_min, y2_min)
        inter_x_max = min(x1_max, x2_max)
        inter_y_max = min(y1_max, y2_max)
        
        if inter_x_max < inter_x_min or inter_y_max < inter_y_min:
            return 0.0
        
        inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
        
        # Union
        box1_area = (x1_max - x1_min) * (y1_max - y1_min)
        box2_area = (x2_max - x2_min) * (y2_max - y2_min)
        union_area = box1_area + box2_area - inter_area
        
        return inter_area / union_area if union_area > 0 else 0.0
    
    def test_on_coco_val(self, data_yaml='coco.yaml'):
        """
        Test on COCO validation dataset using Ultralytics built-in validation.
        
        Args:
            data_yaml: Path to COCO data YAML file
        """
        print(f"\n{'='*60}")
        print("Testing on COCO Validation Dataset")
        print(f"{'='*60}\n")
        
        # Run validation
        results = self.model.val(data=data_yaml, conf=self.confidence_threshold, iou=self.iou_threshold)
        
        return results
    
    def display_coco_results(self, results):
        """Display COCO validation results."""
        print(f"\n{'='*60}")
        print("COCO VALIDATION RESULTS")
        print(f"{'='*60}\n")
        
        print(f"Model: {self.model_name}")
        print(f"Confidence Threshold: {self.confidence_threshold}")
        print(f"IoU Threshold: {self.iou_threshold}")
        
        print(f"\n{'='*60}")
        print("ACCURACY METRICS")
        print(f"{'='*60}\n")
        
        # Extract metrics
        metrics = results.results_dict
        
        # mAP metrics
        map50 = metrics.get('metrics/mAP50(B)', 0)
        map50_95 = metrics.get('metrics/mAP50-95(B)', 0)
        
        # Precision and Recall
        precision = metrics.get('metrics/precision(B)', 0)
        recall = metrics.get('metrics/recall(B)', 0)
        
        # F1 Score
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        print(f"Precision:        {precision:.4f} ({precision*100:.2f}%)")
        print(f"Recall:           {recall:.4f} ({recall*100:.2f}%)")
        print(f"F1 Score:         {f1:.4f}")
        print(f"mAP@0.5:          {map50:.4f} ({map50*100:.2f}%)")
        print(f"mAP@0.5:0.95:     {map50_95:.4f} ({map50_95*100:.2f}%)")
        
        print(f"\n{'='*60}")
        print("VISION 29 REQUIREMENT CHECK")
        print(f"{'='*60}\n")
        
        # Check Vision 29 requirement (≥85% accuracy)
        accuracy_met = map50 >= 0.85
        
        if accuracy_met:
            print(f"✅ PASSED: mAP@0.5 = {map50*100:.2f}% (≥85% required)")
        else:
            print(f"❌ FAILED: mAP@0.5 = {map50*100:.2f}% (≥85% required)")
            print(f"   Need to improve by {(0.85 - map50)*100:.2f}%")
        
        print(f"\n{'='*60}\n")
        
        return {
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'map50': map50,
            'map50_95': map50_95,
            'accuracy_met': accuracy_met
        }
    
    def test_different_thresholds(self, data_yaml='coco.yaml', thresholds=[0.25, 0.35, 0.45]):
        """
        Test different confidence thresholds to find optimal value.

        Args:
            data_yaml: Path to COCO data YAML file
            thresholds: List of confidence thresholds to test
        """
        print(f"\n{'='*60}")
        print("TESTING DIFFERENT CONFIDENCE THRESHOLDS")
        print(f"{'='*60}\n")
        
        results_list = []
        
        for threshold in thresholds:
            print(f"\nTesting threshold: {threshold}")
            self.confidence_threshold = threshold
            
            results = self.model.val(data=data_yaml, conf=threshold, iou=self.iou_threshold, verbose=False)
            metrics = results.results_dict
            
            map50 = metrics.get('metrics/mAP50(B)', 0)
            precision = metrics.get('metrics/precision(B)', 0)
            recall = metrics.get('metrics/recall(B)', 0)
            
            results_list.append({
                'threshold': threshold,
                'precision': precision,
                'recall': recall,
                'map50': map50
            })
            
            print(f"  Precision: {precision*100:.2f}%, Recall: {recall*100:.2f}%, mAP@0.5: {map50*100:.2f}%")
        
        # Display summary
        print(f"\n{'='*60}")
        print("THRESHOLD COMPARISON")
        print(f"{'='*60}\n")
        
        print(f"{'Threshold':<12} {'Precision':<12} {'Recall':<12} {'mAP@0.5':<12} {'Status'}")
        print(f"{'-'*60}")
        
        for result in results_list:
            status = "✅ PASS" if result['map50'] >= 0.85 else "❌ FAIL"
            print(f"{result['threshold']:<12.1f} {result['precision']*100:<11.2f}% {result['recall']*100:<11.2f}% {result['map50']*100:<11.2f}% {status}")
        
        # Find best threshold
        best = max(results_list, key=lambda x: x['map50'])
        print(f"\n✅ Best threshold: {best['threshold']} (mAP@0.5: {best['map50']*100:.2f}%)")
        
        return results_list


def main():
    parser = argparse.ArgumentParser(description='Advanced accuracy testing for YOLO11s')
    parser.add_argument('--model', type=str, default='yolo11s', help='YOLO model name')
    parser.add_argument('--conf', type=float, default=0.5, help='Confidence threshold')
    parser.add_argument('--iou', type=float, default=0.5, help='IoU threshold')
    parser.add_argument('--test-thresholds', action='store_true', help='Test multiple confidence thresholds')
    parser.add_argument('--data', type=str, default='coco.yaml', help='Dataset YAML file')
    
    args = parser.parse_args()
    
    # Create tester
    tester = AdvancedAccuracyTester(
        model_name=args.model,
        confidence_threshold=args.conf,
        iou_threshold=args.iou
    )
    
    if args.test_thresholds:
        # Test multiple thresholds
        results = tester.test_different_thresholds(data_yaml=args.data)
    else:
        # Single test
        results = tester.test_on_coco_val(data_yaml=args.data)
        metrics = tester.display_coco_results(results)
        
        # Save results
        output_file = f"accuracy_test_coco_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(metrics, f, indent=2)
        print(f"✅ Results saved to {output_file}")


if __name__ == '__main__':
    main()

