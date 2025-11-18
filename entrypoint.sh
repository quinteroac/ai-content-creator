#!/bin/bash

# Entrypoint script for ComfyUI on RunPod

# Don't exit on error for background processes
set -e

# Change to ComfyUI directory
cd /root/comfy/ComfyUI

# Configurable environment variables
PORT=${PORT:-8188}
HOST=${HOST:-0.0.0.0}
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

# Resolve Python interpreter
if command -v python3 &> /dev/null; then
    PYTHON_BIN="$(command -v python3)"
elif command -v python &> /dev/null; then
    PYTHON_BIN="$(command -v python)"
else
    echo "Error: Python not found"
    exit 1
fi
echo "Using Python interpreter: ${PYTHON_BIN}"

# Helper function to download a model from HuggingFace
hf_dl() {
    local local_dir="$1"
    local filename="$2"
    local url="$3"
    bash /root/comfy_model_downloader.sh hf "$local_dir" "$filename" "$url"
}

# Helper function to download a model from CivitAI
civitai_dl() {
    local local_dir="$1"
    local filename="$2"
    local url="$3"
    bash /root/comfy_model_downloader.sh civitai "$local_dir" "$filename" "$url"
}

# Download necessary models on container start. Each block invokes the corresponding download function.
# All downloaded files will be placed under /app/ComfyUI/models/<category>/

civitai_dl "checkpoints" \
    "plantMilkModelSuite_walnut.safetensors" \
    "https://civitai.com/api/download/models/1714002?type=Model&format=SafeTensor&size=pruned&fp=fp16"

hf_dl "vae" \
    "qwen_image_vae.safetensors" \
    "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors"

hf_dl "text_encoders" \
    "qwen_2.5_vl_7b_fp8_scaled.safetensors" \
    "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"

hf_dl "diffusion_models" \
    "qwen_image_edit_2509_fp8_e4m3fn.safetensors" \
    "https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_2509_fp8_e4m3fn.safetensors"

hf_dl "loras" \
    "Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors" \
    "https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Edit-2509/Qwen-Image-Edit-2509-Lightning-4steps-V1.0-bf16.safetensors"

civitai_dl "loras" \
    "qwen-edit-skin_1.1_000002750.safetensors" \
    "https://civitai.com/api/download/models/2376235?type=Model&format=SafeTensor"

civitai_dl "loras" \
    "aldniki_qwen_reality_transform_v01.safetensors" \
    "https://civitai.com/api/download/models/2157828?type=Model&format=SafeTensor"

civitai_dl "loras" \
    "lenovo.safetensors" \
    "https://civitai.com/api/download/models/2106185?type=Model&format=SafeTensor"

hf_dl "vae" \
    "wan_2.1_vae.safetensors" \
    "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors"

hf_dl "clip" \
    "nsfw_wan_umt5-xxl_fp8_scaled.safetensors" \
    "https://huggingface.co/NSFW-API/NSFW-Wan-UMT5-XXL/resolve/main/nsfw_wan_umt5-xxl_fp8_scaled.safetensors"

hf_dl "loras" \
    "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors" \
    "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors"

hf_dl "loras" \
    "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors" \
    "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors"

civitai_dl "diffusion_models" \
    "wan22RemixT2VI2V_i2vHighV20.safetensors" \
    "https://civitai.com/api/download/models/2381931?type=Model&format=SafeTensor&size=pruned&fp=fp8"

civitai_dl "diffusion_models" \
    "wan22RemixT2VI2V_i2vLowV20.safetensors" \
    "https://civitai.com/api/download/models/2382303?type=Model&format=SafeTensor&size=pruned&fp=fp8"



# Start Anime Generator web interface in background
echo "Starting Anime Generator on ${ANIME_GENERATOR_HOST}:${ANIME_GENERATOR_PORT}..."
cd /app
COMFYUI_HOST=${COMFYUI_HOST} COMFYUI_PORT=${COMFYUI_PORT} "$PYTHON_BIN" app.py > /tmp/anime_generator.log 2>&1 &
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
echo "  - Anime Generator: http://${ANIME_GENERATOR_HOST}:${ANIME_GENERATOR_PORT}"
echo ""

# Run ComfyUI in foreground
exec comfy launch -- --listen 0.0.0.0 --port ${COMFYUI_PORT}