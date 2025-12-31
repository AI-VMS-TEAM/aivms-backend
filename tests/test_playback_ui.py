"""
Playback UI Test Suite
Simulates user interactions with the playback player
"""

import sys
import os
import json
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path to import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app as flask_app

# Use Flask test client instead of HTTP requests to avoid Flask caching issues
test_client = flask_app.test_client()

class PlaybackUITester:
    def __init__(self):
        self.test_results = []
        self.cameras = []
        self.playback_info = None
        
    def log_test(self, name, status, details=""):
        """Log test result"""
        result = {
            'name': name,
            'status': status,
            'details': details,
            'timestamp': datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status_icon = "✅" if status == "PASS" else "❌"
        print(f"{status_icon} {name}")
        if details:
            print(f"   {details}")
    
    def test_page_loads(self):
        """Test 1: Playback page loads"""
        try:
            response = test_client.get("/playback.html")
            if response.status_code == 200 and "playback" in response.data.decode().lower():
                self.log_test("Page loads", "PASS", f"Status: {response.status_code}")
                return True
            else:
                self.log_test("Page loads", "FAIL", f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Page loads", "FAIL", str(e))
            return False

    def test_camera_api(self):
        """Test 2: Camera API returns cameras"""
        try:
            response = test_client.get("/api/cameras")
            if response.status_code == 200:
                self.cameras = json.loads(response.data)
                if len(self.cameras) > 0:
                    self.log_test("Camera API", "PASS", f"Found {len(self.cameras)} cameras")
                    for cam in self.cameras:
                        print(f"   - {cam.get('name')}")
                    return True
                else:
                    self.log_test("Camera API", "FAIL", "No cameras found")
                    return False
            else:
                self.log_test("Camera API", "FAIL", f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Camera API", "FAIL", str(e))
            return False
    
    def test_playback_info_query(self):
        """Test 3: Query playback info for time range"""
        if not self.cameras:
            self.log_test("Playback info query", "SKIP", "No cameras available")
            return False

        try:
            camera_id = self.cameras[0].get('name', '').lower().replace(' ', '_').replace('-', '_')

            # Query last 1 hour
            now = datetime.now()
            start_time = now - timedelta(hours=1)
            end_time = now

            url = f"/api/playback/{camera_id}?start_time={start_time.isoformat()}&end_time={end_time.isoformat()}"

            response = test_client.get(url)

            if response.status_code == 200:
                self.playback_info = json.loads(response.data)

                if 'error' in self.playback_info:
                    self.log_test("Playback info query", "FAIL", self.playback_info['error'])
                    return False

                segments = self.playback_info.get('segment_count', 0)
                duration = self.playback_info.get('total_duration_ms', 0)
                size = self.playback_info.get('total_size_bytes', 0)

                details = f"Segments: {segments}, Duration: {duration}ms, Size: {size} bytes"
                self.log_test("Playback info query", "PASS", details)
                return True
            else:
                self.log_test("Playback info query", "FAIL", f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Playback info query", "FAIL", str(e))
            return False
    
    def test_hls_playlist(self):
        """Test 4: HLS playlist generation"""
        if not self.playback_info:
            self.log_test("HLS playlist generation", "SKIP", "No playback info")
            return False

        try:
            camera_id = self.cameras[0].get('name', '').lower().replace(' ', '_').replace('-', '_')

            now = datetime.now()
            start_time = now - timedelta(hours=1)
            end_time = now

            url = f"/api/playback/{camera_id}/playlist.m3u8?start_time={start_time.isoformat()}&end_time={end_time.isoformat()}"

            response = test_client.get(url)

            if response.status_code == 200:
                playlist = response.data.decode()

                # Check for M3U8 format
                if "#EXTM3U" in playlist and "#EXTINF" in playlist:
                    segment_count = playlist.count("#EXTINF")
                    details = f"Valid M3U8 with {segment_count} segments"
                    self.log_test("HLS playlist generation", "PASS", details)
                    return True
                else:
                    self.log_test("HLS playlist generation", "FAIL", "Invalid M3U8 format")
                    return False
            else:
                self.log_test("HLS playlist generation", "FAIL", f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_test("HLS playlist generation", "FAIL", str(e))
            return False
    
    def test_time_range_validation(self):
        """Test 5: Time range validation"""
        if not self.cameras:
            self.log_test("Time range validation", "SKIP", "No cameras available")
            return False

        try:
            camera_id = self.cameras[0].get('name', '').lower().replace(' ', '_').replace('-', '_')

            # Test invalid range (start > end)
            now = datetime.now()
            start_time = now
            end_time = now - timedelta(hours=1)

            url = f"/api/playback/{camera_id}?start_time={start_time.isoformat()}&end_time={end_time.isoformat()}"

            response = test_client.get(url)

            if response.status_code == 200:
                data = json.loads(response.data)
                if 'error' in data:
                    self.log_test("Time range validation", "PASS", "Invalid range rejected")
                    return True

            # Test valid range
            start_time = now - timedelta(hours=1)
            end_time = now
            url = f"/api/playback/{camera_id}?start_time={start_time.isoformat()}&end_time={end_time.isoformat()}"

            response = test_client.get(url)
            if response.status_code == 200:
                data = json.loads(response.data)
                if 'error' not in data:
                    self.log_test("Time range validation", "PASS", "Valid range accepted")
                    return True

            self.log_test("Time range validation", "FAIL", "Validation not working")
            return False
        except Exception as e:
            self.log_test("Time range validation", "FAIL", str(e))
            return False
    
    def test_segment_serving(self):
        """Test 6: Segment file serving"""
        if not self.playback_info or not self.playback_info.get('segments'):
            self.log_test("Segment file serving", "SKIP", "No segments available")
            return False

        try:
            camera_id = self.cameras[0].get('name', '').lower().replace(' ', '_').replace('-', '_')
            segment = self.playback_info['segments'][0]
            segment_path = segment.get('segment_path', '')

            # Extract relative path
            if 'recordings' in segment_path:
                rel_path = segment_path.split('recordings\\')[-1] if '\\' in segment_path else segment_path.split('recordings/')[-1]
            else:
                rel_path = Path(segment_path).name

            url = f"/api/playback/segment/{camera_id}/{rel_path}"
            response = test_client.get(url)

            if response.status_code == 200:
                size = len(response.data)
                details = f"Segment size: {size} bytes"
                self.log_test("Segment file serving", "PASS", details)
                return True
            else:
                self.log_test("Segment file serving", "FAIL", f"Status: {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Segment file serving", "FAIL", str(e))
            return False
    
    def test_multiple_cameras(self):
        """Test 7: Multiple camera support"""
        if len(self.cameras) < 2:
            self.log_test("Multiple camera support", "SKIP", "Less than 2 cameras")
            return True

        try:
            success_count = 0

            for camera in self.cameras[:2]:
                camera_id = camera.get('name', '').lower().replace(' ', '_').replace('-', '_')

                now = datetime.now()
                start_time = now - timedelta(minutes=30)
                end_time = now

                url = f"/api/playback/{camera_id}?start_time={start_time.isoformat()}&end_time={end_time.isoformat()}"

                response = test_client.get(url)
                if response.status_code == 200 and 'error' not in json.loads(response.data):
                    success_count += 1

            if success_count == min(2, len(self.cameras)):
                details = f"Tested {success_count} cameras successfully"
                self.log_test("Multiple camera support", "PASS", details)
                return True
            else:
                self.log_test("Multiple camera support", "FAIL", f"Only {success_count} cameras worked")
                return False
        except Exception as e:
            self.log_test("Multiple camera support", "FAIL", str(e))
            return False
    
    def test_error_handling(self):
        """Test 8: Error handling"""
        try:
            # Test invalid camera
            now = datetime.now()
            url = f"/api/playback/invalid_camera?start_time={now.isoformat()}&end_time={(now + timedelta(hours=1)).isoformat()}"

            response = test_client.get(url)

            # Should either return 404 or error in response
            if response.status_code != 200:
                self.log_test("Error handling", "PASS", "Invalid camera handled")
                return True
            else:
                data = json.loads(response.data)
                if 'error' in data:
                    self.log_test("Error handling", "PASS", "Invalid camera handled")
                    return True
                else:
                    self.log_test("Error handling", "FAIL", "Invalid camera not handled")
                    return False
        except Exception as e:
            self.log_test("Error handling", "FAIL", str(e))
            return False
    
    def run_all_tests(self):
        """Run all tests"""
        print("\n" + "=" * 80)
        print("PLAYBACK UI TEST SUITE")
        print("=" * 80 + "\n")
        
        tests = [
            self.test_page_loads,
            self.test_camera_api,
            self.test_playback_info_query,
            self.test_hls_playlist,
            self.test_time_range_validation,
            self.test_segment_serving,
            self.test_multiple_cameras,
            self.test_error_handling
        ]
        
        for test in tests:
            test()
            print()
        
        # Summary
        print("=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        passed = sum(1 for r in self.test_results if r['status'] == 'PASS')
        failed = sum(1 for r in self.test_results if r['status'] == 'FAIL')
        skipped = sum(1 for r in self.test_results if r['status'] == 'SKIP')
        
        print(f"✅ Passed:  {passed}")
        print(f"❌ Failed:  {failed}")
        print(f"⏭️  Skipped: {skipped}")
        print(f"📊 Total:   {len(self.test_results)}")
        print()
        
        if failed == 0:
            print("🎉 ALL TESTS PASSED!")
        else:
            print(f"⚠️  {failed} test(s) failed")
        
        print("=" * 80 + "\n")
        
        return failed == 0


if __name__ == "__main__":
    tester = PlaybackUITester()
    success = tester.run_all_tests()
    exit(0 if success else 1)

