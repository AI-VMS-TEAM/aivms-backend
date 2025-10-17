import os
import json
import cv2
from urllib.parse import quote

class CameraManager:
    def __init__(self, config_file):
        self.config_file = config_file
        self.cameras = self.load_cameras_from_file()
        print(f"CameraManager initialized with {len(self.cameras)} camera(s).")

    def load_cameras_from_file(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print("Warning: cameras.json is corrupted. Starting fresh.")
                return []
        return []

    def save_cameras_to_file(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.cameras, f, indent=4)

    def verify_rtsp_url(self, rtsp_url):
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        if cap.isOpened():
            cap.release()
            return True
        else:
            cap.release()
            return False

    def add_camera(self, data):
        address = data['ip']
        if data.get('port'):
            address += f":{data['port']}"
        
        path = data.get('path', '').lstrip('/')
        
        rtsp_url = f"rtsp://{quote(data['username'])}:{quote(data['password'])}@{address}/{path}"

        if self.verify_rtsp_url(rtsp_url):
            new_camera = { 'name': data['name'], 'ip': data['ip'], 'port': data.get('port', ''), 'username': data['username'], 'password': data['password'], 'path': path }
            self.cameras.append(new_camera)
            self.save_cameras_to_file()
            return new_camera, None
        else:
            return None, "Could not connect to the RTSP stream."