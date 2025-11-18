#!/usr/bin/env python3
"""
Aplicación Web para Generación Iterativa de Imágenes de Anime
Utiliza ComfyUI para generar imágenes basadas en prompts iterativos
"""
from flask import Flask, render_template, Response, session
from flask_cors import CORS
from authlib.integrations.flask_client import OAuth
from config import (
    FLASK_SECRET_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
    PREFERRED_URL_SCHEME, ENABLE_OAUTH_LOGIN, ANIME_GENERATOR_PORT, ANIME_GENERATOR_HOST
)
from auth import login_required, is_authenticated
from routes.auth import create_auth_blueprint
from routes.generate import create_generate_blueprint
from routes.video import create_video_blueprint
from routes.api import create_api_blueprint, load_tags_cache
from routes.social_routes import create_social_blueprint
from utils.comfy_config import COMFYUI_URL_GENERATE, COMFYUI_URL_EDIT, COMFYUI_URL_VIDEO

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = FLASK_SECRET_KEY
app.config['GOOGLE_CLIENT_ID'] = GOOGLE_CLIENT_ID
app.config['GOOGLE_CLIENT_SECRET'] = GOOGLE_CLIENT_SECRET
app.config['PREFERRED_URL_SCHEME'] = PREFERRED_URL_SCHEME
app.config['ENABLE_OAUTH_LOGIN'] = ENABLE_OAUTH_LOGIN
app.config['TOTP_ISSUER'] = 'AI Content Creator'

# Setup OAuth
oauth = OAuth(app)
if ENABLE_OAUTH_LOGIN:
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
        oauth.register(
            name='google',
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'},
        )
    else:
        print("Warning: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured for Google login.")
else:
    print("OAuth login disabled via ENABLE_OAUTH_LOGIN.")

# Register blueprints
app.register_blueprint(create_auth_blueprint(app, oauth))
app.register_blueprint(create_generate_blueprint(app))
app.register_blueprint(create_video_blueprint(app))
app.register_blueprint(create_api_blueprint(app))
app.register_blueprint(create_social_blueprint(app))

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

@app.route('/')
@login_required(app)
def index():
    """Página principal con headers de no-caché"""
    html = render_template('index.html', user_email=session.get('user_email'))
    response = Response(html)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

if __name__ == '__main__':
    # Cargar tags al iniciar la aplicación
    load_tags_cache()
    
    print(f"Iniciando Generador de Anime en {ANIME_GENERATOR_HOST}:{ANIME_GENERATOR_PORT}")
    print(f"Conectando a ComfyUI:")
    print(f"  - Generate: {COMFYUI_URL_GENERATE}")
    print(f"  - Edit: {COMFYUI_URL_EDIT}")
    print(f"  - Video: {COMFYUI_URL_VIDEO}")
    app.run(host=ANIME_GENERATOR_HOST, port=ANIME_GENERATOR_PORT, debug=False)

