# ComfyUI Container for RunPod

This project contains the necessary files to create a Docker container that runs ComfyUI, compatible with RunPod.

## Description

ComfyUI is a powerful and modular user interface for Stable Diffusion. This container is configured to run on RunPod with all necessary dependencies.

## Project Structure

- `Dockerfile`: Defines the Docker image with ComfyUI and all its dependencies
- `entrypoint.sh`: Script that starts ComfyUI and the CivitAI downloader
- `requirements.txt`: Required Python dependencies
- `civitai_downloader.py`: Core logic for downloading models from CivitAI
- `civitai_web.py`: Flask web interface for the CivitAI model downloader
- `RUNPOD_TEMPLATE_README.md`: Documentation for deploying the template on RunPod
- `.dockerignore`: Files to exclude from Docker build
- `.github/workflows/`: GitHub Actions workflows for automatic Docker builds
- `push-to-github.ps1`: PowerShell script to push changes to GitHub (Windows)
- `push-to-github.sh`: Bash script to push changes to GitHub (Linux/Mac/WSL)

## Building the Image

To build the Docker image locally:

```bash
docker build -t comfyui-runpod .
```

### Optimizing Build Time (Cache)

The Dockerfile has been optimized for fast rebuilds using Docker's layer caching:

**Key optimizations:**
1. **Layer ordering**: Dependencies are installed in separate layers to maximize cache hits
2. **Pip cache enabled**: Removed `--no-cache-dir` to allow pip to cache downloaded packages between builds
3. **Late cleanup**: Cleanup operations run at the end to avoid breaking cache for earlier layers
4. **Requirements first**: `requirements.txt` is copied early to enable caching of pip installations

**First build**: Takes ~15-30 minutes (downloads PyTorch, ComfyUI, dependencies)  
**Subsequent builds**: Typically takes 2-5 minutes if only code changes

**To force rebuild without cache:**
```bash
docker build --no-cache -t comfyui-runpod .
```

**To use build cache when building:**
```bash
# Standard build (uses cache automatically)
docker build -t comfyui-runpod .

# Using Docker BuildKit for better caching
DOCKER_BUILDKIT=1 docker build -t comfyui-runpod .
```

## Local Execution

To run the container locally:

```bash
docker run -p 8188:8188 -p 7860:7860 comfyui-runpod
```

Then you can access:
- **ComfyUI** at `http://localhost:8188`
- **CivitAI Model Downloader** at `http://localhost:7860`

## CivitAI Model Downloader

The container includes a built-in web interface for downloading models directly from CivitAI to the correct ComfyUI directories.

### Accessing the Downloader

The CivitAI Model Downloader is available at port `7860` by default:

```bash
docker run -p 8188:8188 -p 7860:7860 comfyui-runpod
```

Access the downloader at: `http://localhost:7860`

### Features

- 🎨 **Web Interface**: Simple, user-friendly web interface for downloading models
- 📦 **Automatic Placement**: Models are automatically placed in the correct ComfyUI directory based on type (Checkpoint, LoRA, VAE, Controlnet, etc.)
- 📊 **Real-time Progress**: Live progress bar showing download percentage and MB downloaded
- 🔑 **API Key Support**: Optional CivitAI API key for NSFW models and faster downloads
- 🔍 **URL/ID Support**: Enter model ID or full CivitAI URL

### Usage

1. **Open the web interface** at `http://localhost:7860`
2. **Enter your CivitAI API key** (optional, but recommended for NSFW models and higher speeds)
   - Get your API key from: https://civitai.com/user/account
3. **Enter the Model ID or URL**:
   - Option 1: Paste the full CivitAI URL (e.g., `https://civitai.com/models/12345/example-model`)
   - Option 2: Enter just the model ID (e.g., `12345`)
4. **Optionally specify a Version ID** (leave empty for latest version)
5. **Click "Download Model"** and watch the progress bar update in real-time

### Example

```
Model URL: https://civitai.com/models/12345/example-model
Model ID: 12345
```

The model will be automatically downloaded to the appropriate directory:
- **Checkpoints** → `/app/ComfyUI/models/checkpoints/`
- **LoRA** → `/app/ComfyUI/models/loras/`
- **VAE** → `/app/ComfyUI/models/vae/`
- **Controlnet** → `/app/ComfyUI/models/controlnet/`
- And so on...

### Configuration

You can customize the CivitAI downloader port and host using environment variables:

- `CIVITAI_PORT`: Port for the CivitAI downloader (default: 7860)
- `CIVITAI_HOST`: Host for the CivitAI downloader (default: 0.0.0.0)

Example:
```bash
docker run -p 8188:8188 -p 9000:9000 \
  -e CIVITAI_PORT=9000 \
  -e CIVITAI_HOST=0.0.0.0 \
  comfyui-runpod
```

### Benefits of Using an API Key

- ✅ Access to NSFW models
- ✅ Higher download speeds
- ✅ Better rate limits
- ✅ Access to private models (if you have permission)

### Notes

- The downloader runs automatically when the container starts
- Downloads are streamed directly to the appropriate ComfyUI model directory
- If a model already exists, the downloader will notify you
- Progress is tracked in real-time with detailed MB information

## Automated Builds with GitHub Actions

This repository includes a GitHub Actions workflow for automatic Docker image builds to GitHub Container Registry (GHCR).

### Self-Hosted Runner Setup

The workflow is configured to use a **self-hosted runner** to avoid disk space limitations of GitHub-hosted runners.

#### Prerequisites

Before setting up the runner, you need to install:

1. **Docker Desktop** (required)
   - Download from: https://www.docker.com/products/docker-desktop
   - Make sure WSL 2 is enabled (Docker Desktop will prompt you during installation)
   - Verify installation: `docker --version`

2. **Git** (required)
   - Download from: https://git-scm.com/download/win
   - Usually already installed on Windows
   - Verify installation: `git --version`

3. **PowerShell 5.1+** (required)
   - Comes pre-installed on Windows 10/11
   - Or install PowerShell 7+ from: https://aka.ms/powershell-release
   - Verify installation: `$PSVersionTable.PSVersion`

4. **Disk Space** (recommended)
   - At least 50GB free space for Docker images and build cache
   - PyTorch and dependencies are large (~2-3GB)

5. **GitHub Personal Access Token** (required for setup)
   - Go to: https://github.com/settings/tokens/new
   - Select `repo` scope (Full control of private repositories)
   - Click "Generate token"

The setup script (`setup-local-runner.ps1`) will automatically check for Docker and Git.

**To set up the local runner:**

1. **Run the setup script:**
   ```powershell
   .\setup-local-runner.ps1
   ```
   
   The script will:
   - Check for Docker installation
   - Download the latest GitHub Actions runner
   - Configure it for this repository

2. **Start the runner:**
   ```powershell
   cd _runner
   .\run.cmd
   ```

3. **Trigger a workflow:**
   - Push to `main` branch, or
   - Go to Actions → "Build Docker Image" → "Run workflow"

The runner will execute builds on your local machine using your Docker installation.

## Configuration

### Environment Variables

**ComfyUI:**
- `PORT`: Port on which ComfyUI will run (default: 8188)
- `HOST`: Host on which ComfyUI will run (default: 0.0.0.0)

**CivitAI Downloader:**
- `CIVITAI_PORT`: Port for the CivitAI downloader web interface (default: 7860)
- `CIVITAI_HOST`: Host for the CivitAI downloader (default: 0.0.0.0)

Example:
```bash
docker run -p 8188:8188 -p 7860:7860 \
  -e PORT=8188 \
  -e HOST=0.0.0.0 \
  -e CIVITAI_PORT=7860 \
  -e CIVITAI_HOST=0.0.0.0 \
  comfyui-runpod
```

## Features

- ✅ Python 3.10
- ✅ PyTorch with CUDA 11.8 support
- ✅ ComfyUI with all its dependencies
- ✅ ComfyUI Manager pre-installed for easy plugin management
- ✅ **CivitAI Model Downloader** - Web interface for downloading models directly from CivitAI
- ✅ Compatible with RunPod GPU (NVIDIA)
- ✅ XFormers for memory optimization
- ✅ Production-ready configuration
- ✅ Entrypoint script with GPU verification

## Notes

- Models can be loaded in `/app/ComfyUI/models`
- Outputs are saved in `/app/ComfyUI/output`
- Inputs are read from `/app/ComfyUI/input`
- Custom nodes and plugins can be installed via ComfyUI Manager (accessible through the ComfyUI web interface)

## Additional Resources

- [ComfyUI Documentation](https://github.com/comfyanonymous/ComfyUI)
- [RunPod Documentation](https://docs.runpod.io/)
