# AIVMS Edge Device
# Runs ML inference and video recording locally

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY edge/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy edge application
COPY edge/ /app/
COPY config/ /app/config/
COPY services/detection_service.py /app/services/
COPY services/tracking_service.py /app/services/
COPY services/zone_service.py /app/services/
COPY services/recording_engine.py /app/services/
COPY services/frame_extractor.py /app/services/

# Create directories
RUN mkdir -p /app/storage/recordings /app/storage/clips /app/models

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV EDGE_STORAGE_PATH=/app/storage

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
    CMD curl -f http://localhost:5000/health || exit 1

# Run edge application
CMD ["python", "app.py"]
