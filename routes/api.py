"""
General API routes (tags, settings, upload, image serving, OpenAI integration)
"""
import os
import csv
import time
import uuid
import requests
import traceback
import mimetypes
from flask import Blueprint, request, jsonify, send_file, Response
from werkzeug.utils import secure_filename
from utils.comfy_config import get_comfy_url, update_comfy_endpoint, get_all_endpoints, build_comfy_headers
from utils.media import resolve_local_media_path, upload_image_data_url_to_comfy, upload_image_bytes_to_comfy
from utils.google_drive import get_authorization_url, exchange_code_for_credentials, get_drive_service, upload_file_to_drive
from auth import api_login_required
from urllib.parse import urlparse
from config import SCRIPT_DIR, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL, PREFERRED_URL_SCHEME

# Cache de tags en memoria
TAGS_CACHE = {}
TAGS_CACHE_LOADED = False

def load_tags_cache():
    """Cargar todos los tags en memoria organizados por categoría"""
    global TAGS_CACHE, TAGS_CACHE_LOADED
    
    if TAGS_CACHE_LOADED:
        return
    
    csv_path = os.path.join(SCRIPT_DIR, 'data', 'tags.csv')
    
    if not os.path.exists(csv_path):
        print(f"Warning: Tags file not found at {csv_path}")
        TAGS_CACHE_LOADED = True
        return
    
    print("Loading tags into memory...")
    start_time = time.time()
    
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
    
    for category in tags_by_category:
        tags_by_category[category].sort(key=lambda x: x['post_count'], reverse=True)
    
    TAGS_CACHE = tags_by_category
    TAGS_CACHE_LOADED = True
    
    elapsed = time.time() - start_time
    total_tags = sum(len(tags) for tags in TAGS_CACHE.values())
    print(f"Loaded {total_tags} tags in {elapsed:.2f} seconds ({len(TAGS_CACHE)} categories)")

# Almacenar estados de generación
generation_status = {}

def create_api_blueprint(app):
    """Crear blueprint de API general"""
    api_bp = Blueprint('api', __name__)

    @api_bp.route('/api/upload-image', methods=['POST'])
    @api_login_required(app)
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

            comfy_url = get_comfy_url('generate')
            upload_response = requests.post(
                f"{comfy_url}/upload/image",
                data={'type': 'input', 'overwrite': 'true'},
                files={'image': (upload_name, file_data, mime_type)},
                headers=build_comfy_headers()
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

    @api_bp.route('/api/upload-image-data', methods=['POST'])
    @api_login_required(app)
    def api_upload_image_data():
        """Subir una imagen recibida como data URL al backend de ComfyUI"""
        try:
            data = request.get_json(force=True, silent=False) or {}
            data_url = data.get('data_url')
            if not data_url:
                return jsonify({"success": False, "error": "Image data URL not provided"}), 400

            filename = secure_filename(data.get('filename') or "upload.png") or "upload.png"
            mime_type = data.get('mime_type')
            mode = data.get('mode', 'generate')
            image_type = data.get('image_type', 'input')  # Por defecto 'input', pero puede ser 'output' para modo edit

            # Si se especificó image_type diferente de 'input', subir directamente con ese tipo
            if image_type != 'input':
                from utils.media import upload_image_bytes_to_comfy
                import base64
                # Extraer los bytes del data_url
                header, encoded = data_url.split(',', 1)
                content_bytes = base64.b64decode(encoded)
                # Subir con el tipo especificado
                upload_name = upload_image_bytes_to_comfy(
                    content_bytes=content_bytes,
                    filename=filename,
                    mime_type=mime_type or 'image/png',
                    image_type=image_type,
                    mode=mode
                )
            else:
                # Subir con el método normal (a 'input')
                upload_name = upload_image_data_url_to_comfy(
                    data_url=data_url,
                    filename=filename,
                    mime_type_override=mime_type,
                    mode=mode
                )

            return jsonify({
                "success": True,
                "image": {
                    "filename": upload_name,
                    "subfolder": image_type,
                    "type": image_type,
                    "original_name": filename
                }
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @api_bp.route('/api/settings/comfy-endpoint', methods=['GET', 'POST'])
    @api_login_required(app)
    def api_comfy_endpoint_settings():
        """Obtener o actualizar los endpoints de ComfyUI en tiempo de ejecución."""
        if request.method == 'GET':
            endpoints = get_all_endpoints()
            return jsonify({
                "success": True,
                **endpoints
            })

        data = request.get_json(silent=True) or {}
        
        # Aceptar cualquier valor que venga, sin validar
        updated_endpoints = {}
        errors = []
        
        # Actualizar endpoint de generate si está presente (aceptar cualquier valor, incluso vacío)
        if 'generate' in data:
            try:
                url_value = data.get('generate', '') or ''
                update_comfy_endpoint('generate', url_value)
                endpoints = get_all_endpoints()
                updated_endpoints['generate'] = endpoints['generate']
                updated_endpoints['url'] = endpoints['url']  # Compatibilidad
            except Exception as e:
                errors.append(f"Error updating generate endpoint: {str(e)}")
        elif 'url' in data:
            # Compatibilidad hacia atrás: 'url' actualiza 'generate'
            try:
                url_value = data.get('url', '') or ''
                update_comfy_endpoint('generate', url_value)
                endpoints = get_all_endpoints()
                updated_endpoints['generate'] = endpoints['generate']
                updated_endpoints['url'] = endpoints['url']  # Compatibilidad
            except Exception as e:
                errors.append(f"Error updating generate endpoint: {str(e)}")
        
        # Actualizar endpoint de edit si está presente (aceptar cualquier valor, incluso vacío)
        if 'edit' in data:
            try:
                url_value = data.get('edit', '') or ''
                update_comfy_endpoint('edit', url_value)
                endpoints = get_all_endpoints()
                updated_endpoints['edit'] = endpoints['edit']
            except Exception as e:
                errors.append(f"Error updating edit endpoint: {str(e)}")
        
        # Actualizar endpoint de video si está presente (aceptar cualquier valor, incluso vacío)
        if 'video' in data:
            try:
                url_value = data.get('video', '') or ''
                update_comfy_endpoint('video', url_value)
                endpoints = get_all_endpoints()
                updated_endpoints['video'] = endpoints['video']
            except Exception as e:
                errors.append(f"Error updating video endpoint: {str(e)}")
        
        # Solo retornar error si hubo excepciones al actualizar
        if errors:
            return jsonify({
                "success": False,
                "error": "; ".join(errors),
                "updated": updated_endpoints
            }), 400
        
        # Retornar todos los endpoints actualizados
        endpoints = get_all_endpoints()
        return jsonify({
            "success": True,
            **endpoints,
            "updated": updated_endpoints
        })

    @api_bp.route('/api/image/<filename>')
    @api_login_required(app)
    def serve_image(filename):
        """Servir imágenes generadas desde almacenamiento local o ComfyUI."""
        try:
            subfolder = request.args.get('subfolder', '')
            raw_type = request.args.get('type', 'output') or 'output'
            image_type = raw_type.lower()
            download = request.args.get('download', '0') == '1'
            
            if image_type == 'local':
                local_override = request.args.get('local_path') or filename
                try:
                    local_path = resolve_local_media_path(local_override)
                except ValueError as exc:
                    return jsonify({"error": str(exc)}), 400

                if not os.path.exists(local_path):
                    return jsonify({"error": f"Local file not found: {filename}"}), 404

                as_attachment = download
                guessed_mime = mimetypes.guess_type(local_path)[0]
                return send_file(
                    local_path,
                    mimetype=guessed_mime,
                    as_attachment=as_attachment,
                    download_name=os.path.basename(local_path),
                )

            try:
                params = {"filename": filename, "type": raw_type or 'output'}
                if subfolder:
                    params["subfolder"] = subfolder
                format_param = request.args.get('format')
                if format_param:
                    params["format"] = format_param

                print(f"[MEDIA] Proxying request to /view with params: {params}")

                comfy_url = get_comfy_url('generate')
                response = requests.get(
                    f"{comfy_url}/view",
                    params=params,
                    headers=build_comfy_headers(),
                    stream=True
                )
                if response.status_code == 200:
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
                traceback.print_exc()
                return jsonify({"error": f"Error fetching image from ComfyUI: {str(e)}"}), 500
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

    @api_bp.route('/api/status/<prompt_id>')
    @api_login_required(app)
    def get_status(prompt_id):
        """Obtener estado de una generación"""
        if prompt_id in generation_status:
            return jsonify(generation_status[prompt_id])
        return jsonify({"error": "Prompt ID not found"}), 404

    @api_bp.route('/api/convert-to-natural-language', methods=['POST'])
    @api_login_required(app)
    def convert_to_natural_language():
        """Convertir prompt de tags a lenguaje natural usando OpenAI GPT-4o"""
        try:
            data = request.get_json()
            tags_prompt = data.get('prompt', '').strip()
            
            print(f"[DEBUG] convert-to-natural-language called with tags prompt: '{tags_prompt[:100]}...'")
            
            if not tags_prompt:
                return jsonify({"success": False, "error": "Empty prompt"}), 400
            
            if not OPENAI_API_KEY:
                print(f"[DEBUG] OPENAI_API_KEY not configured")
                return jsonify({"success": False, "error": "OPENAI_API_KEY not configured"}), 500
            
            print(f"[DEBUG] OPENAI_API_KEY exists: {bool(OPENAI_API_KEY)}, length: {len(OPENAI_API_KEY) if OPENAI_API_KEY else 0}")
            
            system_prompt = (
                "You are an expert AI art prompt engineer. I will provide you with a prompt composed of danbooru tags and other AI art tags. "
                "Your task is to convert this tag-based prompt into a detailed, natural language description that is rich, descriptive, and flows naturally. "
                "Write it as if you were describing the scene to another artist in natural, flowing English. "
                "Make it detailed, vivid, and evocative while preserving all the important information from the tags. "
                "Do not use tag format or comma-separated lists. Write in complete sentences with proper grammar. "
                "The output should be a cohesive paragraph or paragraphs that describe the image in natural language."
            )
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}"
            }
            
            payload = {
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Convert the following tag-based prompt to natural language:\n\n{tags_prompt}"}
                ],
                "temperature": 0.7,
                "max_tokens": 800
            }
            
            api_url = f"{OPENAI_API_BASE.rstrip('/')}/chat/completions"
            print(f"[DEBUG] Calling OpenAI API to convert tags to natural language with model: {OPENAI_MODEL} at {api_url}")
            response = requests.post(
                api_url,
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
            traceback.print_exc()
            return jsonify({
                "success": False,
                "error": f"Error converting to natural language: {str(e)}"
            }), 500

    @api_bp.route('/api/improve-prompt', methods=['POST'])
    @api_login_required(app)
    def improve_prompt():
        """Mejorar prompt usando OpenAI GPT-4o"""
        try:
            data = request.get_json()
            user_prompt = data.get('prompt', '').strip()
            step_name = data.get('step_name', '')
            
            print(f"[DEBUG] improve-prompt called with prompt: '{user_prompt}', step: '{step_name}'")
            
            if not user_prompt:
                return jsonify({"success": False, "error": "Empty prompt"}), 400
            
            if not OPENAI_API_KEY:
                print(f"[DEBUG] OPENAI_API_KEY not configured")
                return jsonify({"success": False, "error": "OPENAI_API_KEY not configured"}), 500
            
            print(f"[DEBUG] OPENAI_API_KEY exists: {bool(OPENAI_API_KEY)}, length: {len(OPENAI_API_KEY) if OPENAI_API_KEY else 0}")
            
            system_prompt = (
                f"You are an artist who excels at creating AI paintings using the Lumina model and can craft high-quality Lumina prompts. "
                f"I want to use AI for my creative process. I will provide you with a complete prompt that has been built step by step. "
                f"You need to refine ONLY the <{step_name}> part of it. Even though you will see the full prompt, you must respond ONLY with tags for the <{step_name}> step. "
                f"Reply ONLY with tags separated by comma for the {step_name} step. Use danbooru tags. If you have to refer to an author, use @ followed by his name, example @gemart. "
                f"Do NOT include tags from other steps, only the tags relevant to <{step_name}>."
            )
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}"
            }
            
            payload = {
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            api_url = f"{OPENAI_API_BASE.rstrip('/')}/chat/completions"
            print(f"[DEBUG] Calling OpenAI API with model: {OPENAI_MODEL} at {api_url}")
            response = requests.post(
                api_url,
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
            traceback.print_exc()
            return jsonify({
                "success": False,
                "error": f"Error improving prompt: {str(e)}"
            }), 500

    @api_bp.route('/api/tags/<category>')
    @api_login_required(app)
    def get_tags(category):
        """Obtener tags filtrados por categoría"""
        try:
            load_tags_cache()
            
            if category == 'Natural-language enrichment':
                return jsonify({"success": True, "tags": []})
            
            csv_category = category
            
            if not csv_category:
                return jsonify({"success": True, "tags": []})
            
            excluded_tags = request.args.get('excluded', '').split(',')
            excluded_tags = [tag.strip() for tag in excluded_tags if tag.strip()]
            excluded_set = set(excluded_tags)
            
            if csv_category not in TAGS_CACHE:
                return jsonify({"success": True, "tags": []})
            
            tags = [
                tag for tag in TAGS_CACHE[csv_category]
                if tag['name'] not in excluded_set
            ]
            
            tags = tags[:40]
            
            return jsonify({
                "success": True,
                "tags": [tag['name'] for tag in tags]
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @api_bp.route('/api/drive/authorize', methods=['GET'])
    @api_login_required(app)
    def api_drive_authorize():
        """Obtener URL de autorización para Google Drive"""
        try:
            if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
                return jsonify({
                    "success": False,
                    "error": "Google Drive is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
                }), 503
            
            # Construir redirect URI usando el esquema preferido
            from flask import url_for
            # Si es localhost, forzar http; de lo contrario usar el esquema preferido
            host = request.host
            if 'localhost' in host or '127.0.0.1' in host:
                scheme = 'http'
            else:
                scheme = PREFERRED_URL_SCHEME or request.scheme
            
            redirect_uri = url_for('api.api_drive_callback', _external=True, _scheme=scheme)
            
            print(f"[GOOGLE_DRIVE] Host: {host}")
            print(f"[GOOGLE_DRIVE] Scheme: {scheme}")
            print(f"[GOOGLE_DRIVE] Redirect URI: {redirect_uri}")
            print(f"[GOOGLE_DRIVE] Client ID: {GOOGLE_CLIENT_ID}")
            print(f"[GOOGLE_DRIVE] Make sure this exact URI is registered in Google Cloud Console")
            
            authorization_url, state = get_authorization_url(
                redirect_uri=redirect_uri,
                client_id=GOOGLE_CLIENT_ID,
                client_secret=GOOGLE_CLIENT_SECRET
            )
            
            if not authorization_url:
                return jsonify({
                    "success": False,
                    "error": "Failed to generate authorization URL. Check server logs for details."
                }), 500
            
            from flask import session
            session['drive_oauth_state'] = state
            
            return jsonify({
                "success": True,
                "authorization_url": authorization_url,
                "redirect_uri": redirect_uri  # Incluir para debugging
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @api_bp.route('/api/drive/callback', methods=['GET'])
    @api_login_required(app)
    def api_drive_callback():
        """Callback de autorización de Google Drive"""
        try:
            from flask import session, redirect, url_for
            code = request.args.get('code')
            state = request.args.get('state')
            
            if not code:
                return jsonify({
                    "success": False,
                    "error": "Authorization code not provided"
                }), 400
            
            if state != session.get('drive_oauth_state'):
                return jsonify({
                    "success": False,
                    "error": "Invalid state parameter"
                }), 400
            
            # Construir redirect URI usando el mismo método que en authorize
            host = request.host
            if 'localhost' in host or '127.0.0.1' in host:
                scheme = 'http'
            else:
                scheme = PREFERRED_URL_SCHEME or request.scheme
            
            redirect_uri = url_for('api.api_drive_callback', _external=True, _scheme=scheme)
            
            print(f"[GOOGLE_DRIVE] Callback - Host: {host}, Scheme: {scheme}")
            print(f"[GOOGLE_DRIVE] Callback redirect URI: {redirect_uri}")
            
            granted_scopes_param = request.args.get('scope')
            granted_scopes = granted_scopes_param.split(' ') if granted_scopes_param else None
            if granted_scopes:
                print(f"[GOOGLE_DRIVE] Granted scopes from callback: {granted_scopes}")
            
            credentials = exchange_code_for_credentials(
                code=code,
                redirect_uri=redirect_uri,
                client_id=GOOGLE_CLIENT_ID,
                client_secret=GOOGLE_CLIENT_SECRET,
                scopes=granted_scopes
            )
            
            if not credentials:
                return jsonify({
                    "success": False,
                    "error": "Failed to exchange authorization code"
                }), 500
            
            # Guardar credenciales en la sesión
            session['drive_credentials'] = credentials
            session.pop('drive_oauth_state', None)
            
            # Redirigir a la página principal con mensaje de éxito
            return redirect('/?drive_auth=success')
        except Exception as e:
            traceback.print_exc()
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @api_bp.route('/api/drive/upload', methods=['POST'])
    @api_login_required(app)
    def api_drive_upload():
        """Subir un archivo a Google Drive"""
        try:
            from flask import session
            data = request.get_json()
            
            # Verificar credenciales
            credentials = session.get('drive_credentials')
            if not credentials:
                return jsonify({
                    "success": False,
                    "error": "Not authenticated with Google Drive. Please authorize first.",
                    "requires_auth": True
                }), 401
            
            # Obtener información del archivo
            file_url = data.get('file_url')
            filename = data.get('filename', 'uploaded_file')
            mime_type = data.get('mime_type', 'application/octet-stream')
            folder_id = data.get('folder_id')  # Opcional
            
            if not file_url:
                return jsonify({
                    "success": False,
                    "error": "file_url is required"
                }), 400
            
            # Normalizar URL para soportar rutas relativas del backend
            if file_url.startswith('/'):
                file_url = urljoin(request.host_url, file_url.lstrip('/'))
            else:
                parsed_url = urlparse(file_url)
                if not parsed_url.scheme:
                    file_url = urljoin(request.host_url, file_url)
            
            # Descargar el archivo
            # Si es un data URL, decodificarlo directamente
            if file_url.startswith('data:'):
                import base64
                try:
                    header, encoded = file_url.split(',', 1)
                    file_content = base64.b64decode(encoded)
                except Exception as e:
                    return jsonify({
                        "success": False,
                        "error": f"Failed to decode data URL: {str(e)}"
                    }), 400
            else:
                # Si es una URL normal, descargarla
                response = requests.get(file_url, stream=True)
                if response.status_code != 200:
                    return jsonify({
                        "success": False,
                        "error": f"Failed to download file: HTTP {response.status_code}"
                    }), 500
                
                file_content = response.content
            
            # Crear servicio de Drive
            service = get_drive_service(credentials)
            if not service:
                return jsonify({
                    "success": False,
                    "error": "Failed to create Google Drive service",
                    "requires_auth": True
                }), 500
            
            # Subir archivo
            result = upload_file_to_drive(
                service=service,
                file_content=file_content,
                filename=filename,
                mime_type=mime_type,
                folder_id=folder_id
            )
            
            if result.get('success'):
                return jsonify({
                    "success": True,
                    "file_id": result.get('file_id'),
                    "file_name": result.get('file_name'),
                    "web_view_link": result.get('web_view_link')
                })
            else:
                return jsonify({
                    "success": False,
                    "error": result.get('error', 'Unknown error')
                }), 500
                
        except Exception as e:
            traceback.print_exc()
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @api_bp.route('/api/drive/status', methods=['GET'])
    @api_login_required(app)
    def api_drive_status():
        """Verificar estado de autenticación con Google Drive"""
        try:
            from flask import session
            credentials = session.get('drive_credentials')
            return jsonify({
                "success": True,
                "authenticated": credentials is not None
            })
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @api_bp.route('/api/models', methods=['GET'])
    @api_login_required(app)
    def get_models():
        """Endpoint to get available models from ComfyUI directories."""
        base_path = '/app/ComfyUI/models'
        checkpoints_path = os.path.join(base_path, 'checkpoints')
        loras_path = os.path.join(base_path, 'loras')

        try:
            checkpoints = [f for f in os.listdir(checkpoints_path) if os.path.isfile(os.path.join(checkpoints_path, f))] if os.path.exists(checkpoints_path) else []
            loras = [f for f in os.listdir(loras_path) if os.path.isfile(os.path.join(loras_path, f))] if os.path.exists(loras_path) else []

            return jsonify({
                'success': True,
                'models': {
                    'checkpoints': checkpoints,
                    'loras': loras
                }
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({'success': False, 'error': 'Could not read model directories.'}), 500

    return api_bp

