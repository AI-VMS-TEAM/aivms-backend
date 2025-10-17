import configparser
from flask import Flask
from models.camera_manager import CameraManager
from services.stream_service import StreamManager
from controllers.main_routes import create_blueprint

# --- Initialization ---
app = Flask(__name__, static_folder='public', static_url_path='')

config = configparser.ConfigParser()
config.read('config.ini')
NVR_IP_ADDRESS = config.get('Network', 'nvr_ip', fallback='127.0.0.1')
print(f"Using NVR IP Address from config: {NVR_IP_ADDRESS}")

camera_manager = CameraManager('cameras.json')
stream_manager = StreamManager(camera_manager.cameras)

# Create and register the blueprint (Controller)
main_routes = create_blueprint(camera_manager, stream_manager, NVR_IP_ADDRESS)
app.register_blueprint(main_routes)

# --- Main Execution ---
if __name__ == '__main__':
    stream_manager.start_all_streams()
    app.run(host='0.0.0.0', port=3000)