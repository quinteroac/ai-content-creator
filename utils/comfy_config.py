"""
ComfyUI configuration and URL management
Supports three separate endpoints: Generate, Edit, Video
"""
import os
import json
from urllib.parse import urlparse

# Load default configuration from defaults.json
DEFAULTS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'defaults.json')
_defaults = {}
if os.path.exists(DEFAULTS_FILE):
    try:
        with open(DEFAULTS_FILE, 'r', encoding='utf-8') as f:
            _defaults = json.load(f)
    except Exception as e:
        print(f"[Config] Warning: Could not load defaults.json: {e}")

def get_default(key_path, default_value=None):
    """Get a value from defaults.json using dot notation (e.g., 'comfyui.endpoints.generate')."""
    keys = key_path.split('.')
    value = _defaults
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default_value
    return value if value is not None else default_value

def normalize_comfy_url(url_value: str, default_host='127.0.0.1', default_port=8188):
    """Normalizar URL de ComfyUI, construyéndola si es necesario."""
    normalized = (url_value or '').strip()
    if not normalized:
        # Construir URL desde host y port
        comfy_host = os.environ.get('COMFYUI_HOST', default_host).strip() or default_host
        try:
            comfy_port = int(os.environ.get('COMFYUI_PORT', default_port))
        except (TypeError, ValueError):
            comfy_port = default_port
        if comfy_port == 443:
            normalized = f"https://{comfy_host}"
        else:
            normalized = f"http://{comfy_host}:{comfy_port}"
    
    return normalized.rstrip('/')

# Inicializar tres endpoints separados
# Prioridad: Variable de entorno > defaults.json > valores hardcodeados
COMFYUI_URL_GENERATE = normalize_comfy_url(
    os.environ.get('COMFYUI_URL_GENERATE', '').strip() or get_default('comfyui.endpoints.generate', ''),
    default_port=8188
)
COMFYUI_URL_EDIT = normalize_comfy_url(
    os.environ.get('COMFYUI_URL_EDIT', '').strip() or 
    os.environ.get('COMFYUI_URL', '').strip() or 
    get_default('comfyui.endpoints.edit', ''),
    default_port=8189
)
COMFYUI_URL_VIDEO = normalize_comfy_url(
    os.environ.get('COMFYUI_URL_VIDEO', '').strip() or 
    os.environ.get('COMFYUI_URL', '').strip() or 
    get_default('comfyui.endpoints.video', ''),
    default_port=8190
)

# Mantener COMFYUI_URL para compatibilidad hacia atrás (usa el endpoint de Generate)
COMFYUI_URL = COMFYUI_URL_GENERATE

# Extraer host y port del endpoint de Generate para WebSocket (usado principalmente en generate)
parsed = urlparse(COMFYUI_URL_GENERATE)
COMFYUI_HOST = parsed.hostname or '127.0.0.1'
COMFYUI_PORT = parsed.port or (443 if parsed.scheme == 'https' else 8188)
WS_PROTOCOL = "wss" if parsed.scheme == 'https' else "ws"

# Modal credentials (optional)
MODAL_KEY = os.environ.get('MODAL_KEY') or get_default('modal.key')
MODAL_SECRET = os.environ.get('MODAL_SECRET') or get_default('modal.secret')

def get_modal_headers():
    """Obtener headers opcionales para Modal (si están configurados)."""
    headers = {}
    if MODAL_KEY:
        headers["Modal-Key"] = MODAL_KEY
    if MODAL_SECRET:
        headers["Modal-Secret"] = MODAL_SECRET
    return headers

def build_comfy_headers(extra_headers=None):
    """Construir headers para ComfyUI incluyendo Modal si aplica."""
    headers = get_modal_headers()
    if extra_headers:
        headers.update(extra_headers)
    return headers

def get_comfy_url(mode='generate'):
    """Obtener la URL de ComfyUI según el modo de operación."""
    mode_lower = mode.lower()
    if mode_lower in ['edit', 'editing']:
        return COMFYUI_URL_EDIT
    elif mode_lower in ['video', 'videos']:
        return COMFYUI_URL_VIDEO
    else:  # 'generate', 'generation', default
        return COMFYUI_URL_GENERATE

def update_comfy_endpoint(endpoint_type, url):
    """Actualizar un endpoint de ComfyUI dinámicamente. Acepta cualquier valor tal cual viene, sin validar."""
    global COMFYUI_URL_GENERATE, COMFYUI_URL_EDIT, COMFYUI_URL_VIDEO, COMFYUI_URL
    global COMFYUI_HOST, COMFYUI_PORT, WS_PROTOCOL
    
    # Aceptar el valor tal cual viene, sin validar ni normalizar
    # Solo hacer un trim básico si es string
    if isinstance(url, str):
        sanitized = url.strip()
    else:
        sanitized = str(url) if url else ""
    
    # Actualizar el endpoint correspondiente
    endpoint_type_lower = endpoint_type.lower()
    if endpoint_type_lower in ['generate', 'generation']:
        COMFYUI_URL_GENERATE = sanitized
        COMFYUI_URL = sanitized  # Mantener compatibilidad
        # Intentar actualizar variables de WebSocket si parece una URL válida
        if sanitized and '://' in sanitized:
            try:
                parsed = urlparse(sanitized)
                if parsed.hostname:
                    COMFYUI_HOST = parsed.hostname
                    COMFYUI_PORT = parsed.port or (443 if parsed.scheme == 'https' else 8188)
                    WS_PROTOCOL = "wss" if parsed.scheme == 'https' else "ws"
            except Exception:
                # Si hay error, mantener valores por defecto
                pass
        print(f"[Settings] ComfyUI Generate endpoint updated to: {COMFYUI_URL_GENERATE}")
    elif endpoint_type_lower in ['edit', 'editing']:
        COMFYUI_URL_EDIT = sanitized
        print(f"[Settings] ComfyUI Edit endpoint updated to: {COMFYUI_URL_EDIT}")
    elif endpoint_type_lower in ['video', 'videos']:
        COMFYUI_URL_VIDEO = sanitized
        print(f"[Settings] ComfyUI Video endpoint updated to: {COMFYUI_URL_VIDEO}")
    else:
        raise ValueError(f"Unknown endpoint type: {endpoint_type}")
    
    return sanitized

def get_all_endpoints():
    """Obtener todos los endpoints actuales."""
    return {
        "generate": COMFYUI_URL_GENERATE,
        "edit": COMFYUI_URL_EDIT,
        "video": COMFYUI_URL_VIDEO,
        "url": COMFYUI_URL  # Para compatibilidad hacia atrás
    }

print(f"[Config] ComfyUI Generate endpoint: {COMFYUI_URL_GENERATE}")
print(f"[Config] ComfyUI Edit endpoint: {COMFYUI_URL_EDIT}")
print(f"[Config] ComfyUI Video endpoint: {COMFYUI_URL_VIDEO}")

