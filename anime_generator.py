#!/usr/bin/env python3
"""
Aplicación Web para Generación Iterativa de Imágenes de Anime
Utiliza ComfyUI para generar imágenes basadas en prompts iterativos
"""

import os
import sys
import json
import uuid
import time
import threading
import base64
import mimetypes
import io
import random
import csv
from functools import wraps

import pyotp
import qrcode
import websocket
import requests
import datetime
import logging
import traceback
from authlib.integrations.flask_client import OAuth
from urllib.parse import urlparse
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_from_directory,
    Response,
    redirect,
    url_for,
    session,
    abort,
)
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)  # Permitir CORS para que el frontend pueda hacer requests
app.config['SECRET_KEY'] = os.urandom(24)
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET')
app.config['PREFERRED_URL_SCHEME'] = os.environ.get('PREFERRED_URL_SCHEME', 'https')
app.config['ENABLE_OAUTH_LOGIN'] = (
    os.environ.get('ENABLE_OAUTH_LOGIN', 'false').strip().lower() not in {'0', 'false', 'no', 'off'}
)

ALLOWED_USERS = [
    email.strip().lower()
    for email in (os.environ.get('ALLOWED_USERS') or '').split(',')
    if email.strip()
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, 'data')
TOTP_SECRETS_PATH = os.path.join(DATA_DIR, 'totp_secrets.json')
TOTP_ISSUER = os.environ.get('TOTP_ISSUER', 'Anime Generator')

LOG_DIR = os.path.join(SCRIPT_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
AUTH_LOG_PATH = os.path.join(LOG_DIR, 'auth_debug.log')

OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

oauth = OAuth(app)
if app.config['ENABLE_OAUTH_LOGIN']:
    if app.config['GOOGLE_CLIENT_ID'] and app.config['GOOGLE_CLIENT_SECRET']:
        oauth.register(
            name='google',
            client_id=app.config['GOOGLE_CLIENT_ID'],
            client_secret=app.config['GOOGLE_CLIENT_SECRET'],
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'},
        )
    else:
        print(
            "Warning: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured for Google login."
        )
else:
    print("OAuth login disabled via ENABLE_OAUTH_LOGIN.")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

auth_logger = logging.getLogger('auth_debug')
if not auth_logger.handlers:
    auth_logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler(AUTH_LOG_PATH, encoding='utf-8')
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    auth_logger.addHandler(file_handler)
    auth_logger.propagate = False


def load_totp_secrets():
    if not os.path.exists(TOTP_SECRETS_PATH):
        return {}
    try:
        with open(TOTP_SECRETS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as exc:
        print(f"Warning: Unable to load TOTP secrets: {exc}")
    return {}


def save_totp_secrets(secrets):
    try:
        with open(TOTP_SECRETS_PATH, 'w', encoding='utf-8') as f:
            json.dump(secrets, f, indent=2)
    except Exception as exc:
        print(f"Warning: Unable to persist TOTP secrets: {exc}")


TOTP_SECRETS = load_totp_secrets()


def is_user_allowed(email):
    if not email:
        return False
    if not ALLOWED_USERS:
        return True
    return email.lower() in ALLOWED_USERS


def get_user_totp_secret(email):
    return TOTP_SECRETS.get(email.lower())


def ensure_user_totp_secret(email):
    normalized = email.lower()
    secret = TOTP_SECRETS.get(normalized)
    if not secret:
        secret = pyotp.random_base32()
        TOTP_SECRETS[normalized] = secret
        save_totp_secrets(TOTP_SECRETS)
    return secret


def is_authenticated():
    if not app.config['ENABLE_OAUTH_LOGIN']:
        return True
    return (
        session.get('user_email')
        and session.get('google_sub')
        and session.get('2fa_verified')
    )


def api_login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not app.config['ENABLE_OAUTH_LOGIN']:
            return func(*args, **kwargs)
        if not is_authenticated():
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        return func(*args, **kwargs)

    return wrapper


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not app.config['ENABLE_OAUTH_LOGIN']:
            return view_func(*args, **kwargs)
        if is_authenticated():
            return view_func(*args, **kwargs)

        if session.get('pending_2fa'):
            return redirect(url_for('two_factor'))

        next_url = request.args.get('next') or request.path or '/'
        session['next_url'] = next_url
        return redirect(url_for('login_page', next=next_url))

    return wrapper


def get_next_url(default='/'):
    return session.pop('next_url', None) or request.args.get('next') or default


def require_oauth():
    if not app.config['ENABLE_OAUTH_LOGIN']:
        abort(404, description="OAuth login is disabled.")
    if not (app.config['GOOGLE_CLIENT_ID'] and app.config['GOOGLE_CLIENT_SECRET']):
        abort(503, description="Google OAuth is not configured.")
    return oauth.create_client('google')


@app.route('/login')
def login_page():
    if not app.config['ENABLE_OAUTH_LOGIN']:
        return redirect(url_for('index'))
    if is_authenticated():
        return redirect(url_for('index'))

    error_code = request.args.get('error')
    error_messages = {
        'unauthorized': 'Access denied for this account.',
        'oauth_error': 'Authentication failed. Please try again.',
        '2fa_failed': 'Invalid verification code. Please try again.',
    }
    error_message = error_messages.get(error_code)
    next_url = request.args.get('next') or session.get('next_url') or '/'
    return render_template('login.html', error=error_message, next_url=next_url)


@app.route('/auth/google')
def auth_google():
    if not app.config['ENABLE_OAUTH_LOGIN']:
        return redirect(url_for('login_page'))
    next_url = request.args.get('next') or request.referrer or '/'
    session['next_url'] = next_url
    google = require_oauth()
    redirect_uri = url_for('auth_google_callback', _external=True)
    nonce = uuid.uuid4().hex
    session['oauth_nonce'] = nonce
    return google.authorize_redirect(redirect_uri, nonce=nonce)


@app.route('/auth/google/callback')
def auth_google_callback():
    if not app.config['ENABLE_OAUTH_LOGIN']:
        return redirect(url_for('login_page'))
    google = require_oauth()
    try:
        token = google.authorize_access_token()
        nonce = session.pop('oauth_nonce', None)
        userinfo = google.parse_id_token(token, nonce=nonce)
        if not userinfo:
            userinfo = google.get('userinfo').json()
        auth_logger.info(
            "OAuth callback success. token_keys=%s userinfo_keys=%s",
            list((token or {}).keys()),
            list((userinfo or {}).keys()),
        )
    except Exception as exc:
        auth_logger.error("OAuth callback error: %s", exc)
        auth_logger.error("Traceback: %s", traceback.format_exc())
        auth_logger.error("OAuth token payload: %s", token)
        session.clear()
        return redirect(url_for('login_page', error='oauth_error'))

    email = (userinfo or {}).get('email')
    sub = (userinfo or {}).get('sub')
    if not email or not sub:
        auth_logger.warning(
            "OAuth callback missing email/sub. userinfo=%s", userinfo
        )
        session.clear()
        return redirect(url_for('login_page', error='oauth_error'))

    if not is_user_allowed(email):
        auth_logger.info("OAuth login rejected (not allowed): %s", email)
        session.clear()
        return redirect(url_for('login_page', error='unauthorized'))

    auth_logger.info("OAuth login accepted for %s (sub=%s)", email.lower(), sub)

    session['user_email'] = email.lower()
    session['google_sub'] = sub
    session['pending_2fa'] = True
    session.pop('2fa_verified', None)

    secret = get_user_totp_secret(email)
    if secret:
        session.pop('needs_2fa_setup', None)
        return redirect(url_for('two_factor'))

    ensure_user_totp_secret(email)
    session['needs_2fa_setup'] = True
    return redirect(url_for('two_factor_setup'))


@app.route('/2fa', methods=['GET', 'POST'])
def two_factor():
    if not app.config['ENABLE_OAUTH_LOGIN']:
        return redirect(url_for('index'))
    email = session.get('user_email')
    if not session.get('pending_2fa') or not email:
        return redirect(url_for('login_page'))

    if session.get('needs_2fa_setup'):
        return redirect(url_for('two_factor_setup'))

    secret = get_user_totp_secret(email)
    if not secret:
        session['needs_2fa_setup'] = True
        return redirect(url_for('two_factor_setup'))

    error = None
    if request.method == 'POST':
        code = (request.form.get('code') or '').strip()
        totp = pyotp.TOTP(secret)
        if totp.verify(code, valid_window=1):
            auth_logger.info("2FA verification success for %s", email)
            session['2fa_verified'] = True
            session['pending_2fa'] = False
            session.pop('needs_2fa_setup', None)
            return redirect(get_next_url(url_for('index')))
        error = 'Invalid verification code. Try again.'
        auth_logger.warning("2FA verification failed for %s", email)

    return render_template('two_factor_verify.html', error=error)


@app.route('/2fa/setup', methods=['GET', 'POST'])
def two_factor_setup():
    if not app.config['ENABLE_OAUTH_LOGIN']:
        return redirect(url_for('index'))
    email = session.get('user_email')
    if not session.get('pending_2fa') or not email:
        return redirect(url_for('login_page'))

    secret = ensure_user_totp_secret(email)
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=email, issuer_name=TOTP_ISSUER)

    buffer = io.BytesIO()
    qrcode.make(provisioning_uri).save(buffer, format='PNG')
    qr_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    error = None
    if request.method == 'POST':
        code = (request.form.get('code') or '').strip()
        if totp.verify(code, valid_window=1):
            auth_logger.info("2FA setup complete for %s", email)
            session['2fa_verified'] = True
            session['pending_2fa'] = False
            session.pop('needs_2fa_setup', None)
            return redirect(get_next_url(url_for('index')))
        error = 'Invalid verification code. Try again.'
        auth_logger.warning("2FA setup failed (bad code) for %s", email)

    return render_template(
        'two_factor_setup.html',
        qr_code=qr_b64,
        provisioning_uri=provisioning_uri,
        error=error,
    )


@app.route('/logout')
def logout():
    if not app.config['ENABLE_OAUTH_LOGIN']:
        session.clear()
        return redirect(url_for('index'))
    session.clear()
    return redirect(url_for('login_page'))


# Cache de tags en memoria
TAGS_CACHE = {}
TAGS_CACHE_LOADED = False

def load_tags_cache():
    """Cargar todos los tags en memoria organizados por categoría"""
    global TAGS_CACHE, TAGS_CACHE_LOADED
    
    if TAGS_CACHE_LOADED:
        return
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, 'data', 'tags.csv')
    
    if not os.path.exists(csv_path):
        print(f"Warning: Tags file not found at {csv_path}")
        TAGS_CACHE_LOADED = True
        return
    
    print("Loading tags into memory...")
    start_time = time.time()
    
    # Diccionario temporal para acumular tags por categoría
    tags_by_category = {}
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            category = row['category']
            tag_name = row['name']
            post_count = int(row['post_count'])
            
            if category not in tags_by_category:
                tags_by_category[category] = []
            
            tags_by_category[category].append({
                'name': tag_name,
                'post_count': post_count
            })
    
    # Ordenar cada categoría por post_count (más populares primero)
    for category in tags_by_category:
        tags_by_category[category].sort(key=lambda x: x['post_count'], reverse=True)
    
    TAGS_CACHE = tags_by_category
    TAGS_CACHE_LOADED = True
    
    elapsed = time.time() - start_time
    total_tags = sum(len(tags) for tags in TAGS_CACHE.values())
    print(f"Loaded {total_tags} tags in {elapsed:.2f} seconds ({len(TAGS_CACHE)} categories)")

# Agregar headers de no-caché para archivos estáticos
@app.after_request
def add_no_cache_headers(response):
    """Agregar headers de no-caché para HTML, JS y CSS"""
    if response.content_type and (
        'text/html' in response.content_type or
        'application/javascript' in response.content_type or
        'text/css' in response.content_type
    ):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# Configuración de ComfyUI
# Permite especificar URL completa o construirla desde host y port
def apply_comfy_endpoint(url_value: str):
    """Actualizar variables globales relacionadas al endpoint de ComfyUI."""
    global COMFYUI_URL, COMFYUI_HOST, COMFYUI_PORT, WS_PROTOCOL

    normalized = (url_value or '').strip()
    if not normalized:
        raise ValueError("ComfyUI endpoint URL cannot be empty.")

    COMFYUI_URL = normalized.rstrip('/')
    parsed = urlparse(COMFYUI_URL)
    COMFYUI_HOST = parsed.hostname or '127.0.0.1'
    COMFYUI_PORT = parsed.port or (443 if parsed.scheme == 'https' else 8188)
    WS_PROTOCOL = "wss" if parsed.scheme == 'https' else "ws"


env_comfy_url = os.environ.get('COMFYUI_URL', '').strip()
if env_comfy_url:
    apply_comfy_endpoint(env_comfy_url)
else:
    comfy_host = os.environ.get('COMFYUI_HOST', '127.0.0.1').strip() or '127.0.0.1'
    try:
        comfy_port = int(os.environ.get('COMFYUI_PORT', 8188))
    except (TypeError, ValueError):
        comfy_port = 8188
    if comfy_port == 443:
        apply_comfy_endpoint(f"https://{comfy_host}")
    else:
        apply_comfy_endpoint(f"http://{comfy_host}:{comfy_port}")

# Almacenar estados de generación
generation_status = {}

# Cargar workflow desde archivo JSON
def load_workflow(workflow_path, default_relative=None):
    """Cargar workflow desde archivo JSON"""
    try:
        # Intentar rutas relativas y absolutas
        script_dir = os.path.dirname(os.path.abspath(__file__))
        possible_paths = [
            workflow_path,  # Ruta absoluta o relativa al directorio actual
            os.path.join(script_dir, workflow_path),  # Relativa al script
        ]
        if default_relative:
            possible_paths.append(os.path.join(script_dir, default_relative))
        
        for path in possible_paths:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    workflow = json.load(f)
                    print(f"[OK] Workflow cargado desde: {path}")
                    return workflow
        
        raise FileNotFoundError(f"Workflow no encontrado en ninguna de las rutas: {possible_paths}")
    except Exception as e:
        print(f"Error cargando workflow: {e}")
        raise

# Cargar workflow base de Illustrious por defecto
WORKFLOW_PATH = os.environ.get('LUMINA_WORKFLOW_PATH', 'workflows/text-to-image/text-to-image-illustrious.json')
VIDEO_WORKFLOW_PATH = os.environ.get('VIDEO_WORKFLOW_PATH', 'workflows/image-to-video/video_wan2_2_14B_i2v_remix.json')
EDIT_WORKFLOW_PATH = os.environ.get('EDIT_WORKFLOW_PATH', 'workflows/edit-image/edit-image-qwen-2509.json')
try:
    BASE_WORKFLOW = load_workflow(WORKFLOW_PATH, 'workflows/text-to-image/text-to-image-illustrious.json')
except Exception as e:
    print(f"Error fatal: No se pudo cargar el workflow de Illustrious: {e}")
    print("Asegúrate de que el archivo workflows/text-to-image/text-to-image-illustrious.json existe")
    sys.exit(1)

try:
    EDIT_WORKFLOW = load_workflow(EDIT_WORKFLOW_PATH, 'workflows/edit-image/edit-image-qwen-2509.json')
except Exception as e:
    print(f"Error fatal: No se pudo cargar el workflow de edición: {e}")
    print("Asegúrate de que el archivo workflows/edit-image/edit-image-qwen-2509.json existe")
    sys.exit(1)

def queue_prompt(workflow, client_id=str(uuid.uuid4())):
    """Enviar prompt a la cola de ComfyUI"""
    try:
        p = {"prompt": workflow, "client_id": client_id}
        data = json.dumps(p).encode('utf-8')
        
        response = requests.post(
            f"{COMFYUI_URL}/prompt",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Error sending prompt: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error in queue_prompt: {e}")
        raise

def get_media_outputs(prompt_id, target_nodes=None, media_key="images"):
    """Obtener archivos generados (imágenes, videos, etc.) para un prompt_id específico"""
    target_nodes = target_nodes or ["19"]
    possible_keys = [media_key]
    if media_key == "videos":
        possible_keys.extend(["video", "files", "images"])  # ComfyUI variations
    elif media_key == "images":
        possible_keys.extend(["image", "files"])
    else:
        possible_keys.extend(["videos", "images", "files"])
    try:
        # Intentar primero el endpoint específico /history/{prompt_id}
        try:
            response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=5)
            if response.status_code == 200:
                history_data = response.json()
                print(f"[OK] Endpoint /history/{prompt_id} works correctly")
                print(f"[DEBUG] /history/{prompt_id} keys: {list(history_data.keys())}")

                # Algunos backends devuelven {"outputs": {...}}, otros {prompt_id: {...}}
                candidates = []
                if isinstance(history_data, dict):
                    if "outputs" in history_data:
                        candidates.append(history_data)
                    if prompt_id in history_data and isinstance(history_data[prompt_id], dict):
                        candidates.append(history_data[prompt_id])

                for candidate in candidates:
                    if "outputs" not in candidate:
                        continue
                    for node_id in target_nodes:
                        if node_id in candidate["outputs"]:
                            node_outputs = candidate["outputs"][node_id]
                            print(f"[DEBUG] Node {node_id} outputs keys: {list(node_outputs.keys())}")
                            for key in possible_keys:
                                if key in node_outputs:
                                    media = node_outputs[key]
                                    count = len(media) if isinstance(media, list) else 1
                                    print(f"[OK] {key.capitalize()} found in specific endpoint: {count}")
                                    if isinstance(media, list):
                                        return media
                                    return [media]

                if not candidates:
                    print(f"[WARN] Unexpected structure from /history/{prompt_id}: {history_data}")
                else:
                    print(f"[WARN] 'outputs' key not found in candidates for /history/{prompt_id}")
        except requests.exceptions.RequestException as e:
            print(f"[WARN] Endpoint /history/{prompt_id} not available (status: {getattr(e.response, 'status_code', 'N/A')}), using fallback")

        # Fallback: obtener el historial completo y buscar el prompt_id
        print(f"Using full history to search for prompt_id: {prompt_id}")
        response = requests.get(f"{COMFYUI_URL}/history", timeout=5)
        if response.status_code == 200:
            history = response.json()
            print(f"Searching for prompt_id '{prompt_id}' in history. Total entries: {len(history)}")
            if prompt_id in history:
                prompt_data = history[prompt_id]
                print(f"[OK] Prompt_id found in history")
                print(f"[DEBUG] prompt_data keys: {list(prompt_data.keys())}")
                if "outputs" in prompt_data:
                    for node_id in target_nodes:
                        if node_id in prompt_data["outputs"]:
                            node_outputs = prompt_data["outputs"][node_id]
                            print(f"[DEBUG] Node {node_id} outputs keys: {list(node_outputs.keys())}")
                            for key in possible_keys:
                                if key in node_outputs:
                                    media = node_outputs[key]
                                    count = len(media) if isinstance(media, list) else 1
                                    print(f"[OK] {key.capitalize()} found in full history: {count}")
                                    if isinstance(media, list):
                                        print(f"  Filenames: {[item.get('filename', str(item)) if isinstance(item, dict) else item for item in media[:4]]}")
                                        return media
                                    print(f"  Filename: {media.get('filename', str(media)) if isinstance(media, dict) else media}")
                                    return [media]
                else:
                    print(f"[WARN] 'outputs' key not found in prompt_data: {prompt_data}")
            else:
                print(f"[WARN] Prompt_id '{prompt_id}' not found in history. Available IDs: {list(history.keys())[:5]}...")

            # Buscar en toda la estructura como último recurso
            for key, value in history.items():
                if key == prompt_id and isinstance(value, dict) and "outputs" in value:
                    for node_id, node_data in value.get("outputs", {}).items():
                        if node_id in target_nodes:
                            print(f"[DEBUG] Node {node_id} (fallback) outputs keys: {list(node_data.keys())}")
                            for media_key_candidate in possible_keys:
                                if media_key_candidate in node_data:
                                    media = node_data[media_key_candidate]
                                    if isinstance(media, list):
                                        return media
                                    return [media]
                elif key == prompt_id:
                    print(f"[WARN] Fallback entry for {prompt_id} lacks 'outputs': {value}")
        return None
    except Exception as e:
        print(f"Error getting history for prompt_id {prompt_id}: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_image_filename(prompt_id):
    """Compatibilidad hacia atrás para obtener imágenes generadas"""
    return get_media_outputs(prompt_id, target_nodes=["19"], media_key="images")

def wait_for_completion(client_id, prompt_id, max_wait=300, target_nodes=None, media_key="images"):
    """Esperar a que se complete la generación y obtener los archivos solicitados"""
    target_nodes = target_nodes or ["19"]
    media_items = []
    execution_completed = False
    
    def on_message(ws, message):
        nonlocal execution_completed
        if message:
            try:
                data = json.loads(message)
                if data.get("type") == "executed":
                    node_id = data.get("data", {}).get("node")
                    if node_id and node_id in target_nodes:
                        execution_completed = True
                elif data.get("type") == "execution_cached":
                    execution_completed = True
                elif data.get("type") == "executing":
                    if not data.get("data", {}).get("node"):  # Ejecución completada
                        execution_completed = True
            except Exception as e:
                print(f"Error procesando mensaje WebSocket: {e}")
    
    def on_error(ws, error):
        print(f"WebSocket error: {error}")
    
    def on_close(ws, close_status_code, close_msg):
        pass
    
    def on_open(ws):
        pass
    
    # Intentar conectar via WebSocket
    ws = None
    try:
        # Construir URL WebSocket con el protocolo correcto
        if COMFYUI_PORT == 443 and WS_PROTOCOL == "wss":
            ws_url = f"{WS_PROTOCOL}://{COMFYUI_HOST}/ws?clientId={client_id}"
        else:
            ws_url = f"{WS_PROTOCOL}://{COMFYUI_HOST}:{COMFYUI_PORT}/ws?clientId={client_id}"
        ws = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )
        
        # Ejecutar WebSocket en thread separado
        def run_ws():
            try:
                ws.run_forever()
            except Exception as e:
                print(f"Error en WebSocket: {e}")
        
        thread = threading.Thread(target=run_ws, daemon=True)
        thread.start()
        
        # Dar tiempo para que se conecte
        time.sleep(1)
    except Exception as e:
        print(f"Error al conectar WebSocket: {e}")
        # Continuar sin WebSocket, usaremos polling
    
    # Esperar hasta que se complete o timeout
    start_time = time.time()
    check_interval = 0.5  # Verificar cada 0.5 segundos para respuesta más rápida
    last_check = 0
    
    # Primera verificación inmediata (para el mock que guarda instantáneamente)
    media_info = get_media_outputs(prompt_id, target_nodes=target_nodes, media_key=media_key)
    if media_info and len(media_info) > 0:
        valid_media = []
        for item in media_info:
            if isinstance(item, dict):
                valid_media.append({
                    "filename": item.get("filename", ""),
                    "subfolder": item.get("subfolder", ""),
                    "type": item.get("type", "output")
                })
            elif isinstance(item, str):
                valid_media.append({
                    "filename": item,
                    "subfolder": "",
                    "type": "output"
                })

        if valid_media:
            print(f"[OK] {media_key.capitalize()} found immediately, returning {len(valid_media)} item(s)")
            if ws:
                try:
                    ws.close()
                except:
                    pass
            return valid_media
    
    while time.time() - start_time < max_wait:
        # Verificar si hay imágenes disponibles en el historial
        if time.time() - last_check >= check_interval:
            media_info = get_media_outputs(prompt_id, target_nodes=target_nodes, media_key=media_key)
            if media_info and len(media_info) > 0:
                valid_media = []
                for item in media_info:
                    if isinstance(item, dict):
                        valid_media.append({
                            "filename": item.get("filename", ""),
                            "subfolder": item.get("subfolder", ""),
                            "type": item.get("type", "output")
                        })
                    elif isinstance(item, str):
                        valid_media.append({
                            "filename": item,
                            "subfolder": "",
                            "type": "output"
                        })

                if valid_media:
                    media_items = valid_media
                    if len(media_items) >= 1:
                        break
                    if execution_completed:
                        break
            last_check = time.time()
        
        # Si execution_completed, esperar un poco más para que se guarden las imágenes
        if execution_completed:
            time.sleep(2)
            media_info = get_media_outputs(prompt_id, target_nodes=target_nodes, media_key=media_key)
            if media_info and len(media_info) > 0:
                valid_media = []
                for item in media_info:
                    if isinstance(item, dict):
                        valid_media.append({
                            "filename": item.get("filename", ""),
                            "subfolder": item.get("subfolder", ""),
                            "type": item.get("type", "output")
                        })
                    elif isinstance(item, str):
                        valid_media.append({
                            "filename": item,
                            "subfolder": "",
                            "type": "output"
                        })
                if valid_media:
                    media_items = valid_media
                    break
        
        time.sleep(0.5)
    
    # Cerrar WebSocket si está abierto
    if ws:
        try:
            ws.close()
        except:
            pass
    
    # Si aún no tenemos imágenes, intentar obtenerlas del historial una vez más
    if not media_items:
        time.sleep(2)  # Esperar un poco más
        media_info = get_media_outputs(prompt_id, target_nodes=target_nodes, media_key=media_key)
        if media_info:
            if isinstance(media_info, list):
                media_items = media_info
            else:
                media_items = [media_info]

    return media_items

def generate_random_seed():
    """Generar una semilla aleatoria para la generación de imágenes"""
    return random.randint(0, 2**32 - 1)


def upload_image_to_comfy(filename, subfolder='', image_type='output'):
    """Descargar una imagen desde ComfyUI y subirla al directorio de inputs"""
    params = {
        'filename': filename,
        'type': image_type or 'output'
    }
    if subfolder:
        params['subfolder'] = subfolder

    response = requests.get(f"{COMFYUI_URL}/view", params=params, timeout=60)
    if response.status_code != 200:
        raise ValueError(f"Unable to retrieve source image: HTTP {response.status_code}")

    content_type = response.headers.get('Content-Type', 'image/png')
    extension = os.path.splitext(filename)[1] or '.png'
    upload_name = f"video_source_{uuid.uuid4().hex}{extension}"

    upload_response = requests.post(
        f"{COMFYUI_URL}/upload/image",
        data={'type': 'input', 'overwrite': 'true'},
        files={'image': (upload_name, response.content, content_type)},
        timeout=60
    )

    if upload_response.status_code != 200:
        raise ValueError(f"Unable to upload source image: HTTP {upload_response.status_code}")

    return upload_name


def upload_image_bytes_to_comfy(content_bytes, filename='upload.png', mime_type='image/png', image_type='input'):
    """Subir bytes de imagen directamente a ComfyUI"""
    if not content_bytes:
        raise ValueError("Empty image content provided")

    base_name = secure_filename(os.path.basename(filename)) or "upload.png"
    extension = os.path.splitext(base_name)[1]
    if not extension:
        guessed_ext = mimetypes.guess_extension(mime_type or '')
        extension = guessed_ext if guessed_ext else '.png'
        base_name = f"{base_name}{extension}"

    upload_name = f"user_upload_{uuid.uuid4().hex}{extension}"

    upload_response = requests.post(
        f"{COMFYUI_URL}/upload/image",
        data={'type': image_type, 'overwrite': 'true'},
        files={'image': (upload_name, content_bytes, mime_type or 'image/png')},
        timeout=60
    )

    if upload_response.status_code != 200:
        raise ValueError(f"Unable to upload provided image: HTTP {upload_response.status_code}")

    return upload_name


def upload_image_data_url_to_comfy(data_url, filename='upload.png', mime_type_override=None):
    """Convertir un data URL a bytes y subirlo a ComfyUI"""
    if not data_url or ',' not in data_url:
        raise ValueError("Invalid image data URL")

    header, encoded = data_url.split(',', 1)
    mime_type = 'image/png'
    if header.startswith('data:'):
        mime_section = header[5:]
        if ';' in mime_section:
            mime_type = mime_section.split(';', 1)[0] or 'image/png'
        else:
            mime_type = mime_section or 'image/png'
    if mime_type_override:
        mime_type = mime_type_override

    try:
        content_bytes = base64.b64decode(encoded)
    except Exception as exc:
        raise ValueError(f"Invalid base64 image content: {exc}") from exc

    return upload_image_bytes_to_comfy(content_bytes, filename=filename, mime_type=mime_type, image_type='input')


def resolve_local_media_path(filename):
    """Resolver la ruta absoluta de un archivo guardado en el directorio local de salida."""
    if not filename:
        raise ValueError("Local filename is required")

    if os.path.sep in filename or (os.path.altsep and os.path.altsep in filename):
        raise ValueError("Invalid local filename")

    output_root = os.path.abspath(OUTPUT_DIR)
    candidate_path = os.path.abspath(os.path.join(OUTPUT_DIR, filename))
    if not candidate_path.startswith(output_root):
        raise ValueError("Local filename resolves outside of output directory")
    return candidate_path


def persist_media_locally(media_items, prompt_id, media_category="images"):
    """Descargar archivos generados desde ComfyUI y guardarlos en el directorio local."""
    if not media_items:
        return []

    saved_items = []
    output_root = os.path.abspath(OUTPUT_DIR)
    os.makedirs(output_root, exist_ok=True)

    for index, item in enumerate(media_items, start=1):
        if isinstance(item, dict):
            remote_filename = item.get("filename") or f"{prompt_id}_{index}"
            remote_subfolder = item.get("subfolder", "")
            remote_type = item.get("type") or "output"
            format_hint = item.get("format") or item.get("extension")
        else:
            remote_filename = str(item)
            remote_subfolder = ""
            remote_type = "output"
            format_hint = None

        params = {"filename": remote_filename, "type": remote_type or "output"}
        if remote_subfolder:
            params["subfolder"] = remote_subfolder
        if format_hint:
            params["format"] = format_hint

        response = requests.get(
            f"{COMFYUI_URL}/view",
            params=params,
            stream=True,
            timeout=90,
        )
        if response.status_code != 200:
            response.close()
            raise ValueError(
                f"Unable to download generated {media_category[:-1] if media_category.endswith('s') else media_category} "
                f"'{remote_filename}': HTTP {response.status_code}"
            )

        content_type = response.headers.get("Content-Type", "")
        extension = os.path.splitext(remote_filename)[1]
        if not extension:
            if format_hint:
                extension = f".{format_hint.lstrip('.')}"
            elif content_type:
                guessed = mimetypes.guess_extension(content_type.split(';')[0])
                extension = guessed or (".mp4" if media_category == "videos" else ".png")
            else:
                extension = ".mp4" if media_category == "videos" else ".png"

        local_filename = f"{prompt_id}_{media_category}_{index:02d}_{uuid.uuid4().hex}{extension}"
        local_path = os.path.join(output_root, local_filename)

        try:
            with open(local_path, "wb") as output_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        output_file.write(chunk)
        finally:
            response.close()

        try:
            file_size = os.path.getsize(local_path)
        except OSError:
            file_size = None

        media_record = {
            "filename": local_filename,
            "type": "local",
            "subfolder": "",
            "prompt_id": prompt_id,
            "local_path": local_filename,
            "mime_type": content_type or ("video/mp4" if media_category == "videos" else "image/png"),
            "size": file_size,
            "original_name": remote_filename,
            "original": {
                "filename": remote_filename,
                "subfolder": remote_subfolder,
                "type": remote_type,
            },
        }

        if format_hint:
            media_record["format"] = format_hint

        saved_items.append(media_record)

    return saved_items


def upload_local_media_to_comfy(local_filename):
    """Subir un archivo de imagen almacenado localmente a ComfyUI."""
    resolved_path = resolve_local_media_path(local_filename)
    if not os.path.exists(resolved_path):
        raise ValueError(f"Local media file not found: {local_filename}")

    mime_type = mimetypes.guess_type(resolved_path)[0] or 'image/png'
    with open(resolved_path, "rb") as media_file:
        content_bytes = media_file.read()

    return upload_image_bytes_to_comfy(
        content_bytes,
        filename=os.path.basename(resolved_path),
        mime_type=mime_type,
        image_type='input',
    )


def generate_images(positive_prompt, negative_prompt=None, width=1024, height=1024, steps=20, seed=None):
    """Generar imágenes usando ComfyUI"""
    client_id = str(uuid.uuid4())
    
    # Crear workflow con el prompt proporcionado
    workflow = json.loads(json.dumps(BASE_WORKFLOW))

    # Actualizar prompts positivos (nodos 6 y 15)
    positive_nodes = ["6", "15"]
    base_positive = ""
    for node_id in positive_nodes:
        base_positive = workflow.get(node_id, {}).get("inputs", {}).get("text", "")
        if base_positive:
            break

    if base_positive:
        if "<Prompt Start>" in base_positive:
            parts = base_positive.split("<Prompt Start>")
            new_positive = parts[0] + "<Prompt Start> Digital anime illustration " + positive_prompt
        else:
            new_positive = f"{base_positive} {positive_prompt}".strip()
    else:
        new_positive = positive_prompt

    for node_id in positive_nodes:
        if node_id in workflow and "inputs" in workflow[node_id]:
            workflow[node_id]["inputs"]["text"] = new_positive

    # Actualizar prompts negativos (nodos 7 y 16) si se proporciona
    if negative_prompt:
        negative_nodes = ["7", "16"]
        base_negative = ""
        for node_id in negative_nodes:
            base_negative = workflow.get(node_id, {}).get("inputs", {}).get("text", "")
            if base_negative:
                break
        if base_negative:
            new_negative = f"{base_negative} {negative_prompt}".strip()
        else:
            new_negative = negative_prompt

        for node_id in negative_nodes:
            if node_id in workflow and "inputs" in workflow[node_id]:
                workflow[node_id]["inputs"]["text"] = new_negative

    # Actualizar resolución (nodo 5 - EmptyLatentImage)
    if "5" in workflow and "inputs" in workflow["5"]:
        workflow["5"]["inputs"]["width"] = int(width)
        workflow["5"]["inputs"]["height"] = int(height)

    # Actualizar configuración de muestreo (nodos 10 y 11 - KSamplerAdvanced)
    sampler_nodes = ["10", "11"]
    steps_value = int(steps)
    seed_value = int(seed) if seed is not None else generate_random_seed()

    for node_id in sampler_nodes:
        if node_id in workflow and "inputs" in workflow[node_id]:
            sampler_inputs = workflow[node_id]["inputs"]
            if "steps" in sampler_inputs:
                sampler_inputs["steps"] = steps_value
            if "noise_seed" in sampler_inputs:
                sampler_inputs["noise_seed"] = seed_value
    
    try:
        # Enviar a la cola
        result = queue_prompt(workflow, client_id)
        prompt_id = result["prompt_id"]
        
        # Esperar a que se complete
        images = wait_for_completion(client_id, prompt_id)
        local_images = persist_media_locally(images, prompt_id, media_category="images")
        if not local_images:
            raise ValueError("No images were persisted locally after generation.")

        return {
            "success": True,
            "prompt_id": prompt_id,
            "images": local_images,
            "client_id": client_id
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }



def generate_video_from_image(positive_prompt, source_image, width=None, height=None, negative_prompt=None, length=None, fps=None):
    """Generar un video a partir de una imagen usando ComfyUI"""
    workflow = load_workflow(VIDEO_WORKFLOW_PATH, 'workflows/image-to-video/video_wan2_2_14B_i2v_remix.json')
    if not workflow:
        raise ValueError("Video workflow could not be loaded")

    workflow = json.loads(json.dumps(workflow))

    if "93" in workflow:
        workflow["93"]["inputs"]["text"] = positive_prompt

    if negative_prompt and "89" in workflow:
        base_negative = workflow["89"]["inputs"].get("text", "")
        workflow["89"]["inputs"]["text"] = f"{base_negative} {negative_prompt}".strip()

    if length is not None and "98" in workflow:
        try:
            workflow["98"]["inputs"]["length"] = int(length)
        except (ValueError, TypeError):
            pass

    if fps is not None and "94" in workflow:
        try:
            workflow["94"]["inputs"]["fps"] = int(fps)
        except (ValueError, TypeError):
            pass

    if width is not None and "98" in workflow:
        try:
            workflow["98"]["inputs"]["width"] = int(width)
        except (ValueError, TypeError):
            pass

    if height is not None and "98" in workflow:
        try:
            workflow["98"]["inputs"]["height"] = int(height)
        except (ValueError, TypeError):
            pass

    if source_image.get('data_url'):
        upload_name = upload_image_data_url_to_comfy(
            data_url=source_image.get('data_url'),
            filename=source_image.get('filename') or source_image.get('original_name') or "upload.png",
            mime_type_override=source_image.get('mime_type')
        )
    elif (source_image.get('type') or '').lower() == 'local':
        upload_name = upload_local_media_to_comfy(
            source_image.get('local_path') or source_image.get('filename', '')
        )
    else:
        upload_name = upload_image_to_comfy(
            filename=source_image.get('filename', ''),
            subfolder=source_image.get('subfolder', ''),
            image_type=source_image.get('type', 'output')
        )

    if "97" in workflow:
        workflow["97"]["inputs"]["image"] = upload_name

    client_id = str(uuid.uuid4())

    result = queue_prompt(workflow, client_id)
    prompt_id = result.get("prompt_id")

    videos = wait_for_completion(
        client_id,
        prompt_id,
        target_nodes=["108", "94"],  # Prefer SaveVideo (node 108), fallback to CreateVideo (94)
        media_key="videos"
    )

    if not videos:
        raise ValueError("Video generation completed but no output was returned")

    normalized_videos = []
    for video in videos:
        if isinstance(video, dict):
            normalized_videos.append({
                **video,
                "type": video.get("type") or "output",
                "subfolder": video.get("subfolder", ""),
                "filename": video.get("filename") or "",
                "format": video.get("format") or video.get("extension") or "mp4"
            })
        else:
            normalized_videos.append({
                "filename": str(video),
                "type": "output",
                "subfolder": "",
                "format": "mp4"
            })

    print(f"[VIDEO] Outputs for prompt {prompt_id}: {normalized_videos}")

    return {
        "success": True,
        "prompt_id": prompt_id,
        "client_id": client_id,
        "videos": normalized_videos
    }


def generate_image_edit(positive_prompt, source_image, width=None, height=None, steps=20, seed=None):
    """Editar una imagen existente usando el workflow de Qwen Image Edit"""
    if not source_image or not source_image.get('filename'):
        if not source_image or not source_image.get('data_url'):
            raise ValueError("No source image provided for edit mode")

    workflow = json.loads(json.dumps(EDIT_WORKFLOW))

    if source_image.get('data_url'):
        upload_name = upload_image_data_url_to_comfy(
            data_url=source_image.get('data_url'),
            filename=source_image.get('filename') or "upload.png",
            mime_type_override=source_image.get('mime_type')
        )
    elif (source_image.get('type') or '').lower() == 'local':
        upload_name = upload_local_media_to_comfy(
            source_image.get('local_path') or source_image.get('filename', '')
        )
    else:
        upload_name = upload_image_to_comfy(
            filename=source_image.get('filename', ''),
            subfolder=source_image.get('subfolder', ''),
            image_type=source_image.get('type', 'output')
        )

    if "78" in workflow:
        workflow["78"]["inputs"]["image"] = upload_name

    if "111" in workflow and "inputs" in workflow["111"]:
        workflow["111"]["inputs"]["prompt"] = positive_prompt or ""
    if "110" in workflow and "inputs" in workflow["110"]:
        workflow["110"]["inputs"]["prompt"] = ""

    if width is not None and height is not None:
        try:
            w = int(width)
            h = int(height)
            if "112" in workflow and "inputs" in workflow["112"]:
                workflow["112"]["inputs"]["width"] = w
                workflow["112"]["inputs"]["height"] = h
            megapixels = max((w * h) / 1_000_000, 0.1)
            if "93" in workflow and "inputs" in workflow["93"]:
                workflow["93"]["inputs"]["megapixels"] = round(megapixels, 2)
        except (ValueError, TypeError):
            pass

    steps_value = int(steps)
    seed_value = int(seed) if seed is not None else generate_random_seed()

    if "3" in workflow and "inputs" in workflow["3"]:
        workflow["3"]["inputs"]["steps"] = steps_value
        workflow["3"]["inputs"]["seed"] = seed_value

    client_id = str(uuid.uuid4())
    result = queue_prompt(workflow, client_id)
    prompt_id = result["prompt_id"]

    images = wait_for_completion(
        client_id,
        prompt_id,
        target_nodes=["60"],
        media_key="images"
    )

    if not images:
        raise ValueError("Edit workflow completed but returned no images")

    local_images = persist_media_locally(images, prompt_id, media_category="images")
    if not local_images:
        raise ValueError("No edited images were persisted locally.")

    return {
        "success": True,
        "prompt_id": prompt_id,
        "images": local_images,
        "client_id": client_id
    }


@app.route('/')
@login_required
def index():
    """Página principal con headers de no-caché"""
    html = render_template('index.html', user_email=session.get('user_email'))
    response = Response(html)
    # Agregar headers para evitar caché del navegador
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/video')
@login_required
def video_page():
    """Página para la generación de video"""
    filename = request.args.get('filename', '')
    subfolder = request.args.get('subfolder', '')
    image_type = request.args.get('type', 'output')
    prompt = request.args.get('prompt', '')
    resolution = request.args.get('resolution', '1024x1024')
    local_path = request.args.get('local_path', '')
    prompt_id = request.args.get('prompt_id', '')

    video_data = {
        "filename": filename,
        "subfolder": subfolder,
        "imageType": image_type,
        "prompt": prompt,
        "resolution": resolution,
        "localPath": local_path,
        "promptId": prompt_id,
    }

    return render_template('video.html', video_data=video_data, user_email=session.get('user_email'))

@app.route('/api/generate', methods=['POST'])
@api_login_required
def api_generate():
    """API endpoint para generar imágenes"""
    try:
        data = request.get_json()
        prompt = data.get('prompt', '').strip()
        width = data.get('width', 1024)
        height = data.get('height', 1024)
        steps = data.get('steps', 20)  # Por defecto 20 steps
        seed = data.get('seed', None)  # Seed opcional
        mode = (data.get('mode') or 'generate').strip().lower()
        if mode not in ('generate', 'edit'):
            return jsonify({"success": False, "error": "Invalid generation mode"}), 400
        
        if not prompt:
            return jsonify({"success": False, "error": "Empty prompt"}), 400
        
        # Validar dimensiones
        width = int(width)
        height = int(height)
        if width <= 0 or height <= 0:
            return jsonify({"success": False, "error": "Invalid dimensions"}), 400
        
        # Validar steps
        steps = int(steps)
        if steps <= 0:
            return jsonify({"success": False, "error": "Invalid steps"}), 400
        
        # Validar seed si se proporciona
        if seed is not None:
            try:
                seed = int(seed)
                if seed < 0 or seed >= 2**32:
                    return jsonify({"success": False, "error": "Invalid seed (must be 0-4294967295)"}), 400
            except (ValueError, TypeError):
                return jsonify({"success": False, "error": "Invalid seed format"}), 400
        
        if mode == 'generate':
            result = generate_images(prompt, width=width, height=height, steps=steps, seed=seed)
        else:
            source_image = data.get('image') or {}
            if not source_image.get('filename'):
                return jsonify({"success": False, "error": "No source image available for edit mode"}), 400
            result = generate_image_edit(
                positive_prompt=prompt,
                source_image=source_image,
                width=width,
                height=height,
                steps=steps,
                seed=seed
            )
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/upload-image', methods=['POST'])
@api_login_required
def api_upload_image():
    """Subir una imagen proporcionada por el usuario al backend de ComfyUI"""
    try:
        if 'image' not in request.files:
            return jsonify({"success": False, "error": "Image file not provided"}), 400

        image_file = request.files['image']
        if image_file.filename == '':
            return jsonify({"success": False, "error": "Invalid filename"}), 400

        file_data = image_file.read()
        if not file_data:
            return jsonify({"success": False, "error": "Empty file"}), 400

        original_name = secure_filename(image_file.filename) or "upload.png"
        extension = os.path.splitext(original_name)[1] or '.png'
        upload_name = f"user_upload_{uuid.uuid4().hex}{extension}"
        mime_type = image_file.mimetype or 'image/png'

        upload_response = requests.post(
            f"{COMFYUI_URL}/upload/image",
            data={'type': 'input', 'overwrite': 'true'},
            files={'image': (upload_name, file_data, mime_type)},
            timeout=60
        )

        if upload_response.status_code != 200:
            return jsonify({
                "success": False,
                "error": f"Unable to upload image to ComfyUI: HTTP {upload_response.status_code}"
            }), 500

        return jsonify({
            "success": True,
            "image": {
                "filename": upload_name,
                "subfolder": "input",
                "type": "input",
                "original_name": original_name
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/upload-image-data', methods=['POST'])
@api_login_required
def api_upload_image_data():
    """Subir una imagen recibida como data URL al backend de ComfyUI"""
    try:
        data = request.get_json(force=True, silent=False) or {}
        data_url = data.get('data_url')
        if not data_url:
            return jsonify({"success": False, "error": "Image data URL not provided"}), 400

        filename = secure_filename(data.get('filename') or "upload.png") or "upload.png"
        mime_type = data.get('mime_type')

        upload_name = upload_image_data_url_to_comfy(
            data_url=data_url,
            filename=filename,
            mime_type_override=mime_type
        )

        return jsonify({
            "success": True,
            "image": {
                "filename": upload_name,
                "subfolder": "input",
                "type": "input",
                "original_name": filename
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/settings/comfy-endpoint', methods=['GET', 'POST'])
@api_login_required
def api_comfy_endpoint_settings():
    """Obtener o actualizar el endpoint de ComfyUI en tiempo de ejecución."""
    if request.method == 'GET':
        return jsonify({"success": True, "url": COMFYUI_URL})

    data = request.get_json(silent=True) or {}
    candidate = (data.get('url') or '').strip()
    if not candidate:
        return jsonify({"success": False, "error": "Endpoint URL is required."}), 400

    formatted = candidate
    if '://' not in formatted:
        formatted = f"http://{formatted}"

    try:
        parsed = urlparse(formatted)
    except Exception:
        return jsonify({"success": False, "error": "Endpoint URL is invalid."}), 400

    if parsed.scheme not in {'http', 'https'}:
        return jsonify({"success": False, "error": "Endpoint URL must use http or https."}), 400
    if not parsed.netloc:
        return jsonify({"success": False, "error": "Endpoint URL is missing a host."}), 400

    sanitized = formatted.rstrip('/')
    try:
        apply_comfy_endpoint(sanitized)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    print(f"[Settings] ComfyUI endpoint updated to {COMFYUI_URL}")
    return jsonify({"success": True, "url": COMFYUI_URL})


@app.route('/api/generate-video', methods=['POST'])
@api_login_required
def api_generate_video():
    """API endpoint para generar videos a partir de una imagen"""
    try:
        data = request.get_json()
        prompt = (data.get('prompt') or '').strip()
        if not prompt:
            return jsonify({"success": False, "error": "Prompt is required"}), 400

        image_info = data.get('image') or {}
        if not image_info.get('filename'):
            if image_info.get('data_url'):
                try:
                    upload_name = upload_image_data_url_to_comfy(
                        data_url=image_info.get('data_url'),
                        filename=image_info.get('filename') or image_info.get('original_name') or "upload.png",
                        mime_type_override=image_info.get('mime_type')
                    )
                    image_info = {
                        "filename": upload_name,
                        "subfolder": "input",
                        "type": "input"
                    }
                except Exception as e:
                    return jsonify({"success": False, "error": f"Unable to upload source image: {e}"}), 500
            else:
                return jsonify({"success": False, "error": "Source image is required"}), 400

        width = data.get('width')
        height = data.get('height')

        negative_prompt = (data.get('negative_prompt') or '').strip() or None
        length = data.get('length')
        fps = data.get('fps')

        if width is not None:
            try:
                width = int(width)
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": "Invalid width"}), 400

        if height is not None:
            try:
                height = int(height)
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": "Invalid height"}), 400

        result = generate_video_from_image(
            positive_prompt=prompt,
            source_image=image_info,
            width=width,
            height=height,
            negative_prompt=negative_prompt,
            length=length,
            fps=fps
        )

        return jsonify(result)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/image/<filename>')
@api_login_required
def serve_image(filename):
    """Servir imágenes generadas desde almacenamiento local o ComfyUI."""
    try:
        subfolder = request.args.get('subfolder', '')
        raw_type = request.args.get('type', 'output') or 'output'
        image_type = raw_type.lower()
        download = request.args.get('download', '0') == '1'

        if image_type == 'local':
            try:
                local_path = resolve_local_media_path(filename)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

            if not os.path.exists(local_path):
                return jsonify({"error": f"Local file not found: {filename}"}), 404

            as_attachment = download
            guessed_mime = mimetypes.guess_type(local_path)[0]
            return send_from_directory(
                OUTPUT_DIR,
                os.path.basename(local_path),
                mimetype=guessed_mime,
                as_attachment=as_attachment,
            )

        # Siempre obtener la imagen desde el endpoint /view de ComfyUI
        try:
            params = {"filename": filename, "type": raw_type or 'output'}
            if subfolder:
                params["subfolder"] = subfolder
            format_param = request.args.get('format')
            if format_param:
                params["format"] = format_param

            print(f"[MEDIA] Proxying request to /view with params: {params}")

            response = requests.get(f"{COMFYUI_URL}/view", params=params, stream=True, timeout=30)
            if response.status_code == 200:
                from flask import Response
                return Response(
                    response.iter_content(chunk_size=8192),
                    content_type=response.headers.get('Content-Type', 'image/png'),
                    headers={'Content-Disposition': f'{"attachment" if download else "inline"}; filename="{filename}"'} if download else {}
                )
            else:
                print(f"Error getting image from ComfyUI: HTTP {response.status_code} for {filename}")
                return jsonify({"error": f"Image not found: {filename} (HTTP {response.status_code})"}), 404
        except Exception as e:
            print(f"Error getting image from ComfyUI: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Error fetching image from ComfyUI: {str(e)}"}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/status/<prompt_id>')
@api_login_required
def get_status(prompt_id):
    """Obtener estado de una generación"""
    if prompt_id in generation_status:
        return jsonify(generation_status[prompt_id])
    return jsonify({"error": "Prompt ID not found"}), 404

@app.route('/api/convert-to-natural-language', methods=['POST'])
@api_login_required
def convert_to_natural_language():
    """Convertir prompt de tags a lenguaje natural usando OpenAI GPT-4o"""
    try:
        data = request.get_json()
        tags_prompt = data.get('prompt', '').strip()
        
        print(f"[DEBUG] convert-to-natural-language called with tags prompt: '{tags_prompt[:100]}...'")
        
        if not tags_prompt:
            return jsonify({"success": False, "error": "Empty prompt"}), 400
        
        # Obtener API key de OpenAI desde variable de entorno
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        print(f"[DEBUG] OPENAI_API_KEY exists: {bool(openai_api_key)}, length: {len(openai_api_key) if openai_api_key else 0}")
        if not openai_api_key:
            return jsonify({"success": False, "error": "OPENAI_API_KEY not configured"}), 500
        
        # System prompt para convertir tags a lenguaje natural
        system_prompt = (
            "You are an expert AI art prompt engineer. I will provide you with a prompt composed of danbooru tags and other AI art tags. "
            "Your task is to convert this tag-based prompt into a detailed, natural language description that is rich, descriptive, and flows naturally. "
            "Write it as if you were describing the scene to another artist in natural, flowing English. "
            "Make it detailed, vivid, and evocative while preserving all the important information from the tags. "
            "Do not use tag format or comma-separated lists. Write in complete sentences with proper grammar. "
            "The output should be a cohesive paragraph or paragraphs that describe the image in natural language."
        )
        
        # Llamar a OpenAI API
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_api_key}"
        }
        
        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Convert the following tag-based prompt to natural language:\n\n{tags_prompt}"}
            ],
            "temperature": 0.7,
            "max_tokens": 800
        }
        
        print(f"[DEBUG] Calling OpenAI API to convert tags to natural language")
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        print(f"[DEBUG] OpenAI API response status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            natural_language_prompt = result["choices"][0]["message"]["content"].strip()
            print(f"[DEBUG] Natural language prompt received: '{natural_language_prompt[:100]}...'")
            return jsonify({
                "success": True,
                "natural_language_prompt": natural_language_prompt
            })
        else:
            error_msg = response.text
            print(f"[DEBUG] OpenAI API error: {response.status_code} - {error_msg}")
            return jsonify({
                "success": False,
                "error": f"OpenAI API error: {response.status_code} - {error_msg}"
            }), 500
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"Error converting to natural language: {str(e)}"
        }), 500

@app.route('/api/improve-prompt', methods=['POST'])
@api_login_required
def improve_prompt():
    """Mejorar prompt usando OpenAI GPT-4o"""
    try:
        data = request.get_json()
        user_prompt = data.get('prompt', '').strip()
        step_name = data.get('step_name', '')
        
        print(f"[DEBUG] improve-prompt called with prompt: '{user_prompt}', step: '{step_name}'")
        
        if not user_prompt:
            return jsonify({"success": False, "error": "Empty prompt"}), 400
        
        # Obtener API key de OpenAI desde variable de entorno
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        print(f"[DEBUG] OPENAI_API_KEY exists: {bool(openai_api_key)}, length: {len(openai_api_key) if openai_api_key else 0}")
        if not openai_api_key:
            return jsonify({"success": False, "error": "OPENAI_API_KEY not configured"}), 500
        
        # Construir system prompt con el nombre del paso (según especificación del usuario)
        # Importante: el usuario enviará un prompt completo concatenado, pero debemos responder solo con tags para el paso actual
        system_prompt = (
            f"You are an artist who excels at creating AI paintings using the Lumina model and can craft high-quality Lumina prompts. "
            f"I want to use AI for my creative process. I will provide you with a complete prompt that has been built step by step. "
            f"You need to refine ONLY the <{step_name}> part of it. Even though you will see the full prompt, you must respond ONLY with tags for the <{step_name}> step. "
            f"Reply ONLY with tags separated by comma for the {step_name} step. Use danbooru tags. If you have to refer to an author, use @ followed by his name, example @gemart. "
            f"Do NOT include tags from other steps, only the tags relevant to <{step_name}>."
        )
        
        # Llamar a OpenAI API
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_api_key}"
        }
        
        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        print(f"[DEBUG] Calling OpenAI API with model: gpt-4o")
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        print(f"[DEBUG] OpenAI API response status: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            improved_prompt = result["choices"][0]["message"]["content"].strip()
            print(f"[DEBUG] Improved prompt received: '{improved_prompt[:100]}...'")
            return jsonify({
                "success": True,
                "improved_prompt": improved_prompt
            })
        else:
            error_msg = response.text
            print(f"[DEBUG] OpenAI API error: {response.status_code} - {error_msg}")
            return jsonify({
                "success": False,
                "error": f"OpenAI API error: {response.status_code} - {error_msg}"
            }), 500
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"Error improving prompt: {str(e)}"
        }), 500

@app.route('/api/tags/<category>')
@api_login_required
def get_tags(category):
    """Obtener tags filtrados por categoría"""
    try:
        # Cargar cache si no está cargado
        load_tags_cache()
        
        # Las categorías en el CSV coinciden directamente con los nombres de los pasos
        if category == 'Natural-language enrichment':
            return jsonify({"success": True, "tags": []})
        
        csv_category = category
        
        if not csv_category:
            return jsonify({"success": True, "tags": []})
        
        # Obtener tags ya mostrados de los parámetros de la petición
        excluded_tags = request.args.get('excluded', '').split(',')
        excluded_tags = [tag.strip() for tag in excluded_tags if tag.strip()]
        excluded_set = set(excluded_tags)  # Usar set para búsqueda O(1)
        
        # Obtener tags de la categoría desde el cache
        if csv_category not in TAGS_CACHE:
            return jsonify({"success": True, "tags": []})
        
        # Filtrar tags excluidos (ya están ordenados por post_count)
        tags = [
            tag for tag in TAGS_CACHE[csv_category]
            if tag['name'] not in excluded_set
        ]
        
        # Limitar a 40 tags (ya están ordenados por post_count)
        tags = tags[:40]
        
        return jsonify({
            "success": True,
            "tags": [tag['name'] for tag in tags]
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    # Cargar tags al iniciar la aplicación
    load_tags_cache()
    
    port = int(os.environ.get('ANIME_GENERATOR_PORT', 5000))
    host = os.environ.get('ANIME_GENERATOR_HOST', '0.0.0.0')
    print(f"Iniciando Generador de Anime en {host}:{port}")
    print(f"Conectando a ComfyUI en {COMFYUI_URL}")
    app.run(host=host, port=port, debug=False)
