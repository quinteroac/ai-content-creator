"""
Media handling utilities
Functions for uploading, downloading, and managing media files
"""
import os
import uuid
import base64
import mimetypes
import requests
from werkzeug.utils import secure_filename
from config import OUTPUT_DIR
from utils.comfy_config import get_comfy_url, build_comfy_headers

def resolve_local_media_path(relative_path):
    """Resolver la ruta absoluta de un archivo guardado en el directorio local de salida."""
    if not relative_path:
        raise ValueError("Local filename is required")

    if os.path.isabs(relative_path):
        raise ValueError("Invalid local filename")

    normalized = os.path.normpath(relative_path).replace("\\", "/")
    if normalized.startswith(".."):
        raise ValueError("Invalid local filename")

    output_root = os.path.abspath(OUTPUT_DIR)
    candidate_path = os.path.abspath(os.path.join(OUTPUT_DIR, normalized))
    if not candidate_path.startswith(output_root):
        raise ValueError("Local filename resolves outside of output directory")
    return candidate_path

def upload_image_to_comfy(filename, subfolder='', image_type='output', mode='generate'):
    """Descargar una imagen desde ComfyUI y subirla al directorio de inputs"""
    comfy_url = get_comfy_url(mode)
    params = {
        'filename': filename,
        'type': image_type or 'output'
    }
    if subfolder:
        params['subfolder'] = subfolder

    response = requests.get(
        f"{comfy_url}/view",
        params=params,
        headers=build_comfy_headers()
    )
    if response.status_code != 200:
        raise ValueError(f"Unable to retrieve source image: HTTP {response.status_code}")

    content_type = response.headers.get('Content-Type', 'image/png')
    extension = os.path.splitext(filename)[1] or '.png'
    upload_name = f"video_source_{uuid.uuid4().hex}{extension}"

    upload_response = requests.post(
        f"{comfy_url}/upload/image",
        data={'type': 'input', 'overwrite': 'true'},
        files={'image': (upload_name, response.content, content_type)},
        headers=build_comfy_headers()
    )

    if upload_response.status_code != 200:
        raise ValueError(f"Unable to upload source image: HTTP {upload_response.status_code}")

    return upload_name

def upload_image_bytes_to_comfy(content_bytes, filename='upload.png', mime_type='image/png', image_type='input', mode='generate'):
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
    
    comfy_url = get_comfy_url(mode)
    upload_response = requests.post(
        f"{comfy_url}/upload/image",
        data={'type': image_type, 'overwrite': 'true'},
        files={'image': (upload_name, content_bytes, mime_type or 'image/png')},
        headers=build_comfy_headers()
    )

    if upload_response.status_code != 200:
        raise ValueError(f"Unable to upload provided image: HTTP {upload_response.status_code}")

    return upload_name

def upload_image_data_url_to_comfy(data_url, filename='upload.png', mime_type_override=None, mode='generate'):
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

    return upload_image_bytes_to_comfy(content_bytes, filename=filename, mime_type=mime_type, image_type='input', mode=mode)

def upload_local_media_to_comfy(local_filename, mode='generate'):
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
        mode=mode
    )

def persist_media_locally(media_items, prompt_id, media_category="images", mode='generate'):
    """Descargar archivos generados desde ComfyUI y guardarlos en el directorio local."""
    if not media_items:
        return []

    saved_items = []
    output_root = os.path.abspath(OUTPUT_DIR)
    media_subdir = "videos" if media_category == "videos" else "images"
    target_dir = os.path.join(output_root, media_subdir)
    os.makedirs(target_dir, exist_ok=True)
    
    comfy_url = get_comfy_url(mode)

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
            f"{comfy_url}/view",
            params=params,
            headers=build_comfy_headers(),
            stream=True
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
        local_path = os.path.join(target_dir, local_filename)
        relative_path = os.path.join(media_subdir, local_filename).replace("\\", "/")

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
            "local_path": relative_path,
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
        elif media_category == "videos":
            media_record["format"] = "mp4"

        saved_items.append(media_record)

    return saved_items

