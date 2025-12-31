# AI Video Management System (AIVMS)

Advanced AI-powered video surveillance system with real-time object detection, tracking, and zone-based analytics.

## 🚀 Features

- **Real-time Object Detection** - YOLO11-based detection with GPU acceleration
- **Multi-Object Tracking** - ByteTrack algorithm for accurate tracking
- **Zone-based Analytics** - Define custom zones for counting and analytics
- **HLS Streaming** - Low-latency video streaming via MediaMTX
- **Recording Management** - Automatic retention policy with configurable storage
- **Web Dashboard** - Modern web interface for monitoring and configuration
- **RESTful API** - Complete API for integration with other systems

## 📋 Prerequisites

- **Python 3.12+**
- **CUDA-capable GPU** (recommended for real-time performance)
- **Windows 10/11** (or Linux with modifications)
- **Git**

## 🛠️ Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/aivms-backend.git
cd aivms-backend
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Download MediaMTX

MediaMTX is not included in the repository due to its size. Download it separately:

1. Go to [MediaMTX Releases](https://github.com/bluenviron/mediamtx/releases)
2. Download the latest Windows release (e.g., `mediamtx_vX.X.X_windows_amd64.zip`)
3. Extract `mediamtx.exe` to the project root directory

### 4. Download YOLO Models

YOLO models are not included in the repository. Download them separately:

```bash
# Download YOLO11 model (recommended)
wget https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m.pt

# Or use Python
python -c "from ultralytics import YOLO; YOLO('yolo11m.pt')"
```

Place the `.pt` file in the project root directory.

### 5. Configure the System

Edit `config.ini` to match your setup:

```ini
[cameras]
camera_count = 4

[camera_1]
name = Front Camera
rtsp_url = rtsp://your-camera-ip:554/stream
```

### 6. Create Required Directories

```bash
mkdir recordings
mkdir public\hls
```

## 🎯 Quick Start

### Start MediaMTX

```bash
.\mediamtx.exe
```

### Start Flask Server

```bash
python app.py
```

### Access Web Dashboard

Open your browser and navigate to:
```
http://localhost:5000
```

## 📁 Project Structure

```
aivms-backend/
├── app.py                 # Main Flask application
├── config.ini             # Configuration file
├── mediamtx.yml          # MediaMTX configuration
├── requirements.txt       # Python dependencies
├── services/             # Core services
│   ├── detection_service.py
│   ├── recording_service.py
│   ├── retention_manager.py
│   └── zone_service.py
├── routes/               # API routes
├── public/               # Web frontend
└── models/               # Database models
```

## ⚙️ Configuration

### Retention Policy

Configure automatic cleanup of old recordings in `config.ini`:

```ini
[retention]
retention_days = 7
cleanup_interval_hours = 1
```

### Detection Settings

```ini
[detection]
model_path = yolo11m.pt
confidence_threshold = 0.5
iou_threshold = 0.45
```

## 📊 API Documentation

### Get Detections

```http
GET /api/detections?camera_id=cam1&start_time=<timestamp>&end_time=<timestamp>
```

### Get Recordings

```http
GET /api/recordings?camera_id=cam1&date=2025-12-31
```

### Zone Management

```http
POST /api/zones
GET /api/zones/<camera_id>
PUT /api/zones/<zone_id>
DELETE /api/zones/<zone_id>
```

## 🔧 Troubleshooting

### GPU Not Detected

Ensure CUDA is properly installed:
```bash
python -c "import torch; print(torch.cuda.is_available())"
```

### HLS Streaming Issues

Check MediaMTX logs and ensure cameras are accessible:
```bash
curl rtsp://your-camera-ip:554/stream
```

### Database Issues

Reset the database:
```bash
del recordings.db
python app.py  # Will recreate database
```

## 📝 License

MIT License - See LICENSE file for details

## 🤝 Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## 📧 Support

For issues and questions, please open a GitHub issue.

