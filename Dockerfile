FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# Avoid interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.10 and system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-dev \
    python3-pip \
    git \
    wget \
    curl \
    build-essential \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1 && \
    update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# Create working directory
WORKDIR /app

# Copy requirements and install base dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cu118 -r requirements.txt && \
    pip cache purge && \
    rm -rf /tmp/* /var/tmp/* ~/.cache

# Clone ComfyUI, install dependencies, and cleanup
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI && \
    cd /app/ComfyUI && \
    pip install --no-cache-dir -r requirements.txt && \
    pip cache purge && \
    rm -rf /tmp/* /var/tmp/* ~/.cache && \
    mkdir -p custom_nodes && \
    git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Manager.git custom_nodes/ComfyUI-Manager && \
    cd custom_nodes/ComfyUI-Manager && \
    pip install --no-cache-dir -r requirements.txt && \
    pip cache purge && \
    rm -rf /tmp/* /var/tmp/* ~/.cache && \
    cd /app && \
    rm -rf /app/ComfyUI/.git /app/ComfyUI/custom_nodes/ComfyUI-Manager/.git && \
    mkdir -p /app/ComfyUI/models /app/ComfyUI/output /app/ComfyUI/input

# Copy entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Expose port (ComfyUI uses 8188 by default)
EXPOSE 8188

# Set entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]

