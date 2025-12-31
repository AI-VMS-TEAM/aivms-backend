"""
Test script for Vision 31 Zone API Endpoints
"""
import requests
import json

BASE_URL = 'http://localhost:3000'

def test_zone_endpoints():
    print("=" * 70)
    print("🧪 TESTING VISION 31 ZONE API ENDPOINTS")
    print("=" * 70)
    
    # Test 1: Debug endpoint
    print("\n1️⃣  Testing /api/zones/debug...")
    try:
        r = requests.get(f'{BASE_URL}/api/zones/debug', timeout=5)
        print(f"   Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"   ✅ SUCCESS!")
            print(f"   Zone service initialized: {data.get('zone_service_initialized')}")
            print(f"   Tracking service initialized: {data.get('tracking_service_initialized')}")
        else:
            print(f"   ❌ FAIL: {r.text[:100]}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
    
    # Test 2: Zone list endpoint
    print("\n2️⃣  Testing /api/zones/list...")
    try:
        r = requests.get(f'{BASE_URL}/api/zones/list?camera_id=bosch_front_cam', timeout=5)
        print(f"   Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"   ✅ SUCCESS! Found {data.get('zone_count')} zones")
            for zone in data.get('zones', []):
                print(f"      - {zone.get('name')} ({zone.get('type')})")
        else:
            print(f"   ❌ FAIL: {r.text[:100]}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
    
    # Test 3: Zone analytics endpoint
    print("\n3️⃣  Testing /api/zones/analytics...")
    try:
        r = requests.get(f'{BASE_URL}/api/zones/analytics?camera_id=bosch_front_cam', timeout=5)
        print(f"   Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"   ✅ SUCCESS!")
            print(f"   Analytics for {len(data.get('analytics', []))} zones")
        else:
            print(f"   ❌ FAIL: {r.text[:100]}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
    
    # Test 4: Zone events endpoint
    print("\n4️⃣  Testing /api/zones/events...")
    try:
        r = requests.get(f'{BASE_URL}/api/zones/events?camera_id=bosch_front_cam&limit=10', timeout=5)
        print(f"   Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"   ✅ SUCCESS!")
            print(f"   Found {len(data.get('events', []))} zone events")
        else:
            print(f"   ❌ FAIL: {r.text[:100]}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
    
    # Test 5: Current zone occupancy endpoint
    print("\n5️⃣  Testing /api/zones/current...")
    try:
        r = requests.get(f'{BASE_URL}/api/zones/current?camera_id=bosch_front_cam', timeout=5)
        print(f"   Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"   ✅ SUCCESS!")
            print(f"   Current occupancy for {len(data.get('zones', []))} zones")
            for zone in data.get('zones', []):
                print(f"      - {zone.get('zone_name')}: {zone.get('track_count')} tracks")
        else:
            print(f"   ❌ FAIL: {r.text[:100]}")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
    
    # Test 6: Tracking status (verify server is working)
    print("\n6️⃣  Testing /api/tracking/status (baseline)...")
    try:
        r = requests.get(f'{BASE_URL}/api/tracking/status', timeout=5)
        print(f"   Status: {r.status_code}")
        if r.status_code == 200:
            print(f"   ✅ Server is responding correctly")
        else:
            print(f"   ❌ FAIL")
    except Exception as e:
        print(f"   ❌ ERROR: {e}")
    
    print("\n" + "=" * 70)
    print("✅ ZONE API ENDPOINT TESTING COMPLETE!")
    print("=" * 70)

if __name__ == '__main__':
    test_zone_endpoints()

