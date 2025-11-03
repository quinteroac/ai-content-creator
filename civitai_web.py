#!/usr/bin/env python3
"""
CivitAI Model Downloader Web Interface
Simple Flask web app to download models from CivitAI
"""

import os
import sys
from flask import Flask, render_template_string, request, jsonify, redirect, url_for
from civitai_downloader import CivitAIDownloader
import threading

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)

# Store downloader instance and progress
downloader = None
download_progress = {
    'percent': 0,
    'downloaded': 0,
    'total': 0,
    'active': False,
    'model_name': ''
}

# HTML template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>CivitAI Model Downloader</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            padding: 30px;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 500;
            font-size: 14px;
        }
        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 6px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        input[type="text"]:focus, input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
        }
        .help-text {
            font-size: 12px;
            color: #888;
            margin-top: 5px;
        }
        button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: 6px;
            font-size: 16px;
            font-weight: 500;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            width: 100%;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        .message {
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
            font-size: 14px;
        }
        .success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .info {
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }
        .progress {
            margin-top: 20px;
            display: none;
        }
        .progress-bar {
            width: 100%;
            height: 30px;
            background: #f0f0f0;
            border-radius: 15px;
            overflow: hidden;
            margin-top: 10px;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            width: 0%;
            transition: width 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 12px;
            font-weight: 500;
        }
        .example {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 6px;
            margin-top: 20px;
            font-size: 13px;
            color: #666;
        }
        .example strong {
            color: #333;
        }
        .link {
            color: #667eea;
            text-decoration: none;
        }
        .link:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎨 CivitAI Model Downloader</h1>
        <p class="subtitle">Download models from CivitAI directly to ComfyUI</p>
        
        {% if message %}
        <div class="message {{ message_type }}">
            {{ message }}
        </div>
        {% endif %}
        
        <form method="POST" action="/download" id="downloadForm">
            <div class="form-group">
                <label for="api_key">CivitAI API Key (Optional)</label>
                <input type="password" id="api_key" name="api_key" placeholder="Enter your CivitAI API key" value="{{ api_key or '' }}">
                <div class="help-text">
                    Get your API key from <a href="https://civitai.com/user/account" target="_blank" class="link">CivitAI Account Settings</a>. 
                    Required for NSFW models and higher download speeds.
                </div>
            </div>
            
            <div class="form-group">
                <label for="model_id">Model ID or URL</label>
                <input type="text" id="model_id" name="model_id" placeholder="e.g., 12345 or https://civitai.com/models/12345" required>
                <div class="help-text">
                    Enter the model ID from the CivitAI URL or paste the full URL
                </div>
            </div>
            
            <div class="form-group">
                <label for="version_id">Version ID (Optional)</label>
                <input type="text" id="version_id" name="version_id" placeholder="Leave empty for latest version">
                <div class="help-text">
                    Specify a version ID to download a specific version. Leave empty to download the latest version.
                </div>
            </div>
            
            <button type="submit" id="submitBtn">Download Model</button>
        </form>
        
        <div class="progress" id="progress">
            <div class="progress-bar">
                <div class="progress-fill" id="progressFill">0%</div>
            </div>
        </div>
        
        <div class="example">
            <strong>Example:</strong><br>
            Model URL: <code>https://civitai.com/models/12345/example-model</code><br>
            Model ID: <code>12345</code><br><br>
            The model will be automatically placed in the correct ComfyUI directory based on its type (Checkpoint, LoRA, VAE, etc.)
        </div>
    </div>
    
    <script>
        document.getElementById('downloadForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const submitBtn = document.getElementById('submitBtn');
            const progress = document.getElementById('progress');
            const progressFill = document.getElementById('progressFill');
            
            submitBtn.disabled = true;
            submitBtn.textContent = 'Downloading...';
            progress.style.display = 'block';
            progressFill.style.width = '0%';
            progressFill.textContent = '0%';
            
            // Submit form via fetch to allow progress tracking
            const formData = new FormData(this);
            const messageDiv = document.querySelector('.message');
            if (messageDiv) {
                messageDiv.className = 'message info';
                messageDiv.innerHTML = 'Download started. Progress will be shown below.';
            }
            
            // Start polling immediately, before fetch completes
            let progressInterval = null;
            
            const startPolling = () => {
                if (progressInterval) {
                    clearInterval(progressInterval);
                }
                
                progressInterval = setInterval(() => {
                    fetch('/api/progress')
                        .then(response => response.json())
                        .then(data => {
                            // Update progress bar
                            const percent = Math.min(100, Math.max(0, Math.round(data.percent || 0)));
                            console.log('Progress update:', percent + '%', 'Active:', data.active, 'Total:', data.total, 'Downloaded:', data.downloaded);
                            
                            // Only update if download is active or if we have progress data
                            if (data.active || data.percent > 0 || data.downloaded > 0) {
                                progressFill.style.width = percent + '%';
                                
                                // Show download info if available
                                if (data.total > 0) {
                                    const downloadedMB = (data.downloaded / 1024 / 1024).toFixed(1);
                                    const totalMB = (data.total / 1024 / 1024).toFixed(1);
                                    progressFill.textContent = `${percent}% (${downloadedMB}MB / ${totalMB}MB)`;
                                } else if (data.percent > 0) {
                                    progressFill.textContent = percent + '%';
                                } else if (data.downloaded > 0) {
                                    const downloadedMB = (data.downloaded / 1024 / 1024).toFixed(1);
                                    progressFill.textContent = `${percent}% (${downloadedMB}MB)`;
                                } else {
                                    progressFill.textContent = '0%';
                                }
                            }
                            
                            // Check if download is complete
                            if (!data.active) {
                                // Download completed, stop polling
                                if (progressInterval) {
                                    clearInterval(progressInterval);
                                    progressInterval = null;
                                }
                                
                                if (data.result) {
                                    // Show result message
                                    if (messageDiv) {
                                        if (data.result.success) {
                                            messageDiv.className = 'message success';
                                            let msg = '✓ ' + data.result.message;
                                            if (data.result.path) {
                                                msg += '<br><strong>Path:</strong> ' + data.result.path;
                                            }
                                            if (data.result.model_type) {
                                                msg += '<br><strong>Type:</strong> ' + data.result.model_type;
                                            }
                                            messageDiv.innerHTML = msg;
                                        } else {
                                            messageDiv.className = 'message error';
                                            messageDiv.innerHTML = '✗ ' + (data.result.message || 'Download failed');
                                        }
                                    }
                                    submitBtn.disabled = false;
                                    submitBtn.textContent = 'Download Model';
                                } else if (data.error) {
                                    if (messageDiv) {
                                        messageDiv.className = 'message error';
                                        messageDiv.innerHTML = '✗ Error: ' + data.error;
                                    }
                                    submitBtn.disabled = false;
                                    submitBtn.textContent = 'Download Model';
                                }
                            }
                        })
                        .catch(error => {
                            console.error('Error fetching progress:', error);
                        });
                }, 500);
            };
            
            fetch('/download', {
                method: 'POST',
                body: formData
            }).then(response => {
                if (!response.ok) {
                    throw new Error('Download request failed');
                }
                // Start polling after request is sent
                startPolling();
            }).catch(error => {
                console.error('Error:', error);
                if (progressInterval) {
                    clearInterval(progressInterval);
                    progressInterval = null;
                }
                if (messageDiv) {
                    messageDiv.className = 'message error';
                    messageDiv.innerHTML = '✗ Error starting download: ' + error.message;
                }
                submitBtn.disabled = false;
                submitBtn.textContent = 'Download Model';
            });
        });
        
        // Extract model ID from URL if pasted
        document.getElementById('model_id').addEventListener('paste', function(e) {
            setTimeout(() => {
                let value = this.value;
                const match = value.match(/models\/(\d+)/);
                if (match) {
                    this.value = match[1];
                }
            }, 10);
        });
    </script>
</body>
</html>
"""


def extract_model_id(model_input: str) -> str:
    """Extract model ID from URL or return as-is if it's already an ID"""
    if not model_input:
        return ""
    
    # Remove whitespace
    model_input = model_input.strip()
    
    # Check if it's a URL
    if 'civitai.com' in model_input:
        import re
        match = re.search(r'/models/(\d+)', model_input)
        if match:
            return match.group(1)
    
    # Assume it's already an ID
    return model_input


@app.route('/')
def index():
    """Main page"""
    return render_template_string(HTML_TEMPLATE, message="", message_type="")


@app.route('/download', methods=['POST'])
def download():
    """Handle model download"""
    api_key = request.form.get('api_key', '').strip() or None
    model_input = request.form.get('model_id', '').strip()
    version_id = request.form.get('version_id', '').strip() or None
    
    if not model_input:
        return render_template_string(
            HTML_TEMPLATE,
            message="Please enter a model ID or URL",
            message_type="error",
            api_key=api_key or ""
        )
    
    # Extract model ID
    model_id = extract_model_id(model_input)
    if not model_id.isdigit():
        return render_template_string(
            HTML_TEMPLATE,
            message="Invalid model ID. Please enter a valid CivitAI model ID or URL.",
            message_type="error",
            api_key=api_key or ""
        )
    
    # Initialize downloader
    global downloader, download_progress
    
    # Reset progress - set active BEFORE starting thread
    download_progress = {
        'percent': 0,
        'downloaded': 0,
        'total': 0,
        'active': True,
        'model_name': '',
        'result': None,
        'error': None
    }
    
    # Define progress callback
    def update_progress(percent, downloaded, total):
        download_progress['percent'] = percent
        download_progress['downloaded'] = downloaded
        download_progress['total'] = total
        download_progress['active'] = True  # Keep active during download
    
    downloader = CivitAIDownloader(api_key)
    
    # Download model in a thread to avoid blocking
    def download_thread():
        try:
            result = downloader.download_model(model_id, version_id, progress_callback=update_progress)
            download_progress['active'] = False
            download_progress['result'] = result
            if result.get('success'):
                download_progress['percent'] = 100
        except Exception as e:
            download_progress['active'] = False
            download_progress['error'] = str(e)
            import traceback
            download_progress['error'] = str(e) + '\n' + traceback.format_exc()
    
    import threading
    thread = threading.Thread(target=download_thread, daemon=True)
    thread.start()
    
    # Return immediately with progress tracking page
    return render_template_string(
        HTML_TEMPLATE,
        message="Download started. Progress will be shown below.",
        message_type="info",
        api_key=api_key or ""
    )


@app.route('/api/progress')
def get_progress():
    """API endpoint to get download progress"""
    global download_progress
    response = download_progress.copy()
    # Include result and error if available
    if 'result' in download_progress:
        response['result'] = download_progress['result']
    if 'error' in download_progress:
        response['error'] = download_progress['error']
    return jsonify(response)


@app.route('/api/search')
def search():
    """API endpoint to search models"""
    query = request.args.get('q', '')
    api_key = request.args.get('api_key', '').strip() or None
    
    if not query:
        return jsonify({'error': 'Query parameter required'}), 400
    
    downloader = CivitAIDownloader(api_key)
    results = downloader.search_models(query)
    
    return jsonify({
        'results': [
            {
                'id': m['id'],
                'name': m['name'],
                'type': m.get('type', 'Unknown'),
                'description': m.get('description', '')[:200] + '...' if len(m.get('description', '')) > 200 else m.get('description', '')
            }
            for m in results
        ]
    })


if __name__ == '__main__':
    port = int(os.environ.get('CIVITAI_PORT', 7860))
    host = os.environ.get('CIVITAI_HOST', '0.0.0.0')
    print(f"Starting CivitAI Downloader web interface on {host}:{port}")
    app.run(host=host, port=port, debug=False)

