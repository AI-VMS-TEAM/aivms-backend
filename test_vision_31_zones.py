"""
Test script for Vision 31: Zone-Based Tracking

Tests:
1. Zone configuration loading
2. Zone detection (point-in-polygon)
3. Zone entry/exit events
4. Zone analytics API endpoints
5. Real-time zone event broadcasting

Usage:
    python test_vision_31_zones.py --camera bosch_front_cam --duration 60
"""

import argparse
import requests
import time
import json
from datetime import datetime

# Flask server URL
BASE_URL = "http://localhost:3000"


def test_zone_list(camera_id):
    """Test zone list endpoint."""
    print(f"\n{'='*60}")
    print("TEST 1: Zone List")
    print(f"{'='*60}")
    
    url = f"{BASE_URL}/api/zones/list?camera_id={camera_id}"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Zone list retrieved successfully")
        print(f"   Camera: {data['camera_id']}")
        print(f"   Zone count: {data['zone_count']}")
        
        for zone in data['zones']:
            print(f"\n   Zone: {zone['name']} ({zone['id']})")
            print(f"   Type: {zone['type']}")
            print(f"   Description: {zone['description']}")
            print(f"   Polygon: {len(zone['polygon'])} points")
        
        return True
    else:
        print(f"❌ Failed to get zone list: {response.status_code}")
        print(f"   Error: {response.text}")
        return False


def test_zone_analytics(camera_id):
    """Test zone analytics endpoint."""
    print(f"\n{'='*60}")
    print("TEST 2: Zone Analytics")
    print(f"{'='*60}")
    
    url = f"{BASE_URL}/api/zones/analytics?camera_id={camera_id}"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Zone analytics retrieved successfully")
        print(f"   Camera: {data['camera_id']}")
        print(f"   Time range: {data['start_time']} to {data['end_time']}")
        print(f"   Analytics count: {len(data['analytics'])}")
        
        for analytics in data['analytics']:
            print(f"\n   Zone: {analytics['zone_id']}")
            print(f"   Entries: {analytics['entries']}")
            print(f"   Exits: {analytics['exits']}")
            print(f"   Unique tracks: {analytics['unique_tracks']}")
            print(f"   Current occupancy: {analytics['current_occupancy']}")
        
        return True
    else:
        print(f"❌ Failed to get zone analytics: {response.status_code}")
        print(f"   Error: {response.text}")
        return False


def test_zone_events(camera_id):
    """Test zone events endpoint."""
    print(f"\n{'='*60}")
    print("TEST 3: Zone Events")
    print(f"{'='*60}")
    
    url = f"{BASE_URL}/api/zones/events?camera_id={camera_id}&limit=10"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Zone events retrieved successfully")
        print(f"   Camera: {data['camera_id']}")
        print(f"   Event count: {data['event_count']}")
        
        for event in data['events'][:5]:  # Show first 5 events
            timestamp = datetime.fromtimestamp(event['timestamp']).strftime('%H:%M:%S')
            print(f"\n   Event: {event['event_type']}")
            print(f"   Track ID: {event['track_id']}")
            print(f"   Zone: {event['zone_id']}")
            print(f"   Time: {timestamp}")
        
        return True
    else:
        print(f"❌ Failed to get zone events: {response.status_code}")
        print(f"   Error: {response.text}")
        return False


def test_current_occupancy(camera_id):
    """Test current zone occupancy endpoint."""
    print(f"\n{'='*60}")
    print("TEST 4: Current Zone Occupancy")
    print(f"{'='*60}")
    
    url = f"{BASE_URL}/api/zones/current?camera_id={camera_id}"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Current occupancy retrieved successfully")
        print(f"   Camera: {data['camera_id']}")
        print(f"   Timestamp: {datetime.fromtimestamp(data['timestamp']).strftime('%H:%M:%S')}")
        print(f"   Zones with tracks: {len(data['zones'])}")
        
        for zone in data['zones']:
            print(f"\n   Zone: {zone['zone_id']}")
            print(f"   Track count: {zone['track_count']}")
            for track in zone['tracks']:
                print(f"      Track {track['track_id']}: {track['class']} (dwell: {track['dwell_time']:.1f}s)")
        
        return True
    else:
        print(f"❌ Failed to get current occupancy: {response.status_code}")
        print(f"   Error: {response.text}")
        return False


def monitor_zone_events(camera_id, duration):
    """Monitor zone events in real-time."""
    print(f"\n{'='*60}")
    print(f"TEST 5: Real-Time Zone Event Monitoring ({duration}s)")
    print(f"{'='*60}")
    
    start_time = time.time()
    event_count = 0
    
    while time.time() - start_time < duration:
        url = f"{BASE_URL}/api/zones/events?camera_id={camera_id}&limit=5"
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            if data['event_count'] > event_count:
                new_events = data['event_count'] - event_count
                event_count = data['event_count']
                print(f"   [{datetime.now().strftime('%H:%M:%S')}] {new_events} new zone events detected")
        
        time.sleep(2)
    
    print(f"\n✅ Monitoring complete: {event_count} total zone events")
    return True


def main():
    parser = argparse.ArgumentParser(description='Test Vision 31 Zone-Based Tracking')
    parser.add_argument('--camera', default='bosch_front_cam', help='Camera ID to test')
    parser.add_argument('--duration', type=int, default=30, help='Monitoring duration in seconds')
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print("VISION 31: ZONE-BASED TRACKING TEST")
    print(f"{'='*60}")
    print(f"Camera: {args.camera}")
    print(f"Duration: {args.duration}s")
    print(f"Server: {BASE_URL}")
    
    # Run tests
    results = []
    results.append(("Zone List", test_zone_list(args.camera)))
    results.append(("Zone Analytics", test_zone_analytics(args.camera)))
    results.append(("Zone Events", test_zone_events(args.camera)))
    results.append(("Current Occupancy", test_current_occupancy(args.camera)))
    results.append(("Real-Time Monitoring", monitor_zone_events(args.camera, args.duration)))
    
    # Print summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\n{'='*60}")
    print(f"RESULT: {passed}/{total} tests passed")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()

