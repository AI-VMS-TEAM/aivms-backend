import yaml
from pathlib import Path

config_file = Path('config/zones.yaml')
with open(config_file, 'r') as f:
    config = yaml.safe_load(f)

print('Cameras in zone config:')
for camera_id in config['cameras'].keys():
    print(f'  - {camera_id}')
    zones = config['cameras'][camera_id].get('zones', [])
    print(f'    Zones: {len(zones)}')
    for zone in zones:
        print(f'      - {zone.get("name")}')

print('\n' + '=' * 60)
print('Camera ID mapping from cameras.json:')

import json
with open('cameras.json', 'r') as f:
    cameras = json.load(f)

for camera in cameras:
    name = camera.get('name', '')
    # Convert to camera_id format
    camera_id = name.lower().replace(' ', '_').replace('-', '_')
    print(f'  {name} -> {camera_id}')

