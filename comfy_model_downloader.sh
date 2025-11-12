#!/bin/bash

# This script allows downloading models using comfy-cli from HuggingFace or CivitAI.
# Usage:
#   ./comfy_model_downloader.sh <source> <local_dir> <filename> <url>
#   source: hf or civitai
#   local_dir: subdir under models/
#   filename: file name to save as
#   url: download url

set -e

# Check for the appropriate number of arguments
if [ "$#" -lt 4 ]; then
    echo "Usage: $0 <source: hf|civitai> <local_dir> <filename> <url>"
    exit 1
fi

SOURCE="$1"
LOCAL_DIR="$2"
FILENAME="$3"
URL="$4"

if [ "$SOURCE" = "hf" ]; then
    # Download from HuggingFace using comfy-cli
    comfy --skip-prompt model download --url "$URL" \
        --relative-path "models/$LOCAL_DIR" \
        --filename "$FILENAME"
elif [ "$SOURCE" = "civitai" ]; then
    # Download from CivitAI using comfy-cli, requires CIVITAI_API_TOKEN env variable
    if [ -z "$CIVITAI_API_TOKEN" ]; then
        echo "Error: CIVITAI_API_TOKEN environment variable is not set."
        exit 1
    fi
    comfy --skip-prompt model download --url "$URL" \
        --relative-path "models/$LOCAL_DIR" \
        --filename "$FILENAME" \
        --set-civitai-api-token "$CIVITAI_API_TOKEN"
else
    echo "Unknown source: $SOURCE. Must be 'hf' or 'civitai'."
    exit 1
fi
