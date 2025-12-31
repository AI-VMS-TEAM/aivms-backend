# AIVMS Backend - Multi-stage Dockerfile
# Optimized for Digital Ocean Droplet with GPU support

# ============================================
# Stage 1: Builder
# ============================================
FROM python:3.12-slim-bookworm AS builder

WORKDIR /app

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install PyTorch with CUDA support and other dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    Flask==3.1.2 \
    Flask-CORS==6.0.1 \
    Flask-SocketIO==5.5.1 \
    python-socketio==5.15.0 \
    requests==2.32.5 \
    pyyaml==6.0.3 \
    psutil==7.1.3 \
    ruamel.yaml==0.18.5 \
    bcrypt==4.1.2 \
    numpy==2.2.6 \
    scipy==1.16.3 \
    polars==1.35.2 \
    opencv-python-headless==4.10.0.84 \
    gunicorn==23.0.0 \
    eventlet==0.37.0 \
    lap==0.5.12

# Install PyTorch (CPU version for Digital Ocean - most droplets don't have GPU)
# For GPU droplet, uncomment the CUDA version below
RUN pip install --no-cache-dir \
    torch==2.5.1 \
    torchvision==0.20.1 \
    --index-url https://download.pytorch.org/whl/cpu

# Install YOLO
RUN pip install --no-cache-dir ultralytics==8.3.233

# ============================================
# Stage 2: Runtime
# ============================================
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=appuser:appuser . .

# Create necessary directories
RUN mkdir -p /app/storage/recordings /app/logs /app/data && \
    chown -R appuser:appuser /app

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    FLASK_APP=app.py

# Expose port
EXPOSE 3000

# Health check - increased start period for model loading
HEALTHCHECK --interval=30s --timeout=30s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:3000/api/health || exit 1

# Switch to non-root user
USER appuser

# Run with gunicorn for production (eventlet required for Flask-SocketIO)
CMD ["gunicorn", "--worker-class", "eventlet", "--workers", "1", "--bind", "0.0.0.0:3000", "--timeout", "300", "--keep-alive", "5", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
