### IMPORTANT ALL THIS PROJECT WAS VIBE CODING

# Anime Generator - RunPod Template

A powerful web application for iterative anime image generation using ComfyUI. This application provides an intuitive interface for creating anime-style images through an interactive step-by-step process or direct prompt generation.

## 🎨 Features

### Interactive Generation Mode
- **Step-by-step prompt building**: Build your prompt through 10 categorized steps:
  1. Character
  2. Art-Style
  3. Character Appearance
  4. Clothing
  5. Expression & Action
  6. Camera / Positioning
  7. Lighting & Effects
  8. Scene Atmosphere
  9. Quality Tag
  10. Natural-language enrichment (optional)

- **Smart tag suggestions**: Access to 800,000+ curated tags organized by category
  - Tags are displayed dynamically based on the current step
  - Tags are sorted by popularity (post_count)
  - In-memory cache for fast tag retrieval
  - Prevents duplicate tag suggestions

- **AI-powered prompt enrichment**: Optional OpenAI integration to enhance prompts
- **Progressive generation**: Uses a unified 20-step inference by default across the interactive flow
- **Seed management**: Consistent seed across all steps in interactive mode

### Direct Generation Mode
- **Quick generation**: Direct prompt input for immediate image generation
- **Random seed**: Each generation uses a new random seed
- **Full quality**: Default inference runs at 20 steps

### Additional Features
- **Multiple aspect ratios**: Square (1024x1024), Portrait (823x1216), Landscape (1216x823)
- **Real-time status updates**: WebSocket integration for live generation progress
- **Image gallery**: View and manage generated images
- **Full-size image viewer**: Click to view images in full resolution
- **Responsive design**: Modern, dark-themed UI with smooth animations

## 🚀 Deployment on RunPod

### Quick Start

1. **Create a RunPod Pod**
   - Go to [RunPod.io](https://www.runpod.io)
   - Select "GPU Pods" → "Deploy"
   - Choose your preferred GPU (RTX 4090/5090 recommended)
   - Select "Community Cloud" or "Secure Cloud"

2. **Deploy Using Docker Image**
   - **Container Image**: `ghcr.io/quinteroac/my-anime-genearator:latest`
   - **Container Disk**: Minimum 20GB (recommended: 50GB+)
   - **Volume**: Optional, for persistent model storage

3. **Configure Environment Variables**
   ```bash
   COMFYUI_URL=http://localhost:8188
   OPENAI_API_KEY=your_openai_api_key_here  # Optional, for AI enrichment
   CIVITAI_API_KEY=your_civitai_api_key_here  # Optional, for CivitAI downloads
   ```

4. **Expose Ports**
   - **Port 5000**: Anime Generator Web Interface
   - **Port 8188**: ComfyUI (if running locally)
   - **Port 7860**: CivitAI Model Downloader

5. **Access the Application**
   - Wait for the container to start (check logs)
   - Open the Anime Generator at: `https://your-pod-id-5000.proxy.runpod.net`
   - Or use your RunPod endpoint URL

### Using External ComfyUI Backend

If you have ComfyUI running separately (e.g., on another RunPod pod):

1. **Set the ComfyUI URL**:
   ```bash
   COMFYUI_URL=https://your-comfyui-pod-id-8188.proxy.runpod.net
   ```

2. **Start the Anime Generator**:
   ```bash
   ANIME_GENERATOR_PORT=5000
   ANIME_GENERATOR_HOST=0.0.0.0
   ```

The application will automatically connect to the external ComfyUI instance.

## 📋 Environment Variables

### Required
- `COMFYUI_URL`: URL of the ComfyUI instance
  - Local: `http://localhost:8188` or `http://127.0.0.1:8188`
  - Remote: `https://your-comfyui-pod-id-8188.proxy.runpod.net`

### Optional
- `OPENAI_API_KEY`: OpenAI API key for prompt enrichment feature
  - Get your key at: https://platform.openai.com/api-keys
  - Required only if using AI enrichment

- `CIVITAI_API_KEY`: CivitAI API key for model downloads
  - Get your key at: https://civitai.com/user/account
  - Provides access to NSFW models and faster downloads

- `ANIME_GENERATOR_PORT`: Port for the Anime Generator web interface (default: 5000)
- `ANIME_GENERATOR_HOST`: Host for the Anime Generator (default: 0.0.0.0)

- `COMFYUI_HOST`: ComfyUI host if using separate host/port config (default: 127.0.0.1)
- `COMFYUI_PORT`: ComfyUI port if using separate host/port config (default: 8188)

- `NETAYUME_MODEL_ID`: Model ID for automatic NetaYume Lumina download (default: 1790792)
- `LORA_DETAILER_ID`: LoRA ID for automatic detailer download (default: 1974130)

## 🎯 Usage

### Interactive Mode

1. **Start a new prompt** by clicking the "+" button or toggling to interactive mode
2. **Follow the steps**:
   - Enter your description for each category
   - Use suggested tags by clicking on them (they'll be added to your prompt)
   - Click "Renew Tags" to load more tag suggestions
   - Press Enter or click the Generate button to proceed
3. **Generate images**:
   - Intermediate and final steps use the configured inference count (20 by default)
   - Seed remains constant throughout the flow

### Direct Mode

1. **Toggle to Direct Mode** using the mode selector
2. **Enter your complete prompt** in the textarea
3. **Select aspect ratio** (Square, Portrait, Landscape)
4. **Generate** - images default to 20 steps with a random seed

### AI Enrichment

Enable the AI enrichment toggle to automatically enhance your prompts using OpenAI's GPT models. This feature:
- Improves prompt clarity and detail
- Adds relevant tags and descriptions
- Works in both interactive and direct modes

## 📁 Project Structure

```
.
├── anime_generator.py      # Main Flask application
├── entrypoint.sh           # Container startup script
├── Dockerfile              # Docker image definition
├── requirements.txt        # Python dependencies
├── civitai_downloader.py   # CivitAI model downloader
├── civitai_web.py          # CivitAI web interface
├── templates/
│   └── index.html          # Frontend HTML template
├── static/
│   ├── css/
│   │   └── style.css       # Application styles
│   └── js/
│       └── main.js         # Vue.js frontend logic
├── data/
│   └── tags.csv            # Tag database (800,000+ tags)
└── workflows/
    └── text-to-image/
        └── text-to-image-illustrious.json  # ComfyUI workflow
```

## 🔧 Technical Details

### Backend
- **Framework**: Flask (Python 3.10)
- **Image Generation**: ComfyUI integration via API
- **Tag System**: In-memory cache for fast tag retrieval
- **Image Serving**: Proxies images from ComfyUI `/view` endpoint

### Frontend
- **Framework**: Vue.js 3
- **Styling**: Custom CSS with dark theme
- **Icons**: Heroicons (inline SVG)
- **Real-time Updates**: WebSocket for generation status

### Dependencies
- PyTorch with CUDA 12.1 support (optimized for RTX 4090/5090)
- ComfyUI with ComfyUI Manager
- Flask and Flask-CORS
- WebSocket client for ComfyUI communication
- OpenAI API client (optional)

## 🐳 Docker Image

The application is available as a Docker image on GitHub Container Registry:

```bash
ghcr.io/quinteroac/my-anime-genearator:latest
```

### Building Locally

```bash
docker build -t my-anime-generator .
docker run -p 5000:5000 \
  -e COMFYUI_URL=http://localhost:8188 \
  -e OPENAI_API_KEY=your_key \
  my-anime-generator
```

## 📊 Performance

- **Tag Loading**: Tags are cached in memory on startup (~2-3 seconds)
- **Tag Retrieval**: O(1) lookup after cache initialization
- **Image Generation**: Depends on ComfyUI and GPU (typically 10-30 seconds per image)
- **Memory Usage**: ~2-3GB for tag cache, additional memory for ComfyUI

## 🔍 Troubleshooting

### Images Not Showing

If images are not displaying:
- Verify `COMFYUI_URL` is correctly set
- Check that ComfyUI is accessible from the Anime Generator
- Ensure the ComfyUI instance is running and healthy
- Check container logs: `docker logs <container_id>`

### Tags Not Loading

If tags are not appearing:
- Check that `data/tags.csv` exists in the container
- Verify the file is readable (check permissions)
- Check application logs for tag loading errors

### Connection Issues

If you see connection errors:
- Verify network connectivity between services
- Check firewall settings on RunPod
- Ensure ports are correctly exposed
- Verify proxy URLs are correct

## 📝 Notes

- The application automatically downloads the NetaYume Lumina model and detailer LoRA on first startup
- Models are stored in `/app/ComfyUI/models/`
- Generated images are saved in ComfyUI's output directory
- Tag database contains 800,000+ tags from Danbooru, properly categorized
- The application supports both local and remote ComfyUI instances

## 🔗 Additional Resources

- [ComfyUI Documentation](https://github.com/comfyanonymous/ComfyUI)
- [RunPod Documentation](https://docs.runpod.io/)
- [CivitAI](https://civitai.com/)
- [OpenAI API Documentation](https://platform.openai.com/docs)

## 📄 License

This project uses ComfyUI and other open-source components. Please refer to their respective licenses.

---

**For support or issues, please check the application logs or create an issue in the repository.**
