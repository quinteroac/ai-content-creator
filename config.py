"""
Configuration and constants for the AI Content Creator application
"""
import os
import json

# Load default configuration from defaults.json
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULTS_FILE = os.path.join(SCRIPT_DIR, 'defaults.json')
_defaults = {}
if os.path.exists(DEFAULTS_FILE):
    try:
        with open(DEFAULTS_FILE, 'r', encoding='utf-8') as f:
            _defaults = json.load(f)
    except Exception as e:
        print(f"[Config] Warning: Could not load defaults.json: {e}")

def get_default(key_path, default_value=None):
    """Get a value from defaults.json using dot notation (e.g., 'directories.data')."""
    keys = key_path.split('.')
    value = _defaults
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default_value
    return value if value is not None else default_value

# Application directories
DATA_DIR = os.path.join(SCRIPT_DIR, get_default('directories.data', 'data'))
LOG_DIR = os.path.join(SCRIPT_DIR, get_default('directories.logs', 'logs'))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, get_default('directories.output', 'output'))
OUTPUT_IMAGES_DIR = os.path.join(SCRIPT_DIR, get_default('directories.output_images', 'output/images'))
OUTPUT_VIDEOS_DIR = os.path.join(SCRIPT_DIR, get_default('directories.output_videos', 'output/videos'))

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_IMAGES_DIR, exist_ok=True)
os.makedirs(OUTPUT_VIDEOS_DIR, exist_ok=True)

# Authentication configuration
TOTP_SECRETS_PATH = os.path.join(DATA_DIR, 'totp_secrets.json')
TOTP_ISSUER = os.environ.get('TOTP_ISSUER', get_default('auth.totp_issuer', 'AI Content Creator'))
AUTH_LOG_PATH = os.path.join(LOG_DIR, 'auth_debug.log')

ALLOWED_USERS = [
    email.strip().lower()
    for email in (os.environ.get('ALLOWED_USERS') or '').split(',')
    if email.strip()
]

# Flask configuration
FLASK_SECRET_KEY = os.urandom(24)
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID') or get_default('google.client_id')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET') or get_default('google.client_secret')
PREFERRED_URL_SCHEME = os.environ.get('PREFERRED_URL_SCHEME', get_default('flask.preferred_url_scheme', 'https'))
ENABLE_OAUTH_LOGIN = (
    os.environ.get('ENABLE_OAUTH_LOGIN', '').strip().lower() or 
    str(get_default('auth.enable_oauth_login', False)).lower()
) not in {'0', 'false', 'no', 'off', ''}

# OpenAI configuration
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY') or get_default('openai.api_key')
OPENAI_API_BASE = os.environ.get('OPENAI_API_BASE') or get_default('openai.api_base', 'https://api.openai.com/v1')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL') or get_default('openai.model', 'gpt-4o')
ENABLE_OPENAI_ENRICHMENT = (
    os.environ.get('ENABLE_OPENAI_ENRICHMENT', '').strip().lower() or 
    str(get_default('openai.enable_enrichment', False)).lower()
) not in {'0', 'false', 'no', 'off', ''}

# Application ports
ANIME_GENERATOR_PORT = int(os.environ.get('ANIME_GENERATOR_PORT', get_default('flask.port', 5000)))
ANIME_GENERATOR_HOST = os.environ.get('ANIME_GENERATOR_HOST', get_default('flask.host', '0.0.0.0'))

# Workflow paths
WORKFLOW_PATH = os.environ.get('LUMINA_WORKFLOW_PATH', get_default('workflows.generate', 'workflows/text-to-image/text-to-image-lumina.json'))
VIDEO_WORKFLOW_PATH = os.environ.get('VIDEO_WORKFLOW_PATH', get_default('workflows.video', 'workflows/image-to-video/video_wan2_2_14B_i2v_remix.json'))
EDIT_WORKFLOW_PATH = os.environ.get('EDIT_WORKFLOW_PATH', get_default('workflows.edit', 'workflows/edit-image/edit-image-qwen-2509-aio.json'))

