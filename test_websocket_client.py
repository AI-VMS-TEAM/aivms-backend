"""
Test WebSocket client for real-time detection streaming.

This script connects to the detection WebSocket endpoint and receives
real-time detections as they are made by the YOLO model.

Usage:
    py -3.12 test_websocket_client.py [camera_id]
    
    camera_id: Optional. Specific camera to monitor, or 'all' for all cameras (default: all)
"""

import socketio
import sys
import time
from datetime import datetime

# Create SocketIO client
sio = socketio.Client()

# Statistics
detection_count = 0
start_time = None


@sio.on('connect', namespace='/detections')
def on_connect():
    """Handle connection to server."""
    global start_time
    start_time = time.time()
    print("=" * 60)
    print("✅ Connected to detection WebSocket")
    print("=" * 60)


@sio.on('disconnect', namespace='/detections')
def on_disconnect():
    """Handle disconnection from server."""
    print("\n" + "=" * 60)
    print("❌ Disconnected from detection WebSocket")
    print("=" * 60)


@sio.on('connected', namespace='/detections')
def on_connected(data):
    """Handle initial connection message."""
    print(f"📡 {data['message']}")


@sio.on('subscribed', namespace='/detections')
def on_subscribed(data):
    """Handle subscription confirmation."""
    print(f"✅ {data['message']}")
    print(f"📊 Waiting for detections from: {data['camera_id']}")
    print("=" * 60)


@sio.on('unsubscribed', namespace='/detections')
def on_unsubscribed(data):
    """Handle unsubscription confirmation."""
    print(f"❌ {data['message']}")


@sio.on('detections', namespace='/detections')
def on_detections(data):
    """Handle incoming detections."""
    global detection_count
    
    camera_id = data['camera_id']
    timestamp = data['timestamp']
    detections = data['detections']
    count = data['count']
    
    detection_count += count
    
    # Format timestamp
    dt = datetime.fromtimestamp(timestamp)
    time_str = dt.strftime('%H:%M:%S.%f')[:-3]
    
    # Calculate FPS
    elapsed = time.time() - start_time
    fps = detection_count / elapsed if elapsed > 0 else 0
    
    print(f"\n[{time_str}] 📹 {camera_id} - {count} detection(s)")
    
    for i, det in enumerate(detections, 1):
        class_name = det['class']
        confidence = det['confidence']
        bbox = det['bbox']
        print(f"  {i}. {class_name} ({confidence:.2f}) at [{bbox[0]:.0f}, {bbox[1]:.0f}, {bbox[2]:.0f}, {bbox[3]:.0f}]")
    
    print(f"📊 Total: {detection_count} detections | Avg: {fps:.2f} det/sec")


def main():
    """Main function."""
    # Get camera_id from command line or default to 'all'
    camera_id = sys.argv[1] if len(sys.argv) > 1 else 'all'
    
    print("\n" + "=" * 60)
    print("🚀 AIVMS Real-Time Detection WebSocket Client")
    print("=" * 60)
    print(f"Camera: {camera_id}")
    print(f"Server: http://localhost:3000")
    print("=" * 60)
    
    try:
        # Connect to server
        print("\n🔌 Connecting to WebSocket server...")
        sio.connect('http://localhost:3000', namespaces=['/detections'])
        
        # Subscribe to camera
        print(f"📡 Subscribing to camera: {camera_id}...")
        sio.emit('subscribe', {'camera_id': camera_id}, namespace='/detections')
        
        # Wait for detections (Ctrl+C to stop)
        print("\n⏳ Press Ctrl+C to stop...\n")
        sio.wait()
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopping...")
        
        # Unsubscribe
        sio.emit('unsubscribe', {'camera_id': camera_id}, namespace='/detections')
        
        # Disconnect
        sio.disconnect()
        
        # Print summary
        elapsed = time.time() - start_time if start_time else 0
        print("\n" + "=" * 60)
        print("📊 SUMMARY")
        print("=" * 60)
        print(f"Total detections: {detection_count}")
        print(f"Duration: {elapsed:.1f} seconds")
        print(f"Average rate: {detection_count/elapsed:.2f} detections/sec" if elapsed > 0 else "N/A")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()

