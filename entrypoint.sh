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
ANIME_GENERATOR_PORT=${ANIME_GENERATOR_PORT:-5000}
ANIME_GENERATOR_HOST=${ANIME_GENERATOR_HOST:-0.0.0.0}
COMFYUI_HOST=${COMFYUI_HOST:-127.0.0.1}
COMFYUI_PORT=${COMFYUI_PORT:-8188}
ENABLE_EDIT=${ENABLE_EDIT:-true}
ENABLE_VIDEO=${ENABLE_VIDEO:-true}
ILLUSTRIOUS_CHKP=${ILLUSTRIOUS_CHKP:-1162518}

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

# Helper functions
download_with_wget() {
    local url="$1"
    local destination="$2"
    local name="$3"

    if [ -f "$destination" ]; then
        echo "✓ $name already exists at $destination"
        return 0
    fi

    mkdir -p "$(dirname "$destination")"
    echo "Downloading $name..."
    if wget -O "$destination" "$url"; then
        echo "✓ Downloaded $name"
    else
        echo "✗ Failed to download $name from $url"
        rm -f "$destination"
        return 1
    fi
}

download_from_civitai() {
    local model_id="$1"
    local version_id="$2"
    local name="$3"
    local override="$4"
    local api_key_arg="${CIVITAI_API_KEY:-}"

    echo "Ensuring $name (CivitAI ID: $model_id${version_id:+, Version: $version_id})..."
    if CIVITAI_DIR_OVERRIDE_CHECKPOINT="${override:-}" python /app/civitai_downloader.py "$model_id" "$version_id" "$api_key_arg"; then
        echo "✓ $name ready"
    else
        echo "✗ Failed to download $name (ID: $model_id${version_id:+, Version: $version_id})"
    fi
}

MODELS_ROOT="/app/ComfyUI/models"

echo "=== Preparing Illustrious checkpoint ==="
download_from_civitai "$ILLUSTRIOUS_CHKP" "" "Illustrious checkpoint"

if [[ "${ENABLE_EDIT,,}" == "true" ]]; then
    echo "=== Preparing Qwen Edit assets ==="
    download_with_wget \
        "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors" \
        "${MODELS_ROOT}/vae/qwen_image_vae.safetensors" \
        "Qwen VAE"

    download_with_wget \
        "https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors" \
        "${MODELS_ROOT}/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors" \
        "Qwen diffusion model"

    download_with_wget \
        "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
        "${MODELS_ROOT}/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" \
        "Qwen text encoder"

    download_with_wget \
        "https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Edit-2509/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors" \
        "${MODELS_ROOT}/loras/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors" \
        "Qwen Lightning LoRA"

    download_from_civitai "2097058" "" "Qwen LoRA (2097058)"
    download_from_civitai "1906441" "" "Qwen LoRA (1906441)"
    download_from_civitai "1662740" "" "Qwen LoRA (1662740)"
else
    echo "ENABLE_EDIT set to false. Skipping Qwen Edit downloads."
fi

if [[ "${ENABLE_VIDEO,,}" == "true" ]]; then
    echo "=== Preparing WAN assets ==="
    download_with_wget \
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors" \
        "${MODELS_ROOT}/vae/wan_2.1_vae.safetensors" \
        "WAN VAE"

    download_with_wget \
        "https://huggingface.co/NSFW-API/NSFW-Wan-UMT5-XXL/resolve/main/nsfw_wan_umt5-xxl_fp8_scaled.safetensors" \
        "${MODELS_ROOT}/clip/nsfw_wan_umt5-xxl_fp8_scaled.safetensors" \
        "WAN CLIP"

    download_with_wget \
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors" \
        "${MODELS_ROOT}/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors" \
        "WAN High Noise LoRA"

    download_with_wget \
        "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors" \
        "${MODELS_ROOT}/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors" \
        "WAN Low Noise LoRA"

    download_from_civitai "2342708" "2342708" "WAN diffusion model (high)" "diffusion_models"
    download_from_civitai "2342708" "2342740" "WAN diffusion model (low)" "diffusion_models"
else
    echo "ENABLE_VIDEO set to false. Skipping WAN downloads."
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

# Start Anime Generator web interface in background
echo "Starting Anime Generator on ${ANIME_GENERATOR_HOST}:${ANIME_GENERATOR_PORT}..."
cd /app
COMFYUI_HOST=${COMFYUI_HOST} COMFYUI_PORT=${COMFYUI_PORT} python anime_generator.py > /tmp/anime_generator.log 2>&1 &
ANIME_GENERATOR_PID=$!

# Wait a moment for the web server to start
sleep 2

# Check if Anime Generator web server started successfully
if ! kill -0 $ANIME_GENERATOR_PID 2>/dev/null; then
    echo "Warning: Anime Generator failed to start. Check logs at /tmp/anime_generator.log"
else
    echo "✓ Anime Generator started (PID: $ANIME_GENERATOR_PID)"
fi

# Start ComfyUI
echo "Starting ComfyUI on ${HOST}:${PORT}..."
echo "Working directory: /app/ComfyUI"
echo ""
echo "Access points:"
echo "  - ComfyUI: http://${HOST}:${PORT}"
echo "  - CivitAI Downloader: http://${CIVITAI_HOST}:${CIVITAI_PORT}"
echo "  - Anime Generator: http://${ANIME_GENERATOR_HOST}:${ANIME_GENERATOR_PORT}"
echo ""

cd /app/ComfyUI

# Run ComfyUI in foreground
exec python main.py --listen ${HOST} --port ${PORT}

