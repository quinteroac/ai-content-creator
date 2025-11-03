#!/usr/bin/env python3
"""
CivitAI Model Downloader
Downloads models from CivitAI and places them in the correct ComfyUI directory
"""

import os
import sys
import requests
import json
from pathlib import Path
from typing import Optional, Dict, List
import mimetypes

# ComfyUI model directories
MODEL_DIRS = {
    'Checkpoint': 'checkpoints',
    'TextualInversion': 'embeddings',
    'Hypernetwork': 'hypernetworks',
    'LORA': 'loras',
    'LoCon': 'loras',
    'VAE': 'vae',
    'Controlnet': 'controlnet',
    'Poses': 'controlnet',
    'Upscaler': 'upscale_models',
    'MotionModule': 'motion_modules',
}

BASE_URL = "https://civitai.com/api/v1"
MODELS_DIR = Path("/app/ComfyUI/models")


class CivitAIDownloader:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.headers = {
            "User-Agent": "ComfyUI-CivitAI-Downloader/1.0"
        }
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        
        # Ensure model directories exist
        for dir_name in MODEL_DIRS.values():
            (MODELS_DIR / dir_name).mkdir(parents=True, exist_ok=True)
    
    def get_model_info(self, model_id: str) -> Optional[Dict]:
        """Get model information from CivitAI"""
        try:
            url = f"{BASE_URL}/models/{model_id}"
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching model info: {e}")
            return None
    
    def get_version_info(self, model_id: str, version_id: Optional[str] = None) -> Optional[Dict]:
        """Get specific version information"""
        model_info = self.get_model_info(model_id)
        if not model_info:
            return None
        
        if version_id:
            # Find specific version
            for version in model_info.get('modelVersions', []):
                if str(version['id']) == str(version_id):
                    return version
        else:
            # Return latest version
            versions = model_info.get('modelVersions', [])
            if versions:
                return versions[0]
        
        return None
    
    def determine_model_type(self, model_info: Dict) -> str:
        """Determine model type from CivitAI model info"""
        model_type = model_info.get('type', '')
        return MODEL_DIRS.get(model_type, 'checkpoints')
    
    def download_file(self, url: str, destination: Path, model_name: str, progress_callback=None) -> bool:
        """Download a file from URL to destination"""
        try:
            print(f"Downloading {model_name}...")
            print(f"URL: {url}")
            print(f"Destination: {destination}")
            
            response = requests.get(url, headers=self.headers, stream=True, timeout=300)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            last_percent = -1
            
            with open(destination, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            # Only update if percent changed significantly (to reduce callback frequency)
                            if abs(percent - last_percent) >= 0.1 or downloaded == total_size:
                                sys.stdout.write(f"\rProgress: {percent:.1f}% ({downloaded}/{total_size} bytes)")
                                sys.stdout.flush()
                                last_percent = percent
                                
                                # Call progress callback if provided
                                if progress_callback:
                                    try:
                                        progress_callback(percent, downloaded, total_size)
                                    except Exception as e:
                                        print(f"\nWarning: Progress callback error: {e}")
                        else:
                            # No content-length, just report downloaded bytes
                            if progress_callback and downloaded % (1024 * 1024) == 0:  # Every MB
                                try:
                                    progress_callback(0, downloaded, 0)  # 0% when we don't know total
                                except Exception as e:
                                    print(f"\nWarning: Progress callback error: {e}")
            
            print(f"\n✓ Successfully downloaded: {model_name}")
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"\n✗ Error downloading {model_name}: {e}")
            if destination.exists():
                destination.unlink()  # Remove partial file
            return False
    
    def download_model(self, model_id: str, version_id: Optional[str] = None, progress_callback=None) -> Dict:
        """Download a model from CivitAI"""
        result = {
            'success': False,
            'message': '',
            'path': None
        }
        
        # Get model info
        model_info = self.get_model_info(model_id)
        if not model_info:
            result['message'] = f"Failed to fetch model info for ID: {model_id}"
            return result
        
        model_name = model_info.get('name', 'unknown')
        print(f"Model: {model_name}")
        
        # Get version info
        version_info = self.get_version_info(model_id, version_id)
        if not version_info:
            result['message'] = f"Failed to fetch version info for model {model_id}"
            return result
        
        version_name = version_info.get('name', 'latest')
        print(f"Version: {version_name}")
        
        # Determine model type and directory
        model_type_dir = self.determine_model_type(model_info)
        target_dir = MODELS_DIR / model_type_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Get download URL - try primary file first
        files = version_info.get('files', [])
        if not files:
            result['message'] = "No files found for this version"
            return result
        
        # Find primary file or first file
        primary_file = None
        for file in files:
            if file.get('primary'):
                primary_file = file
                break
        
        if not primary_file:
            primary_file = files[0]
        
        download_url = primary_file.get('downloadUrl')
        if not download_url:
            result['message'] = "No download URL available. This might be a NSFW model requiring authentication."
            return result
        
        filename = primary_file.get('name', f"{model_id}_{version_info.get('id', 'latest')}.safetensors")
        # Clean filename
        filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip()
        
        destination = target_dir / filename
        
        # Check if file already exists
        if destination.exists():
            file_size = destination.stat().st_size
            # Update progress to 100% if callback provided
            if progress_callback:
                try:
                    progress_callback(100, file_size, file_size)
                except Exception as e:
                    print(f"Warning: Progress callback error: {e}")
            result['success'] = True
            result['message'] = f"Model already exists: {destination}"
            result['path'] = str(destination)
            return result
        
        # Download the file
        if self.download_file(download_url, destination, filename, progress_callback):
            result['success'] = True
            result['message'] = f"Successfully downloaded to: {destination}"
            result['path'] = str(destination)
            result['model_type'] = model_type_dir
        else:
            result['message'] = "Download failed"
        
        return result
    
    def search_models(self, query: str, limit: int = 10) -> List[Dict]:
        """Search for models on CivitAI"""
        try:
            url = f"{BASE_URL}/models"
            params = {
                'query': query,
                'limit': limit,
                'types': 'Checkpoint,LORA,LoCon,VAE,Controlnet,TextualInversion'
            }
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get('items', [])
        except requests.exceptions.RequestException as e:
            print(f"Error searching models: {e}")
            return []


if __name__ == "__main__":
    # CLI usage
    if len(sys.argv) < 2:
        print("Usage: civitai_downloader.py <model_id> [version_id] [api_key]")
        sys.exit(1)
    
    model_id = sys.argv[1]
    version_id = sys.argv[2] if len(sys.argv) > 2 else None
    api_key = sys.argv[3] if len(sys.argv) > 3 else None
    
    downloader = CivitAIDownloader(api_key)
    result = downloader.download_model(model_id, version_id)
    
    if result['success']:
        print(f"\n✓ Success: {result['message']}")
        sys.exit(0)
    else:
        print(f"\n✗ Error: {result['message']}")
        sys.exit(1)

