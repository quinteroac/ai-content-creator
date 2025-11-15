"""
Domain logic for video generation (image-to-video)
"""
import json
import uuid
import requests
from utils.workflow import VIDEO_WORKFLOW, load_workflow, find_video_output_nodes
from utils.comfy import queue_prompt, wait_for_completion
from utils.media import persist_media_locally, upload_image_data_url_to_comfy, upload_local_media_to_comfy, upload_image_to_comfy
from utils.comfy_config import get_comfy_url, build_comfy_headers
from config import VIDEO_WORKFLOW_PATH

def generate_video_from_image(positive_prompt, source_image, width=None, height=None, negative_prompt=None, length=None, fps=None, nsfw=False, no_sound=False):
    """Generar un video a partir de una imagen usando ComfyUI"""
    # Seleccionar workflow según NSFW y no_sound
    # NSFW tiene prioridad sobre no_sound
    if nsfw:
        workflow_path = 'workflows/image-to-video/video_wan2_2_14B_i2v_remix_sound_nsfw.json'
        print(f"[VIDEO] Using NSFW workflow: {workflow_path}")
    elif no_sound:
        workflow_path = 'workflows/image-to-video/video_wan2_2_14B_i2v_remix.json'
        print(f"[VIDEO] Using no-sound workflow: {workflow_path}")
    else:
        workflow_path = 'workflows/image-to-video/video_wan2_2_14B_i2v_remix_sound.json'
        print(f"[VIDEO] Using standard workflow with sound: {workflow_path}")
    
    workflow = load_workflow(VIDEO_WORKFLOW_PATH, workflow_path)
    if not workflow:
        raise ValueError(f"Video workflow could not be loaded: {workflow_path}")

    workflow = json.loads(json.dumps(workflow))

    # Extraer prompt de audio del prompt principal
    # Buscar "Audio:" y tomar lo que está después
    video_prompt = positive_prompt
    audio_prompt = ""
    
    if "Audio:" in positive_prompt:
        parts = positive_prompt.split("Audio:", 1)
        video_prompt = parts[0].strip()
        if len(parts) > 1:
            audio_prompt = parts[1].strip()
        print(f"[VIDEO] Extracted video prompt: {video_prompt[:100]}...")
        print(f"[VIDEO] Extracted audio prompt: {audio_prompt[:100] if audio_prompt else 'None'}...")
    else:
        print(f"[VIDEO] No 'Audio:' found in prompt, using full prompt for video only")

    # Actualizar prompt de video (nodo 93)
    if "93" in workflow:
        workflow["93"]["inputs"]["text"] = video_prompt

    # Actualizar prompt de audio (nodo 115 - MMAudioSampler) solo si el workflow tiene sonido
    if audio_prompt and "115" in workflow and not no_sound:
        workflow["115"]["inputs"]["prompt"] = audio_prompt
        print(f"[VIDEO] Updated audio prompt in node 115")
    elif no_sound:
        print(f"[VIDEO] No-sound mode: skipping audio prompt update")

    # Actualizar negative prompt (nodo 89)
    if negative_prompt and "89" in workflow:
        base_negative = workflow["89"]["inputs"].get("text", "")
        workflow["89"]["inputs"]["text"] = f"{base_negative} {negative_prompt}".strip()

    # Actualizar dimensiones y length (nodo 98 - WanImageToVideo)
    if "98" in workflow:
        if length is not None:
            try:
                workflow["98"]["inputs"]["length"] = int(length)
            except (ValueError, TypeError):
                pass
        
        if width is not None:
            try:
                workflow["98"]["inputs"]["width"] = int(width)
            except (ValueError, TypeError):
                pass
        
        if height is not None:
            try:
                workflow["98"]["inputs"]["height"] = int(height)
            except (ValueError, TypeError):
                pass

    # Actualizar fps según el tipo de workflow
    if fps is not None:
        try:
            # Workflow con sonido usa VHS_VideoCombine (nodo 110)
            if "110" in workflow:
                workflow["110"]["inputs"]["frame_rate"] = int(fps)
                print(f"[VIDEO] Updated fps in VHS_VideoCombine (node 110): {fps}")
            # Workflow sin sonido usa CreateVideo (nodo 94)
            elif "94" in workflow:
                workflow["94"]["inputs"]["fps"] = int(fps)
                print(f"[VIDEO] Updated fps in CreateVideo (node 94): {fps}")
        except (ValueError, TypeError, KeyError):
            pass

    # Subir imagen de entrada
    upload_name = None
    
    # Si tiene data_url, subir desde data URL
    # Para video, siempre subir a 'input' porque el nodo LoadImage busca ahí
    if source_image.get('data_url'):
        from utils.media import upload_image_bytes_to_comfy
        import base64
        
        # Extraer los bytes del data_url
        header, encoded = source_image.get('data_url').split(',', 1)
        content_bytes = base64.b64decode(encoded)
        
        # Determinar mime_type
        mime_type = source_image.get('mime_type') or 'image/png'
        if header.startswith('data:'):
            mime_section = header[5:]
            if ';' in mime_section:
                mime_type = mime_section.split(';', 1)[0] or 'image/png'
            else:
                mime_type = mime_section or 'image/png'
        
        upload_name = upload_image_bytes_to_comfy(
            content_bytes=content_bytes,
            filename=source_image.get('filename') or source_image.get('original_name') or "upload.png",
            mime_type=mime_type,
            image_type='input',  # Siempre 'input' para video
            mode='video'
        )
        print(f"[VIDEO] Uploaded image from data_url to input: {upload_name}")
    # Si es una imagen local, subir desde el sistema de archivos
    elif (source_image.get('type') or '').lower() == 'local':
        upload_name = upload_local_media_to_comfy(
            source_image.get('local_path') or source_image.get('filename', ''),
            mode='video'
        )
        print(f"[VIDEO] Uploaded local image: {upload_name}")
    # Si ya tiene filename, verificar si está en el endpoint correcto
    # Para video, siempre necesitamos que esté en 'input'
    elif source_image.get('filename'):
        source_image_type = (source_image.get('type') or '').lower()
        modal_headers = build_comfy_headers()
        
        # Intentar verificar si la imagen existe en el endpoint de video en 'input'
        try:
            comfy_url = get_comfy_url('video')
            # Verificar si existe en 'input' (donde LoadImage la busca)
            check_response = requests.get(
                f"{comfy_url}/view",
                params={
                    'filename': source_image.get('filename'),
                    'type': 'input'
                },
                headers=modal_headers,
                timeout=5
            )
            
            if check_response.status_code == 200:
                upload_name = source_image.get('filename')
                print(f"[VIDEO] Image already exists in video endpoint (input): {upload_name}")
            else:
                # No existe en 'input', necesitamos descargarla y re-subirla a 'input'
                try:
                    from utils.comfy_config import get_comfy_url
                    from utils.media import upload_image_bytes_to_comfy
                    
                    # Intentar descargar desde el endpoint donde esté (generate o video)
                    download_urls = []
                    if source_image_type == 'output':
                        # Si viene de output, intentar desde generate primero
                        download_urls.append(('generate', 'output'))
                        download_urls.append(('video', 'output'))
                    else:
                        # Si viene de input, intentar desde generate primero
                        download_urls.append(('generate', 'input'))
                        download_urls.append(('video', 'input'))
                    
                    download_response = None
                    for endpoint_mode, img_type in download_urls:
                        try:
                            endpoint_url = get_comfy_url(endpoint_mode)
                            download_response = requests.get(
                                f"{endpoint_url}/view",
                                params={
                                    'filename': source_image.get('filename'),
                                    'type': img_type
                                },
                                headers=modal_headers,
                                timeout=10
                            )
                            if download_response.status_code == 200:
                                print(f"[VIDEO] Found image in {endpoint_mode} endpoint ({img_type})")
                                break
                        except Exception:
                            continue
                    
                    if download_response and download_response.status_code == 200:
                        # Subir al endpoint de video en 'input' (donde LoadImage la busca)
                        upload_name = upload_image_bytes_to_comfy(
                            content_bytes=download_response.content,
                            filename=source_image.get('filename', 'upload.png'),
                            mime_type=download_response.headers.get('Content-Type', 'image/png'),
                            image_type='input',  # Siempre 'input' para video
                            mode='video'
                        )
                        print(f"[VIDEO] Re-uploaded image to video endpoint (input): {upload_name}")
                    else:
                        raise ValueError(f"Could not download image from any endpoint")
                except Exception as download_error:
                    print(f"[WARN] Could not download from endpoints: {download_error}")
                    raise
        except Exception as e:
            print(f"[WARN] Could not verify/re-upload image: {e}")
            # Si falla, intentar re-subir desde generate
            try:
                from utils.media import upload_image_to_comfy
                upload_name = upload_image_to_comfy(
                    filename=source_image.get('filename', ''),
                    subfolder=source_image.get('subfolder', ''),
                    image_type=source_image_type or 'output',
                    mode='video'
                )
                print(f"[VIDEO] Re-uploaded image to video endpoint (fallback): {upload_name}")
            except Exception as e2:
                print(f"[WARN] Fallback re-upload also failed: {e2}")
                # Último recurso: usar el filename directamente
                upload_name = source_image.get('filename')
                print(f"[VIDEO] Using filename directly as last resort: {upload_name}")
    else:
        raise ValueError("No valid image source provided (data_url, local_path, or filename required)")

    # Actualizar nodo LoadImage (puede ser 97 o 117 dependiendo del workflow)
    if "117" in workflow:
        workflow["117"]["inputs"]["image"] = upload_name
        print(f"[VIDEO] Updated LoadImage node 117 with: {upload_name}")
    elif "97" in workflow:
        workflow["97"]["inputs"]["image"] = upload_name
        print(f"[VIDEO] Updated LoadImage node 97 with: {upload_name}")

    client_id = str(uuid.uuid4())

    result = queue_prompt(workflow, client_id, mode='video')
    prompt_id = result.get("prompt_id")
    print(f"[VIDEO] Prompt queued with ID: {prompt_id}")

    # Detectar automáticamente los nodos de salida de video
    video_output_nodes = find_video_output_nodes(workflow)
    print(f"[VIDEO] Detected video output nodes: {video_output_nodes}")

    # Buscar video en los nodos detectados
    videos = wait_for_completion(
        client_id,
        prompt_id,
        target_nodes=video_output_nodes,
        media_key="videos",
        mode='video'
    )

    if not videos:
        raise ValueError("Video generation completed but no output was returned")

    normalized_videos = persist_media_locally(videos, prompt_id, media_category="videos", mode='video')
    if not normalized_videos:
        raise ValueError("Video generation finished but no videos were persisted.")

    print(f"[VIDEO] Outputs for prompt {prompt_id}: {normalized_videos}")

    return {
        "success": True,
        "prompt_id": prompt_id,
        "client_id": client_id,
        "videos": normalized_videos
    }

