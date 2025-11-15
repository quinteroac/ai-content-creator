"""
ComfyUI integration utilities
Functions for interacting with ComfyUI API
"""
import json
import uuid
import time
import threading
import requests
import websocket
from utils.comfy_config import get_comfy_url, COMFYUI_HOST, COMFYUI_PORT, WS_PROTOCOL, build_comfy_headers

def queue_prompt(workflow, client_id=None, mode='generate'):
    """Enviar prompt a la cola de ComfyUI"""
    if client_id is None:
        client_id = str(uuid.uuid4())
    try:
        comfy_url = get_comfy_url(mode)
        p = {"prompt": workflow, "client_id": client_id}
        data = json.dumps(p).encode('utf-8')
        
        response = requests.post(
            f"{comfy_url}/prompt",
            data=data,
            headers=build_comfy_headers({"Content-Type": "application/json"})
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Error sending prompt: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error in queue_prompt: {e}")
        raise

def get_media_outputs(prompt_id, target_nodes=None, media_key="images", mode='generate'):
    """Obtener archivos generados (imágenes, videos, etc.) para un prompt_id específico"""
    target_nodes = target_nodes or ["19"]
    comfy_url = get_comfy_url(mode)
    print(f"[DEBUG] get_media_outputs called: prompt_id={prompt_id}, target_nodes={target_nodes}, media_key={media_key}, mode={mode}")
    
    possible_keys = [media_key]
    if media_key == "videos":
        # VHS_VideoCombine puede usar diferentes claves
        possible_keys.extend(["video", "videos", "files", "images", "mp4", "output"])
    elif media_key == "images":
        possible_keys.extend(["image", "images", "files"])
    else:
        possible_keys.extend(["videos", "images", "files", "video", "image"])
    
    try:
        # Intentar primero el endpoint específico /history/{prompt_id}
        try:
            response = requests.get(
                f"{comfy_url}/history/{prompt_id}",
                headers=build_comfy_headers()
            )
            if response.status_code == 200:
                history_data = response.json()

                candidates = []
                if isinstance(history_data, dict):
                    if "outputs" in history_data:
                        candidates.append(history_data)
                    if prompt_id in history_data and isinstance(history_data[prompt_id], dict):
                        candidates.append(history_data[prompt_id])

                for candidate in candidates:
                    if "outputs" not in candidate:
                        continue
                    # Primero buscar en los nodos target específicos
                    for node_id in target_nodes:
                        if node_id in candidate["outputs"]:
                            node_outputs = candidate["outputs"][node_id]
                            print(f"[DEBUG] Node {node_id} outputs keys: {list(node_outputs.keys())}")
                            try:
                                print(f"[DEBUG] Node {node_id} outputs full structure: {json.dumps(node_outputs, indent=2, default=str)[:500]}")
                            except Exception as e:
                                print(f"[DEBUG] Node {node_id} outputs structure (could not serialize): {str(node_outputs)[:500]}")
                            
                            # Buscar en todas las claves posibles
                            for key in possible_keys:
                                if key in node_outputs:
                                    media = node_outputs[key]
                                    count = len(media) if isinstance(media, list) else 1
                                    print(f"[OK] {key.capitalize()} found in node {node_id}: {count} item(s)")
                                    if isinstance(media, list):
                                        return media
                                    return [media]
                            
                            # Si no encontramos en las claves esperadas, buscar cualquier lista que parezca un archivo de video
                            for key, value in node_outputs.items():
                                if isinstance(value, list) and len(value) > 0:
                                    first_item = value[0]
                                    if isinstance(first_item, dict):
                                        filename = first_item.get("filename", "")
                                        if any(ext in filename.lower() for ext in [".mp4", ".webm", ".avi", ".mov"]):
                                            print(f"[INFO] Found video-like files in node {node_id}, key '{key}': {len(value)} item(s)")
                                            return value
                                    elif isinstance(first_item, str) and any(ext in first_item.lower() for ext in [".mp4", ".webm", ".avi", ".mov"]):
                                        print(f"[INFO] Found video-like files in node {node_id}, key '{key}': {len(value)} item(s)")
                                        return value
                    
                    # Si no se encontró en los nodos target, buscar en TODOS los nodos
                    for node_id, node_outputs in candidate["outputs"].items():
                        if isinstance(node_outputs, dict):
                            print(f"[DEBUG] Checking all nodes in candidate - Node {node_id} outputs keys: {list(node_outputs.keys())}")
                            
                            # Buscar en claves esperadas
                            for key in possible_keys:
                                if key in node_outputs:
                                    media = node_outputs[key]
                                    count = len(media) if isinstance(media, list) else 1
                                    print(f"[INFO] Found {key.capitalize()} in node {node_id} (not in target_nodes): {count}")
                                    if isinstance(media, list):
                                        return media
                                    return [media]
                            
                            # Buscar cualquier lista que parezca contener videos
                            for data_key, data_value in node_outputs.items():
                                if isinstance(data_value, list) and len(data_value) > 0:
                                    first_item = data_value[0]
                                    if isinstance(first_item, dict):
                                        filename = first_item.get("filename", "")
                                        if any(ext in filename.lower() for ext in [".mp4", ".webm", ".avi", ".mov"]):
                                            print(f"[INFO] Found video-like files in node {node_id}, key '{data_key}' (all nodes in candidate): {len(data_value)} item(s)")
                                            return data_value
                                    elif isinstance(first_item, str) and any(ext in first_item.lower() for ext in [".mp4", ".webm", ".avi", ".mov"]):
                                        print(f"[INFO] Found video-like files in node {node_id}, key '{data_key}' (all nodes in candidate): {len(data_value)} item(s)")
                                        return data_value

        except requests.exceptions.RequestException as e:
            print(f"[WARN] Endpoint /history/{prompt_id} not available (status: {getattr(e.response, 'status_code', 'N/A')}), using fallback")

        # Fallback: obtener el historial completo y buscar el prompt_id
        response = requests.get(
            f"{comfy_url}/history",
            headers=build_comfy_headers()
        )
        if response.status_code == 200:
            history = response.json()
            if prompt_id in history:
                prompt_data = history[prompt_id]
                if "outputs" in prompt_data:
                    for node_id in target_nodes:
                        if node_id in prompt_data["outputs"]:
                            node_outputs = prompt_data["outputs"][node_id]
                            print(f"[DEBUG] Node {node_id} outputs keys: {list(node_outputs.keys())}")
                            try:
                                print(f"[DEBUG] Node {node_id} outputs full structure: {json.dumps(node_outputs, indent=2, default=str)[:500]}")
                            except Exception as e:
                                print(f"[DEBUG] Node {node_id} outputs structure (could not serialize): {str(node_outputs)[:500]}")
                            
                            # Buscar en todas las claves posibles
                            for key in possible_keys:
                                if key in node_outputs:
                                    media = node_outputs[key]
                                    count = len(media) if isinstance(media, list) else 1
                                    print(f"[OK] {key.capitalize()} found in node {node_id} (full history): {count} item(s)")
                                    if isinstance(media, list):
                                        print(f"  Filenames: {[item.get('filename', str(item)) if isinstance(item, dict) else item for item in media[:4]]}")
                                        return media
                                    print(f"  Filename: {media.get('filename', str(media)) if isinstance(media, dict) else media}")
                                    return [media]
                            
                            # Si no encontramos en las claves esperadas, buscar cualquier lista que parezca un archivo de video
                            for key, value in node_outputs.items():
                                if isinstance(value, list) and len(value) > 0:
                                    first_item = value[0]
                                    if isinstance(first_item, dict):
                                        filename = first_item.get("filename", "")
                                        if any(ext in filename.lower() for ext in [".mp4", ".webm", ".avi", ".mov"]):
                                            print(f"[INFO] Found video-like files in node {node_id}, key '{key}' (full history): {len(value)} item(s)")
                                            return value
                                    elif isinstance(first_item, str) and any(ext in first_item.lower() for ext in [".mp4", ".webm", ".avi", ".mov"]):
                                        print(f"[INFO] Found video-like files in node {node_id}, key '{key}' (full history): {len(value)} item(s)")
                                        return value

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
            
            # Si no se encontró en los nodos target, buscar en TODOS los nodos que tengan outputs
            for key, value in history.items():
                if key == prompt_id and isinstance(value, dict) and "outputs" in value:
                    for node_id, node_data in value.get("outputs", {}).items():
                        if isinstance(node_data, dict):
                            print(f"[DEBUG] Checking all nodes - Node {node_id} outputs keys: {list(node_data.keys())}")
                            
                            # Buscar en claves esperadas
                            for media_key_candidate in possible_keys:
                                if media_key_candidate in node_data:
                                    media = node_data[media_key_candidate]
                                    print(f"[INFO] Found {media_key_candidate} in node {node_id} (not in target_nodes)")
                                    if isinstance(media, list):
                                        return media
                                    return [media]
                            
                            # Buscar cualquier lista que parezca contener videos
                            for data_key, data_value in node_data.items():
                                if isinstance(data_value, list) and len(data_value) > 0:
                                    first_item = data_value[0]
                                    if isinstance(first_item, dict):
                                        filename = first_item.get("filename", "")
                                        if any(ext in filename.lower() for ext in [".mp4", ".webm", ".avi", ".mov"]):
                                            print(f"[INFO] Found video-like files in node {node_id}, key '{data_key}' (all nodes search): {len(data_value)} item(s)")
                                            return data_value
                                    elif isinstance(first_item, str) and any(ext in first_item.lower() for ext in [".mp4", ".webm", ".avi", ".mov"]):
                                        print(f"[INFO] Found video-like files in node {node_id}, key '{data_key}' (all nodes search): {len(data_value)} item(s)")
                                        return data_value
        return None
    except Exception as e:
        print(f"Error getting history for prompt_id {prompt_id}: {e}")
        import traceback
        traceback.print_exc()
        return None

def wait_for_completion(client_id, prompt_id, max_wait=300, target_nodes=None, media_key="images", mode='generate'):
    """Esperar a que se complete la generación y obtener los archivos solicitados"""
    target_nodes = target_nodes or ["19"]
    print(f"[INFO] wait_for_completion: prompt_id={prompt_id}, target_nodes={target_nodes}, media_key={media_key}, max_wait={max_wait}")
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
                    if not data.get("data", {}).get("node"):
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
        if COMFYUI_PORT == 443 and WS_PROTOCOL == "wss":
            ws_url = f"{WS_PROTOCOL}://{COMFYUI_HOST}/ws?clientId={client_id}"
        else:
            ws_url = f"{WS_PROTOCOL}://{COMFYUI_HOST}:{COMFYUI_PORT}/ws?clientId={client_id}"

        modal_headers = build_comfy_headers()
        ws_header = [f"{key}: {value}" for key, value in modal_headers.items()] if modal_headers else None
        ws = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
            header=ws_header
        )
        
        def run_ws():
            try:
                ws.run_forever()
            except Exception as e:
                print(f"Error en WebSocket: {e}")
        
        thread = threading.Thread(target=run_ws, daemon=True)
        thread.start()
        time.sleep(1)
    except Exception as e:
        print(f"Error al conectar WebSocket: {e}")
    
    # Esperar hasta que se complete o timeout
    start_time = time.time()
    check_interval = 0.5
    last_check = 0
    prompt_found_in_history = False
    consecutive_no_outputs = 0
    max_consecutive_no_outputs = 10
    
    # Primera verificación inmediata
    media_info = get_media_outputs(prompt_id, target_nodes=target_nodes, media_key=media_key, mode=mode)
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
    
    # Verificar si el prompt ya existe en el historial
    comfy_url = get_comfy_url(mode)
    try:
        response = requests.get(
            f"{comfy_url}/history/{prompt_id}",
            headers=build_comfy_headers()
        )
        if response.status_code == 200:
            history_data = response.json()
            if prompt_id in history_data or "outputs" in history_data:
                prompt_found_in_history = True
                print(f"[INFO] Prompt {prompt_id} already exists in history")
    except:
        pass
    
    while time.time() - start_time < max_wait:
        if time.time() - last_check >= check_interval:
            comfy_url = get_comfy_url(mode)
            try:
                response = requests.get(
                    f"{comfy_url}/history/{prompt_id}",
                    headers=build_comfy_headers()
                )
                if response.status_code == 200:
                    history_data = response.json()
                    if prompt_id in history_data or "outputs" in history_data:
                        prompt_found_in_history = True
            except:
                pass
            
            media_info = get_media_outputs(prompt_id, target_nodes=target_nodes, media_key=media_key, mode=mode)
            if media_info and len(media_info) > 0:
                consecutive_no_outputs = 0
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
            else:
                if prompt_found_in_history:
                    consecutive_no_outputs += 1
                    if consecutive_no_outputs >= max_consecutive_no_outputs:
                        print(f"[WARN] Prompt {prompt_id} exists in history but no {media_key} found after {max_consecutive_no_outputs} checks. Exiting wait loop.")
                        break
            last_check = time.time()
        
        if execution_completed:
            time.sleep(2)
            media_info = get_media_outputs(prompt_id, target_nodes=target_nodes, media_key=media_key, mode=mode)
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
    
    if ws:
        try:
            ws.close()
        except:
            pass
    
    if not media_items:
        time.sleep(2)
        media_info = get_media_outputs(prompt_id, target_nodes=target_nodes, media_key=media_key, mode=mode)
        if media_info:
            if isinstance(media_info, list):
                media_items = media_info
            else:
                media_items = [media_info]

    return media_items


def interrupt_comfy_execution(mode='generate'):
    """Enviar señal de interrupción a ComfyUI para detener la ejecución actual."""
    comfy_url = get_comfy_url(mode)
    try:
        response = requests.post(
            f"{comfy_url}/queue/interrupt",
            headers=build_comfy_headers(),
            timeout=5
        )
        if response.status_code not in (200, 204):
            raise Exception(f"Interrupt failed: HTTP {response.status_code} - {response.text}")
        return True
    except Exception as exc:
        print(f"[COMFY] Error interrupting execution: {exc}")
        raise
