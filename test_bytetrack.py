"""
Test ByteTrack Integration (Vision 30)

Tests the ByteTrack tracking implementation on live footage.
Measures:
- ID switch rate
- Dwell time accuracy
- Real-time performance
- Track persistence
"""

import cv2
import time
import argparse
from ultralytics import YOLO
from collections import defaultdict
import numpy as np

def test_bytetrack_on_video(video_path: str, model_name: str = "yolo11s", 
                            conf: float = 0.5, frames: int = 100):
    """
    Test ByteTrack tracking on video.
    
    Args:
        video_path: Path to video file or HLS stream
        model_name: YOLO model name
        conf: Confidence threshold
        frames: Number of frames to process
    """
    print(f"\n{'='*60}")
    print(f"ByteTrack Tracking Test")
    print(f"{'='*60}")
    print(f"Video: {video_path}")
    print(f"Model: {model_name}")
    print(f"Confidence: {conf}")
    print(f"Frames: {frames}")
    print(f"{'='*60}\n")
    
    # Load YOLO model
    print("Loading YOLO model...")
    model = YOLO(f"{model_name}.pt")
    
    # Open video
    print("Opening video stream...")
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print(f"❌ Error: Could not open video: {video_path}")
        return
    
    # Get video properties
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"✅ Video opened: {width}x{height} @ {fps:.2f} FPS\n")
    
    # Tracking statistics
    track_history = defaultdict(list)  # track_id -> list of (frame_num, bbox, timestamp)
    track_first_seen = {}  # track_id -> frame_num
    track_last_seen = {}  # track_id -> frame_num
    id_switches = 0
    prev_frame_tracks = {}  # bbox_hash -> track_id
    
    # Performance metrics
    inference_times = []
    frame_count = 0
    start_time = time.time()
    
    print("Starting tracking...\n")
    
    while frame_count < frames:
        ret, frame = cap.read()
        if not ret:
            print("End of video reached")
            break
        
        frame_count += 1
        current_time = time.time()
        
        # Run ByteTrack tracking
        inference_start = time.time()
        results = model.track(
            frame,
            conf=conf,
            persist=True,
            tracker="bytetrack.yaml",
            verbose=False
        )
        inference_time = time.time() - inference_start
        inference_times.append(inference_time)
        
        # Process tracks
        current_frame_tracks = {}
        if results[0].boxes and results[0].boxes.is_track:
            boxes = results[0].boxes
            
            for i in range(len(boxes)):
                track_id = int(boxes.id[i])
                bbox = boxes.xywh[i].cpu().tolist()
                confidence = float(boxes.conf[i])
                class_name = model.names[int(boxes.cls[i])]
                
                # Record track history
                track_history[track_id].append((frame_count, bbox, current_time))
                
                # Track first and last seen
                if track_id not in track_first_seen:
                    track_first_seen[track_id] = frame_count
                track_last_seen[track_id] = frame_count
                
                # Create bbox hash for ID switch detection
                bbox_hash = f"{int(bbox[0]/10)}_{int(bbox[1]/10)}_{int(bbox[2]/10)}_{int(bbox[3]/10)}"
                
                # Check for ID switch
                if bbox_hash in prev_frame_tracks and prev_frame_tracks[bbox_hash] != track_id:
                    id_switches += 1
                    print(f"⚠️  ID switch detected at frame {frame_count}: "
                          f"{prev_frame_tracks[bbox_hash]} -> {track_id}")
                
                current_frame_tracks[bbox_hash] = track_id
        
        prev_frame_tracks = current_frame_tracks
        
        # Print progress every 10 frames
        if frame_count % 10 == 0:
            avg_inference = np.mean(inference_times[-10:]) * 1000
            print(f"Frame {frame_count}/{frames}: "
                  f"{len(current_frame_tracks)} tracks, "
                  f"Inference: {avg_inference:.1f}ms")
    
    cap.release()
    
    # Calculate statistics
    total_time = time.time() - start_time
    avg_inference_time = np.mean(inference_times) * 1000
    avg_fps = frame_count / total_time
    
    total_tracks = len(track_history)
    id_switch_rate = (id_switches / total_tracks * 100) if total_tracks > 0 else 0.0
    
    # Calculate average track duration
    track_durations = []
    for track_id in track_history:
        duration = track_last_seen[track_id] - track_first_seen[track_id]
        track_durations.append(duration)
    
    avg_track_duration = np.mean(track_durations) if track_durations else 0.0
    
    # Print results
    print(f"\n{'='*60}")
    print(f"ByteTrack Test Results")
    print(f"{'='*60}")
    print(f"Frames Processed: {frame_count}")
    print(f"Total Time: {total_time:.2f}s")
    print(f"Average FPS: {avg_fps:.2f}")
    print(f"Average Inference Time: {avg_inference_time:.2f}ms")
    print(f"\nTracking Statistics:")
    print(f"Total Tracks Created: {total_tracks}")
    print(f"ID Switches: {id_switches}")
    print(f"ID Switch Rate: {id_switch_rate:.2f}%")
    print(f"Average Track Duration: {avg_track_duration:.1f} frames")
    print(f"{'='*60}\n")
    
    # Check if ID switch rate meets requirement
    if id_switch_rate < 10.0:
        print(f"✅ PASSED: ID switch rate ({id_switch_rate:.2f}%) < 10%")
    else:
        print(f"❌ FAILED: ID switch rate ({id_switch_rate:.2f}%) >= 10%")
    
    return {
        'frames_processed': frame_count,
        'total_tracks': total_tracks,
        'id_switches': id_switches,
        'id_switch_rate': id_switch_rate,
        'avg_inference_time': avg_inference_time,
        'avg_fps': avg_fps,
        'avg_track_duration': avg_track_duration
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test ByteTrack tracking on video")
    parser.add_argument('--video', type=str, default='http://localhost:8888/bosch_front_cam/index.m3u8',
                       help='Video path or HLS stream URL')
    parser.add_argument('--model', type=str, default='yolo11s',
                       help='YOLO model name (yolo11n, yolo11s, yolo11m, etc.)')
    parser.add_argument('--conf', type=float, default=0.5,
                       help='Confidence threshold (0.0-1.0)')
    parser.add_argument('--frames', type=int, default=100,
                       help='Number of frames to process')
    
    args = parser.parse_args()
    
    test_bytetrack_on_video(args.video, args.model, args.conf, args.frames)

