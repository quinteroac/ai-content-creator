FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# Avoid interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.10 and system dependencies
# This layer rarely changes, so it will be cached
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

# Upgrade pip for better timeout handling
RUN pip install --upgrade pip

# Create working directory and copy requirements early
# This allows pip cache to work effectively
WORKDIR /app
COPY requirements.txt .

# Install PyTorch first (large packages) - using official PyTorch index
RUN pip install --no-cache-dir --default-timeout=600 \
    --index-url https://download.pytorch.org/whl/cu118 \
    torch torchvision torchaudio

# Install other dependencies
RUN pip install --no-cache-dir --default-timeout=300 \
    numpy>=1.24.0 pillow>=9.5.0 opencv-python>=4.7.0 requests>=2.28.0 flask>=2.3.0

# Install xformers separately with longer timeout (it's a large package)
RUN pip install --no-cache-dir --default-timeout=600 \
    --index-url https://download.pytorch.org/whl/cu118 \
    xformers

# Clone ComfyUI, install dependencies
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI && \
    cd /app/ComfyUI && \
    pip install --no-cache-dir --default-timeout=300 -r requirements.txt && \
    mkdir -p custom_nodes && \
    git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Manager.git custom_nodes/ComfyUI-Manager && \
    cd custom_nodes/ComfyUI-Manager && \
    pip install --no-cache-dir --default-timeout=300 -r requirements.txt && \
    cd /app && \
    mkdir -p /app/ComfyUI/models /app/ComfyUI/output /app/ComfyUI/input

# Cleanup to reduce final image size (run last to not break cache)
RUN rm -rf /tmp/* /var/tmp/* ~/.cache \
    /app/ComfyUI/.git \
    /app/ComfyUI/custom_nodes/ComfyUI-Manager/.git

# Copy CivitAI downloader scripts
COPY civitai_downloader.py /app/civitai_downloader.py
COPY civitai_web.py /app/civitai_web.py
RUN chmod +x /app/civitai_downloader.py /app/civitai_web.py

# Copy entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Expose ports (ComfyUI: 8188, CivitAI Downloader: 7860)
EXPOSE 8188 7860

# Set entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]

