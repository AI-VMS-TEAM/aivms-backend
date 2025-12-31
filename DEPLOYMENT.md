# AIVMS Backend - Digital Ocean Deployment Guide

## Prerequisites

- Digital Ocean account
- Domain name (optional but recommended)
- SSH key configured

## Recommended Droplet Specs

### Minimum (Testing/Development)
- **Type**: Basic Droplet
- **CPU**: 2 vCPUs
- **RAM**: 4 GB
- **Storage**: 80 GB SSD
- **Cost**: ~$24/month

### Recommended (Production)
- **Type**: CPU-Optimized or General Purpose
- **CPU**: 4 vCPUs
- **RAM**: 8 GB
- **Storage**: 160 GB SSD (NVMe preferred)
- **Cost**: ~$48-80/month

### With GPU (Heavy AI Workloads)
- **Type**: GPU Droplet (H100, A100)
- **GPU**: NVIDIA GPU
- **RAM**: 16+ GB
- **Storage**: 320 GB NVMe
- **Cost**: ~$2-4/hour

## Quick Start Deployment

### 1. Create Droplet

```bash
# Using doctl CLI
doctl compute droplet create aivms-server \
  --image docker-20-04 \
  --size s-4vcpu-8gb \
  --region nyc1 \
  --ssh-keys YOUR_SSH_KEY_ID \
  --tag-names aivms,production
```

Or use the Digital Ocean web console:
1. Go to Droplets → Create Droplet
2. Choose **Docker** from Marketplace (Ubuntu 22.04)
3. Select your plan
4. Add your SSH key
5. Create Droplet

### 2. Initial Server Setup

SSH into your droplet:
```bash
ssh root@YOUR_DROPLET_IP
```

Run initial setup:
```bash
# Update system
apt update && apt upgrade -y

# Install Docker Compose (if not included)
apt install docker-compose-plugin -y

# Create app user (optional but recommended)
useradd -m -s /bin/bash aivms
usermod -aG docker aivms

# Create project directory
mkdir -p /opt/aivms
cd /opt/aivms
```

### 3. Deploy Application

Transfer your code to the server:
```bash
# From your local machine
scp -r ./* root@YOUR_DROPLET_IP:/opt/aivms/
```

Or clone from Git:
```bash
cd /opt/aivms
git clone https://github.com/YOUR_USERNAME/aivms-backend.git .
```

### 4. Configure the Application

```bash
cd /opt/aivms

# Copy and edit configuration
cp config.ini.docker config.ini
nano config.ini  # Edit with your camera settings

# Edit MediaMTX configuration for your cameras
nano mediamtx.yml

# Create cameras.json with your camera configuration
nano cameras.json
```

Example `cameras.json`:
```json
[
  {
    "name": "Front Camera",
    "rtsp_url": "rtsp://admin:password@192.168.1.100:554/stream",
    "enabled": true
  },
  {
    "name": "Back Camera", 
    "rtsp_url": "rtsp://admin:password@192.168.1.101:554/stream",
    "enabled": true
  }
]
```

### 5. Start the Services

```bash
# Build and start all services
docker compose up -d --build

# Check status
docker compose ps

# View logs
docker compose logs -f backend
```

### 6. Configure Firewall (UFW)

```bash
# Enable UFW
ufw enable

# Allow SSH
ufw allow 22/tcp

# Allow HTTP/HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# Allow AIVMS Backend
ufw allow 3000/tcp

# Allow MediaMTX ports
ufw allow 8554/tcp   # RTSP
ufw allow 8888/tcp   # HLS
ufw allow 5555/tcp   # MediaMTX API

# Check status
ufw status
```

## Production Configuration

### Enable HTTPS with Let's Encrypt

1. Install Certbot:
```bash
apt install certbot python3-certbot-nginx -y
```

2. Create Nginx configuration:
```bash
mkdir -p /opt/aivms/nginx
cat > /opt/aivms/nginx/nginx.conf << 'EOF'
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server backend:3000;
    }

    upstream mediamtx_hls {
        server mediamtx:8888;
    }

    server {
        listen 80;
        server_name YOUR_DOMAIN;

        location / {
            proxy_pass http://backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /hls/ {
            proxy_pass http://mediamtx_hls/;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
        }

        location /socket.io/ {
            proxy_pass http://backend/socket.io/;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
        }
    }
}
EOF
```

3. Start with Nginx profile:
```bash
docker compose --profile with-nginx up -d
```

4. Get SSL certificate:
```bash
certbot --nginx -d YOUR_DOMAIN
```

### Setup Auto-Updates with Watchtower

```bash
docker compose --profile with-watchtower up -d
```

## Monitoring & Maintenance

### View Logs
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend

# Last 100 lines
docker compose logs --tail=100 backend
```

### Check Health
```bash
# Container status
docker compose ps

# Resource usage
docker stats

# API health check
curl http://localhost:3000/api/health
```

### Restart Services
```bash
# Restart all
docker compose restart

# Restart specific service
docker compose restart backend
```

### Update Application
```bash
cd /opt/aivms

# Pull latest code
git pull origin main

# Rebuild and restart
docker compose up -d --build
```

### Backup Data
```bash
# Backup recordings database
docker compose exec backend cp /app/data/recordings.db /app/data/recordings.db.bak

# Export to host
docker cp aivms-backend:/app/data/recordings.db ./backup/

# Backup recordings (if needed)
tar -czf recordings-backup.tar.gz /var/lib/docker/volumes/aivms-backend_recordings_data/
```

## Troubleshooting

### Container Won't Start
```bash
# Check logs
docker compose logs backend

# Check configuration
docker compose config

# Rebuild from scratch
docker compose down
docker compose build --no-cache
docker compose up -d
```

### High CPU Usage
```bash
# Reduce detection FPS in config.ini
detection_fps = 2.0

# Reduce worker threads
worker_threads = 1

# Restart
docker compose restart backend
```

### Out of Memory
```bash
# Check memory usage
free -h
docker stats

# Add swap space
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

### Camera Connection Issues
```bash
# Test RTSP from container
docker compose exec backend python -c "
import cv2
cap = cv2.VideoCapture('rtsp://admin:password@IP:554/stream')
print('Connected:', cap.isOpened())
cap.release()
"

# Check MediaMTX logs
docker compose logs mediamtx
```

## Security Recommendations

1. **Change default credentials** in `config.ini` and `cameras.json`
2. **Use environment variables** for sensitive data:
   ```yaml
   environment:
     - DB_PASSWORD=${DB_PASSWORD}
   ```
3. **Enable HTTPS** with proper SSL certificates
4. **Restrict firewall** to only necessary ports
5. **Regular updates**: `docker compose pull && docker compose up -d`
6. **Monitor logs** for suspicious activity
7. **Use SSH keys** instead of passwords

## Performance Tuning

### For CPU-Only Droplets
```ini
[Detection]
model = yolo11n          # Use nano model
detection_fps = 2.0      # Lower FPS
use_gpu = false

[Performance]
worker_threads = 1
max_queue_size = 30
enable_frame_skip = true
```

### For GPU Droplets
```ini
[Detection]
model = rtdetr-l         # Use larger model
detection_fps = 15.0     # Higher FPS
use_gpu = true

[Performance]
worker_threads = 4
max_queue_size = 100
```

## Support

For issues or questions:
- Check logs: `docker compose logs -f`
- Review this guide
- Open an issue on GitHub
