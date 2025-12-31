"""
Test script to verify live detection and zone tracking with TV footage
"""
import requests
import json
import time

BASE_URL = 'http://localhost:3000'

def test_detection_status():
    """Check detection status"""
    print("\n" + "=" * 70)
    print("📊 DETECTION STATUS")
    print("=" * 70)
    
    try:
        r = requests.get(f'{BASE_URL}/api/detection/status', timeout=5)
        if r.status_code == 200:
            data = r.json()
            print(f"Total detections: {data.get('total_detections', 0)}")
            print(f"Active tracks: {data.get('active_tracks', 0)}")
            print(f"FPS: {data.get('fps', 0):.1f}")
            print()
            
            # Per-camera stats
            cameras = data.get('cameras', {})
            for cam_id, cam_data in cameras.items():
                print(f"Camera: {cam_id}")
                print(f"  Detections: {cam_data.get('detections', 0)}")
                print(f"  Tracks: {cam_data.get('tracks', 0)}")
                print(f"  FPS: {cam_data.get('fps', 0):.1f}")
        else:
            print(f"Error: {r.status_code}")
    except Exception as e:
        print(f"Error: {e}")

def test_zone_status():
    """Check zone detection status"""
    print("\n" + "=" * 70)
    print("🎯 ZONE STATUS (Bosch Front Cam)")
    print("=" * 70)
    
    try:
        r = requests.get(f'{BASE_URL}/api/zones/current?camera_id=bosch_front_cam', timeout=5)
        if r.status_code == 200:
            data = r.json()
            zones = data.get('zones', [])
            print(f"Total zones: {len(zones)}")
            print()
            
            for zone in zones:
                zone_name = zone.get('zone_name', zone.get('zone_id', 'Unknown'))
                print(f"Zone: {zone_name}")
                print(f"  Track count: {zone.get('track_count', 0)}")
                print(f"  Tracks: {zone.get('tracks', [])}")
                print()
        else:
            print(f"Error: {r.status_code}")
    except Exception as e:
        print(f"Error: {e}")

def test_zone_events():
    """Check zone events"""
    print("\n" + "=" * 70)
    print("📋 ZONE EVENTS (Last 10)")
    print("=" * 70)
    
    try:
        r = requests.get(f'{BASE_URL}/api/zones/events?camera_id=bosch_front_cam&limit=10', timeout=5)
        if r.status_code == 200:
            data = r.json()
            events = data.get('events', [])
            print(f"Total events: {len(events)}")
            print()
            
            if events:
                for event in events[-5:]:  # Show last 5
                    zone_name = event.get('zone_name', event.get('zone_id', 'Unknown'))
                    print(f"Track {event.get('track_id')}: {event.get('event_type')} at {zone_name}")
                    print(f"  Time: {event.get('timestamp')}")
            else:
                print("No zone events yet. Waiting for objects to enter zones...")
        else:
            print(f"Error: {r.status_code}")
    except Exception as e:
        print(f"Error: {e}")

def test_tracking_status():
    """Check tracking status"""
    print("\n" + "=" * 70)
    print("🔍 TRACKING STATUS")
    print("=" * 70)
    
    try:
        r = requests.get(f'{BASE_URL}/api/tracking/status', timeout=5)
        if r.status_code == 200:
            data = r.json()
            print(f"Total tracks: {data.get('total_tracks', 0)}")
            print(f"Active tracks: {data.get('active_tracks', 0)}")
            print(f"ID switches: {data.get('id_switches', 0)}")
            print(f"Average dwell time: {data.get('avg_dwell_time', 0):.1f}s")
        else:
            print(f"Error: {r.status_code}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    print("\n🧪 VISION 31 LIVE DETECTION & ZONE TRACKING TEST")
    print("=" * 70)
    print("Testing with Bosch Front Cam pointing at TV (City Traffic 4K)")
    print("=" * 70)
    
    # Run tests
    test_detection_status()
    test_tracking_status()
    test_zone_status()
    test_zone_events()
    
    print("\n" + "=" * 70)
    print("✅ TEST COMPLETE!")
    print("=" * 70)
    print("\n💡 NEXT STEPS:")
    print("1. Watch the live video feed on the frontend")
    print("2. Verify objects are being detected (bounding boxes)")
    print("3. Verify objects are being tracked (consistent IDs)")
    print("4. Verify zone events are being detected (entry/exit)")
    print("5. Run this test again in 30 seconds to see updated stats")
    print("\n📊 To monitor in real-time:")
    print("   - Open browser: http://localhost:3000")
    print("   - Watch live detections and zone events")
    print("   - Check WebSocket messages in browser console")

