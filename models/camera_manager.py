import os
import json
import cv2
from urllib.parse import quote
import requests
from ruamel.yaml import YAML

class CameraManager:
    def __init__(self, json_config, yaml_config):
        self.json_config_file = json_config
        self.yaml_config_file = yaml_config
        self.yaml = YAML()
        self.cameras = self.load_cameras_from_json()
        print(f"CameraManager initialized with {len(self.cameras)} camera(s).")

    def load_cameras_from_json(self):
        """Loads the camera list from the simple JSON file for the UI."""
        if os.path.exists(self.json_config_file):
            try:
                with open(self.json_config_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: {self.json_config_file} is corrupted. Starting fresh.")
                return []
        return []

    def save_cameras_to_json(self):
        """Saves the current camera list to the simple JSON file for the UI."""
        with open(self.json_config_file, 'w') as f:
            json.dump(self.cameras, f, indent=4)

    def add_camera_to_yaml(self, camera_name_slug, camera_config):
        """Adds a new camera path to the mediamtx.yml file."""
        if not os.path.exists(self.yaml_config_file):
            with open(self.yaml_config_file, 'w') as f: self.yaml.dump({'paths': {}}, f)

        with open(self.yaml_config_file, 'r') as f:
            config = self.yaml.load(f)
        
        if 'paths' not in config or config['paths'] is None:
            config['paths'] = {}
        
        # Add the new camera path
        config['paths'][camera_name_slug] = camera_config

        with open(self.yaml_config_file, 'w') as f:
            self.yaml.dump(config, f)

    def trigger_mediamtx_reload(self):
        """Sends an API request to MediaMTX to reload its configuration."""
        try:
            print("Sending reload command to MediaMTX server...")
            response = requests.post("http://localhost:5555/v3/config/paths/reload")  # API is on 5555
            if response.status_code == 200:
                print("MediaMTX reloaded successfully.")
                return True
            else:
                print(f"Failed to reload MediaMTX. Status: {response.status_code}")
                return False
        except requests.exceptions.ConnectionError as e:
            print(f"Could not connect to MediaMTX API: {e}")
            return False

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
            new_camera_for_json = { 'name': data['name'], 'ip': data['ip'], 'port': data.get('port', ''), 'username': data['username'], 'password': data['password'], 'path': path }
            
            # 1. Update the UI's JSON file
            self.cameras.append(new_camera_for_json)
            self.save_cameras_to_json()

            # 2. Update the engine's YAML file
            camera_name_slug = data['name'].lower().replace(' ', '_').replace('-', '_')
            camera_config_for_yaml = {'source': rtsp_url}
            self.add_camera_to_yaml(camera_name_slug, camera_config_for_yaml)
            
            # 3. Tell the engine to reload
            self.trigger_mediamtx_reload()
            
            return new_camera_for_json, None
        else:
            return None, "Could not connect to the RTSP stream."