#!/bin/bash

# Entrypoint script for ComfyUI on RunPod

# Don't exit on error for background processes
set -e

# Change to ComfyUI directory
cd /app/ComfyUI

# Configurable environment variables
PORT=${PORT:-8188}
HOST=${HOST:-0.0.0.0}
CIVITAI_PORT=${CIVITAI_PORT:-7860}
CIVITAI_HOST=${CIVITAI_HOST:-0.0.0.0}

# Check if CUDA is available
if command -v nvidia-smi &> /dev/null; then
    echo "GPU detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "Warning: nvidia-smi not found. Running in CPU mode."
fi

# Verify Python is available
if ! command -v python &> /dev/null; then
    echo "Error: Python not found"
    exit 1
fi

# Start CivitAI downloader web interface in background
echo "Starting CivitAI Model Downloader on ${CIVITAI_HOST}:${CIVITAI_PORT}..."
cd /app
python civitai_web.py > /tmp/civitai.log 2>&1 &
CIVITAI_PID=$!

# Wait a moment for the web server to start
sleep 2

# Check if CivitAI web server started successfully
if ! kill -0 $CIVITAI_PID 2>/dev/null; then
    echo "Warning: CivitAI downloader failed to start. Check logs at /tmp/civitai.log"
else
    echo "✓ CivitAI downloader started (PID: $CIVITAI_PID)"
fi

# Start ComfyUI
echo "Starting ComfyUI on ${HOST}:${PORT}..."
echo "Working directory: /app/ComfyUI"
echo ""
echo "Access points:"
echo "  - ComfyUI: http://${HOST}:${PORT}"
echo "  - CivitAI Downloader: http://${CIVITAI_HOST}:${CIVITAI_PORT}"
echo ""

cd /app/ComfyUI

# Run ComfyUI in foreground
exec python main.py --listen ${HOST} --port ${PORT}

