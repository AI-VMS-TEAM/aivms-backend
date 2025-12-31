#!/bin/bash
# AIVMS Backend - Digital Ocean Deployment Script
# Run this script on a fresh Ubuntu droplet with Docker installed

set -e

echo "=========================================="
echo "AIVMS Backend - Digital Ocean Deployment"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root${NC}"
    exit 1
fi

# Variables
APP_DIR="/opt/aivms"
BACKUP_DIR="/opt/aivms-backups"

echo -e "${YELLOW}Step 1: Updating system...${NC}"
apt update && apt upgrade -y

echo -e "${YELLOW}Step 2: Installing dependencies...${NC}"
apt install -y curl wget git ufw

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Step 3: Installing Docker...${NC}"
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
else
    echo -e "${GREEN}Docker already installed${NC}"
fi

# Install Docker Compose plugin if not present
if ! docker compose version &> /dev/null; then
    echo -e "${YELLOW}Installing Docker Compose plugin...${NC}"
    apt install -y docker-compose-plugin
fi

echo -e "${YELLOW}Step 4: Creating directories...${NC}"
mkdir -p $APP_DIR
mkdir -p $BACKUP_DIR
mkdir -p $APP_DIR/nginx
mkdir -p $APP_DIR/logs

echo -e "${YELLOW}Step 5: Configuring firewall...${NC}"
ufw --force enable
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw allow 3000/tcp  # AIVMS Backend
ufw allow 8554/tcp  # RTSP
ufw allow 8888/tcp  # HLS
ufw allow 5555/tcp  # MediaMTX API

echo -e "${YELLOW}Step 6: Setting up application...${NC}"
cd $APP_DIR

# Check if config exists, if not create from template
if [ ! -f "config.ini" ]; then
    if [ -f "config.ini.docker" ]; then
        cp config.ini.docker config.ini
        echo -e "${YELLOW}Created config.ini from template. Please edit it with your settings.${NC}"
    fi
fi

# Create systemd service for auto-start
echo -e "${YELLOW}Step 7: Creating systemd service...${NC}"
cat > /etc/systemd/system/aivms.service << 'EOF'
[Unit]
Description=AIVMS Backend Docker Compose
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/aivms
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable aivms.service

echo -e "${YELLOW}Step 8: Creating helper scripts...${NC}"

# Create start script
cat > $APP_DIR/start.sh << 'EOF'
#!/bin/bash
cd /opt/aivms
docker compose up -d
echo "AIVMS services started"
docker compose ps
EOF
chmod +x $APP_DIR/start.sh

# Create stop script
cat > $APP_DIR/stop.sh << 'EOF'
#!/bin/bash
cd /opt/aivms
docker compose down
echo "AIVMS services stopped"
EOF
chmod +x $APP_DIR/stop.sh

# Create restart script
cat > $APP_DIR/restart.sh << 'EOF'
#!/bin/bash
cd /opt/aivms
docker compose restart
echo "AIVMS services restarted"
docker compose ps
EOF
chmod +x $APP_DIR/restart.sh

# Create logs script
cat > $APP_DIR/logs.sh << 'EOF'
#!/bin/bash
cd /opt/aivms
docker compose logs -f ${1:-}
EOF
chmod +x $APP_DIR/logs.sh

# Create update script
cat > $APP_DIR/update.sh << 'EOF'
#!/bin/bash
cd /opt/aivms
echo "Pulling latest changes..."
git pull origin main 2>/dev/null || echo "Not a git repo, skipping pull"
echo "Rebuilding containers..."
docker compose build --no-cache
echo "Restarting services..."
docker compose up -d
echo "Update complete!"
docker compose ps
EOF
chmod +x $APP_DIR/update.sh

# Create backup script
cat > $APP_DIR/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/aivms-backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

echo "Creating backup..."
# Backup database
docker cp aivms-backend:/app/data/recordings.db $BACKUP_DIR/recordings_$DATE.db 2>/dev/null || echo "No database to backup"

# Backup config files
tar -czf $BACKUP_DIR/config_$DATE.tar.gz config.ini cameras.json mediamtx.yml 2>/dev/null || echo "Config backup created"

# Keep only last 7 backups
cd $BACKUP_DIR
ls -t recordings_*.db 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null
ls -t config_*.tar.gz 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null

echo "Backup complete: $BACKUP_DIR"
ls -la $BACKUP_DIR
EOF
chmod +x $APP_DIR/backup.sh

# Create status script
cat > $APP_DIR/status.sh << 'EOF'
#!/bin/bash
cd /opt/aivms
echo "========== Container Status =========="
docker compose ps
echo ""
echo "========== Resource Usage =========="
docker stats --no-stream
echo ""
echo "========== Health Check =========="
curl -s http://localhost:3000/api/health | python3 -m json.tool 2>/dev/null || echo "Backend not responding"
EOF
chmod +x $APP_DIR/status.sh

# Setup cron for daily backups
echo -e "${YELLOW}Step 9: Setting up automated backups...${NC}"
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/aivms/backup.sh > /opt/aivms/logs/backup.log 2>&1") | crontab -

echo ""
echo -e "${GREEN}=========================================="
echo "Deployment setup complete!"
echo "==========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Copy your application files to: $APP_DIR"
echo "2. Edit configuration: nano $APP_DIR/config.ini"
echo "3. Edit cameras: nano $APP_DIR/cameras.json"
echo "4. Start services: cd $APP_DIR && ./start.sh"
echo ""
echo "Available scripts:"
echo "  ./start.sh   - Start all services"
echo "  ./stop.sh    - Stop all services"
echo "  ./restart.sh - Restart all services"
echo "  ./logs.sh    - View logs (add service name for specific)"
echo "  ./status.sh  - Check status and health"
echo "  ./update.sh  - Update and rebuild"
echo "  ./backup.sh  - Backup database and configs"
echo ""
echo -e "${YELLOW}Don't forget to update your config.ini and cameras.json!${NC}"
