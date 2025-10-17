import os
import subprocess
import threading
import time
from urllib.parse import quote

# The path needs to go up one level from 'services' to find the 'public' folder
HLS_BASE_DIR = os.path.join(os.path.dirname(__file__), '..', 'public', 'hls')

class StreamManager:
    def __init__(self, cameras):
        self.cameras = cameras

    def start_all_streams(self):
        """Loops through all configured cameras and starts their streams."""
        for i, cam_config in enumerate(self.cameras):
            self.start_single_stream(cam_config, i + 1)

    def start_single_stream(self, cam_config, cam_id):
        """Starts the main and sub stream FFmpeg processes for a single camera."""
        address = cam_config['ip']
        if cam_config.get('port'):
            address += f":{cam_config['port']}"
        path = cam_config.get('path', '').lstrip('/')
        full_rtsp_url = f"rtsp://{quote(cam_config['username'])}:{quote(cam_config['password'])}@{address}/{path}"

        # Start main stream process (low-latency re-encode)
        main_hls_dir = os.path.join(HLS_BASE_DIR, f"cam{cam_id}_main")
        main_thread = threading.Thread(target=self._start_ffmpeg_process, args=(f"cam{cam_id}_main", full_rtsp_url, main_hls_dir, True), daemon=True)
        main_thread.start()
        
        # Start sub stream process (now also using re-encode for stability)
        sub_hls_dir = os.path.join(HLS_BASE_DIR, f"cam{cam_id}_sub")
        sub_thread = threading.Thread(target=self._start_ffmpeg_process, args=(f"cam{cam_id}_sub", full_rtsp_url, sub_hls_dir, False), daemon=True)
        sub_thread.start()

    def _start_ffmpeg_process(self, stream_name, rtsp_url, hls_dir, is_main):
        """The core FFmpeg process runner."""
        os.makedirs(hls_dir, exist_ok=True)
        print(f"Starting FFmpeg for {stream_name}...")
        while True:
            try:
                if is_main: # Low-latency re-encode for main streams
                    command = ['ffmpeg', '-rtsp_transport', 'tcp', '-i', rtsp_url, '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency', '-g', '25', '-c:a', 'aac', '-f', 'hls', '-hls_time', '1', '-hls_list_size', '3', '-hls_flags', 'delete_segments', os.path.join(hls_dir, 'stream.m3u8')]
                else: # --- FIX IS HERE ---
                      # Use a stable re-encode for ALL substreams to prevent crashing and frozen video
                    command = ['ffmpeg', '-rtsp_transport', 'tcp', '-i', rtsp_url, '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency', '-c:a', 'aac', '-f', 'hls', '-hls_time', '2', '-hls_list_size', '5', '-hls_flags', 'delete_segments', os.path.join(hls_dir, 'stream.m3u8')]
                
                subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
            except Exception as e:
                print(f"Error in FFmpeg for {stream_name}. Stderr: {e.stderr.decode() if hasattr(e, 'stderr') else e}")
            print(f"FFmpeg for {stream_name} stopped. Restarting in 5 seconds...")
            time.sleep(5)