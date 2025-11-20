# Lightweight Dockerfile for ComfyUI and Anime Generator (≤1GB image size)

FROM python:3.10-slim

# Avoid interactive prompts and reduce image size
ENV DEBIAN_FRONTEND=noninteractive

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip to the latest version
RUN python3 -m pip install --upgrade pip

# Install only Comfy-CLI and dependencies minimally (no dev/test extras)
RUN pip install --no-cache-dir comfy-cli

WORKDIR /app

# Copy only essential scripts
COPY comfy_model_downloader.sh /app/comfy_model_downloader.sh
RUN chmod +x /app/comfy_model_downloader.sh

# Omit app files in build to keep base image small.
# You will mount or COPY these in a later, separate image or at runtime:
# COPY app.py /app/app.py
# COPY config.py /app/config.py
# COPY auth.py /app/auth.py
# COPY domains /app/domains
# COPY routes /app/routes
# COPY utils /app/utils
# COPY templates /app/templates
# COPY static /app/static
# COPY data /app/data
# COPY workflows /app/workflows
# COPY defaults.json /app/defaults.json

# Copy entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Expose only necessary port
EXPOSE 8188

ENTRYPOINT ["/app/entrypoint.sh"]
