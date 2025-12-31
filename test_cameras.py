#!/usr/bin/env python3
"""
Test script to verify RTSP connectivity to all cameras
"""
import cv2
import json
import os
from urllib.parse import quote

def test_camera_rtsp(camera):
    """Test if a camera's RTSP stream is accessible"""
    print(f"\n{'='*60}")
    print(f"Testing: {camera['name']}")
    print(f"{'='*60}")
    
    # Build RTSP URL
    address = camera['ip']
    if camera.get('port'):
        address += f":{camera['port']}"
    
    path = camera.get('path', '').lstrip('/')
    rtsp_url = f"rtsp://{quote(camera['username'])}:{quote(camera['password'])}@{address}/{path}"
    
    print(f"IP: {camera['ip']}")
    print(f"Port: {camera.get('port', 'default (554)')}")
    print(f"Username: {camera['username']}")
    print(f"Path: {path}")
    print(f"RTSP URL: {rtsp_url}")
    
    # Try to connect
    print("\nAttempting to connect...")
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    
    if cap.isOpened():
        print("✅ SUCCESS: Connected to camera!")
        # Try to read a frame
        ret, frame = cap.read()
        if ret:
            print(f"✅ SUCCESS: Got frame! Resolution: {frame.shape[1]}x{frame.shape[0]}")
        else:
            print("⚠️  WARNING: Connected but couldn't read frame")
        cap.release()
        return True
    else:
        print("❌ FAILED: Could not connect to camera")
        print("   Possible causes:")
        print("   - Camera is offline or unreachable")
        print("   - Wrong IP address")
        print("   - Wrong credentials (username/password)")
        print("   - Wrong RTSP path")
        print("   - Network connectivity issue")
        cap.release()
        return False

def main():
    print("\n" + "="*60)
    print("CAMERA RTSP CONNECTIVITY TEST")
    print("="*60)
    
    # Load cameras from JSON
    if not os.path.exists('cameras.json'):
        print("❌ cameras.json not found!")
        return
    
    with open('cameras.json', 'r') as f:
        cameras = json.load(f)
    
    print(f"\nFound {len(cameras)} camera(s) to test\n")
    
    results = {}
    for camera in cameras:
        success = test_camera_rtsp(camera)
        results[camera['name']] = success
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} cameras working")
    
    if passed == total:
        print("\n🎉 All cameras are working! MediaMTX should be able to stream them.")
    else:
        print(f"\n⚠️  {total - passed} camera(s) failed. Fix these before starting MediaMTX.")

if __name__ == '__main__':
    main()

