# ComfyUI Base Image - RunPod Template

A ready-to-use Docker image for running ComfyUI on RunPod with all dependencies pre-installed.

## Quick Start

1. Deploy a new pod using this template
2. Wait for the pod to initialize 
3. Check the logs - when you see `Starting ComfyUI on 0.0.0.0:8188...`, ComfyUI is ready
4. Access the ComfyUI web interface using the port forwarding or connect button

## Access Points

- **Port 8188**: ComfyUI Web UI - Main interface for creating and running workflows
- **Port 7860**: CivitAI Model Downloader - Web interface to download models directly from CivitAI

## What's Included

This image comes pre-configured with:

- **ComfyUI** - Latest version with all core features
- **ComfyUI Manager** - Pre-installed for easy custom node management
- **PyTorch 2.7.1** - With CUDA 11.8 support for GPU acceleration
- **XFormers** - Memory optimization for better performance
- **Python 3.10** - With all required dependencies
- **CUDA 11.8 Runtime** - Optimized for NVIDIA GPUs
- **CivitAI Model Downloader** - Web interface to download models directly to the correct directories

## Configuration Options

You can customize ComfyUI behavior using environment variables:

- `PORT` - Change the port ComfyUI runs on (default: `8188`)
- `HOST` - Change the host IP address (default: `0.0.0.0`)
- `CIVITAI_PORT` - Change the port for CivitAI downloader (default: `7860`)
- `CIVITAI_HOST` - Change the host for CivitAI downloader (default: `0.0.0.0`)

Set these in RunPod's pod configuration under "Environment Variables".

## File Locations

Important directories inside the container:

```
/app/ComfyUI/
├── models/          # Place your models here
│   ├── checkpoints/  # Stable Diffusion checkpoints
│   ├── loras/        # LoRA models
│   ├── vae/          # VAE files
│   └── ...
├── output/           # Generated images are saved here
├── input/            # Place input files here
└── custom_nodes/     # Custom nodes installation directory
```

## Downloading Models from CivitAI

The template includes a built-in web interface to download models directly from CivitAI.

### How to Use

1. Access the CivitAI downloader at **Port 7860** (or the port you configured)
2. Enter your CivitAI API key (optional, but recommended for NSFW models and faster downloads)
   - Get your API key from [CivitAI Account Settings](https://civitai.com/user/account)
3. Enter the Model ID from the CivitAI URL
   - Example: For `https://civitai.com/models/12345/model-name`, use `12345`
   - You can paste the full URL - it will extract the ID automatically
4. (Optional) Enter a specific Version ID, or leave empty for the latest version
5. Click "Download Model"

The model will be automatically downloaded and placed in the correct ComfyUI directory:
- **Checkpoints** → `/app/ComfyUI/models/checkpoints/`
- **LoRA/LoCon** → `/app/ComfyUI/models/loras/`
- **VAE** → `/app/ComfyUI/models/vae/`
- **Controlnet** → `/app/ComfyUI/models/controlnet/`
- **Textual Inversion** → `/app/ComfyUI/models/embeddings/`
- And more...

Models are immediately available in ComfyUI after download - no restart needed!

### API Key Benefits

- Access to NSFW models (if your account has permissions)
- Faster download speeds
- Higher rate limits

## Managing Custom Nodes

### Using ComfyUI Manager (Recommended)

1. Open ComfyUI in your browser
2. Click the **Manager** button in the top menu
3. Navigate to **Install Custom Nodes**
4. Browse or search for nodes you want to install
5. Click install - no restart required for most nodes

### Manual Installation

If you need to install nodes manually, connect to the pod via terminal and run:

```bash
cd /app/ComfyUI/custom_nodes
git clone <repository-url>
cd <node-directory>
pip install -r requirements.txt  # If the node has dependencies
```

## Persistent Storage

To preserve your models, outputs, and custom nodes between pod restarts, map persistent volumes:

- **Models Volume**: `/app/ComfyUI/models` → Map to your persistent storage
- **Output Volume**: `/app/ComfyUI/output` → Map to your persistent storage
- **Input Volume**: `/app/ComfyUI/input` → Map to your persistent storage (optional)

## GPU Requirements

- **Minimum**: 8GB VRAM (RTX 3060, RTX 3070)
- **Recommended**: 16GB+ VRAM (RTX 3090, RTX 4090, A100)
- **For large models**: 24GB+ VRAM recommended

The image automatically detects and uses available NVIDIA GPUs.

## Tips

- First startup may take longer as dependencies are initialized
- Large models (4GB+) will take time to load into VRAM
- Use ComfyUI Manager to easily update ComfyUI and custom nodes
- Check pod logs if you encounter issues - they show detailed startup information
- GPU memory is displayed in the startup logs for verification

## Resources

- [ComfyUI Official Repository](https://github.com/comfyanonymous/ComfyUI)
- [ComfyUI Manager Documentation](https://github.com/ltdrdata/ComfyUI-Manager)
- [RunPod Documentation](https://docs.runpod.io/)

## Image Details

- **Registry**: GitHub Container Registry (GHCR)
- **Image**: `ghcr.io/quinteroac/comfyui-base-image:local`
- **Base**: NVIDIA CUDA 11.8 Runtime with Ubuntu 22.04
