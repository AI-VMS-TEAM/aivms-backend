# AIVMS Edge/Cloud Architecture

This document describes the split architecture for AI Video Management System.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                           CLOUD SERVER                               │
│                    (DigitalOcean / AWS / Azure)                      │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Flask + SocketIO                                               │ │
│  │  - Tenant Management (multi-tenant SaaS)                        │ │
│  │  - User Authentication (JWT)                                     │ │
│  │  - Event Storage & Queries                                       │ │
│  │  - Alert Processing & Notifications                              │ │
│  │  - Edge Device Management                                        │ │
│  │  - Dashboard API                                                 │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                              ▲                                       │
└──────────────────────────────┼───────────────────────────────────────┘
                               │ WebSocket (persistent)
                               │ REST API (backup)
                               │
       ┌───────────────────────┼───────────────────────┐
       │                       │                       │
       ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   EDGE BOX #1   │    │   EDGE BOX #2   │    │   EDGE BOX #3   │
│   (On-Premise)  │    │   (On-Premise)  │    │   (On-Premise)  │
├─────────────────┤    ├─────────────────┤    ├─────────────────┤
│ • YOLO/RT-DETR  │    │ • YOLO/RT-DETR  │    │ • YOLO/RT-DETR  │
│ • 24/7 Recording│    │ • 24/7 Recording│    │ • 24/7 Recording│
│ • Zone Detection│    │ • Zone Detection│    │ • Zone Detection│
│ • Local Storage │    │ • Local Storage │    │ • Local Storage │
│ • Clip Extraction│   │ • Clip Extraction│   │ • Clip Extraction│
└─────────────────┘    └─────────────────┘    └─────────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
   [IP Cameras]           [IP Cameras]           [IP Cameras]
```

## Components

### Edge Box (On-Premise)
- **Location**: Customer's network, near cameras
- **Hardware**: Mini PC with GPU (NVIDIA Jetson, Intel NUC with GPU, etc.)
- **Responsibilities**:
  - ML inference (YOLO/RT-DETR object detection)
  - 24/7 video recording to local storage
  - Zone monitoring (enter/exit/dwell detection)
  - Event clip extraction
  - Sending events to cloud

### Cloud Server
- **Location**: DigitalOcean, AWS, Azure, etc.
- **Responsibilities**:
  - Multi-tenant management
  - User authentication & authorization
  - Event aggregation from all edge devices
  - Alert processing & notifications (email, webhook)
  - Dashboard API for web/mobile clients
  - Edge device registration & management

## Directory Structure

```
aivms-backend/
├── edge/                    # Edge device application
│   ├── app.py              # Main edge application
│   ├── config.py           # Edge configuration
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   └── services/
│       ├── cloud_connector.py   # WebSocket to cloud
│       └── event_uploader.py    # Clip upload service
│
├── cloud/                   # Cloud server application
│   ├── app.py              # Main cloud application
│   ├── config.py           # Cloud configuration
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── nginx.conf          # Reverse proxy config
│   ├── requirements.txt
│   ├── controllers/
│   │   ├── auth_routes.py      # Authentication
│   │   ├── tenant_routes.py    # Tenant & edge management
│   │   ├── event_routes.py     # Events & alerts API
│   │   └── edge_routes.py      # Edge REST API
│   └── services/
│       ├── tenant_service.py   # Multi-tenancy
│       ├── event_service.py    # Event storage
│       ├── alert_service.py    # Alert processing
│       └── edge_manager.py     # Edge WebSocket handling
```

## Deployment

### Cloud Server

1. **Set up the server** (DigitalOcean droplet, etc.):
```bash
# SSH into server
ssh root@your-server-ip

# Clone the repo
git clone https://github.com/your-repo/aivms-backend.git
cd aivms-backend/cloud

# Configure environment
cp .env.example .env
nano .env  # Edit with your settings
```

2. **Start with Docker**:
```bash
docker-compose up -d
```

3. **For production with HTTPS**:
```bash
# Generate SSL certs (Let's Encrypt)
certbot certonly --standalone -d your-domain.com

# Copy certs
mkdir -p certs
cp /etc/letsencrypt/live/your-domain.com/fullchain.pem certs/
cp /etc/letsencrypt/live/your-domain.com/privkey.pem certs/

# Start with nginx
docker-compose --profile production up -d
```

### Edge Device

1. **Set up hardware**:
   - Install Ubuntu/Debian
   - Install NVIDIA drivers (if using GPU)
   - Install Docker

2. **Register edge in cloud dashboard**:
   - Login to cloud dashboard
   - Go to Settings > Edge Devices
   - Click "Add Edge Device"
   - Copy the `edge_id` and `edge_secret`

3. **Configure edge**:
```bash
git clone https://github.com/your-repo/aivms-backend.git
cd aivms-backend/edge

# Configure
cp .env.example .env
nano .env  # Add EDGE_ID, EDGE_SECRET, CLOUD_URL

# Configure cameras
nano cameras.json
```

4. **Start edge**:
```bash
docker-compose up -d
```

## API Reference

### Authentication

```bash
# Register new tenant
POST /api/auth/register
{
  "tenant_name": "Acme Corp",
  "email": "admin@acme.com",
  "password": "secret123",
  "name": "Admin User"
}

# Login
POST /api/auth/login
{
  "email": "admin@acme.com",
  "password": "secret123"
}
# Returns: { "token": "eyJ...", "user": {...} }

# Get current user
GET /api/auth/me
Authorization: Bearer <token>
```

### Edge Devices

```bash
# List edge devices
GET /api/tenant/edges
Authorization: Bearer <token>

# Register new edge
POST /api/tenant/edges
{
  "name": "Office Camera Box",
  "location": "Main Office"
}
# Returns: { "edge_id": "...", "edge_secret": "..." }

# Send command to edge
POST /api/tenant/edges/{edge_id}/command
{
  "command": "restart_detection",
  "payload": {}
}
```

### Events

```bash
# List detections
GET /api/events/detections?start_time=2024-01-01T00:00:00&object_class=person
Authorization: Bearer <token>

# List zone events
GET /api/events/zones?zone_id=zone_1&event_type=enter
Authorization: Bearer <token>

# List alerts
GET /api/events/alerts?acknowledged=false
Authorization: Bearer <token>

# Acknowledge alert
POST /api/events/alerts/{alert_id}/acknowledge
Authorization: Bearer <token>
```

### Analytics

```bash
# Detection counts by hour
GET /api/events/analytics/detections?group_by=hour
Authorization: Bearer <token>

# Zone activity summary
GET /api/events/analytics/zones
Authorization: Bearer <token>
```

## Edge-Cloud Communication

### WebSocket Events (Edge → Cloud)

```python
# Detection event
socketio.emit('detection', {
    'camera_id': 'cam_1',
    'timestamp': '2024-01-15T10:30:00',
    'object_class': 'person',
    'confidence': 0.95,
    'bbox': [100, 200, 300, 400],
    'track_id': 'track_123'
})

# Zone event
socketio.emit('zone_event', {
    'camera_id': 'cam_1',
    'zone_id': 'zone_restricted',
    'event_type': 'enter',
    'object_class': 'person',
    'timestamp': '2024-01-15T10:30:00'
})

# Alert
socketio.emit('alert', {
    'camera_id': 'cam_1',
    'alert_type': 'intrusion',
    'severity': 'high',
    'title': 'Intrusion Detected',
    'clip_path': '/clips/intrusion_20240115_103000.mp4'
})
```

### WebSocket Commands (Cloud → Edge)

```python
# Restart detection
{'command': 'restart_detection'}

# Update zones
{'command': 'update_zones', 'payload': {'zones': [...]}}

# Get status
{'command': 'get_status'}

# Request clip
{'command': 'request_clip', 'payload': {
    'camera_id': 'cam_1',
    'start_time': '2024-01-15T10:00:00',
    'duration': 60
}}
```

## Environment Variables

### Cloud Server

| Variable | Description | Default |
|----------|-------------|---------|
| JWT_SECRET | Secret for JWT tokens | dev-secret |
| DATABASE_PATH | SQLite database path | ./cloud.db |
| CLIP_UPLOAD_DIR | Directory for uploaded clips | ./clips |
| EDGE_TIMEOUT_SECONDS | Edge heartbeat timeout | 120 |
| SMTP_HOST | SMTP server for emails | - |
| WEBHOOK_URL | Webhook for alerts | - |

### Edge Device

| Variable | Description | Default |
|----------|-------------|---------|
| CLOUD_URL | Cloud server URL | - |
| EDGE_ID | Edge device ID | - |
| EDGE_SECRET | Edge authentication secret | - |
| DETECTION_MODEL | YOLO model to use | yolo11n.pt |
| DETECTION_CONFIDENCE | Min confidence threshold | 0.5 |
| DETECTION_FPS | Detection frame rate | 5 |
| RECORDING_RETENTION_DAYS | Days to keep recordings | 7 |

## Security Considerations

1. **Always use HTTPS** for cloud server
2. **Keep edge secrets secure** - they're shown only once
3. **Use strong JWT secrets** in production
4. **Rotate edge secrets** periodically
5. **Use VPN/Tailscale** if edge devices need extra security
6. **Enable firewall** on edge devices - only allow outbound to cloud

## Scaling

- **Multiple edge devices**: Each tenant can have multiple edges
- **Multiple tenants**: Cloud supports multi-tenancy out of the box
- **Database**: Upgrade from SQLite to PostgreSQL for production
- **Load balancing**: Add more cloud instances behind a load balancer
- **Storage**: Use S3/GCS for clip storage at scale
