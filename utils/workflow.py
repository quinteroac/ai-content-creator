"""
Workflow utilities for loading and processing ComfyUI workflows
"""
import os
import json
import sys
from config import WORKFLOW_PATH, VIDEO_WORKFLOW_PATH, EDIT_WORKFLOW_PATH

def load_workflow(workflow_path, default_relative=None):
    """Cargar workflow desde archivo JSON"""
    try:
        # Intentar rutas relativas y absolutas
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Ajustar para que funcione desde utils/
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

def find_save_image_nodes(workflow):
    """Encontrar todos los nodos SaveImage en un workflow"""
    save_image_nodes = []
    for node_id, node_data in workflow.items():
        if isinstance(node_data, dict) and node_data.get("class_type") == "SaveImage":
            save_image_nodes.append(node_id)
            print(f"[DEBUG] Found SaveImage node: {node_id}")
    
    if save_image_nodes:
        print(f"[INFO] SaveImage nodes detected: {save_image_nodes}")
        return save_image_nodes
    else:
        print(f"[WARN] No SaveImage nodes found, using fallback node 19")
        return ["19"]  # Fallback al nodo por defecto

def find_video_output_nodes(workflow):
    """Encontrar todos los nodos que generan videos en un workflow"""
    video_nodes = []
    for node_id, node_data in workflow.items():
        if isinstance(node_data, dict):
            class_type = node_data.get("class_type", "")
            # Detectar nodos de video comunes
            if class_type in ["VHS_VideoCombine", "SaveVideo", "CreateVideo", "VideoCombine"]:
                video_nodes.append(node_id)
                print(f"[DEBUG] Found video output node: {node_id} ({class_type})")
    
    if video_nodes:
        print(f"[INFO] Video output nodes detected: {video_nodes}")
        return video_nodes
    else:
        print(f"[WARN] No video output nodes found, using fallback node 110")
        return ["110"]  # Fallback al nodo por defecto

# Cargar workflows base
try:
    BASE_WORKFLOW = load_workflow(WORKFLOW_PATH, 'workflows/text-to-image/text-to-image-lumina.json')
except Exception as e:
    print(f"Error fatal: No se pudo cargar el workflow de Lumina: {e}")
    print("Asegúrate de que el archivo workflows/text-to-image/text-to-image-lumina.json existe")
    sys.exit(1)

# Cargar workflow de Chroma
CHROMA_WORKFLOW = None
try:
    CHROMA_WORKFLOW = load_workflow('workflows/text-to-image/text-to-image-chroma.json', 'workflows/text-to-image/text-to-image-chroma.json')
except Exception as e:
    print(f"Warning: No se pudo cargar el workflow de Chroma: {e}")
    print("El workflow de Chroma no estará disponible")

# Cargar workflow de Qwen
QWEN_WORKFLOW = None
try:
    QWEN_WORKFLOW = load_workflow('workflows/text-to-image/text-to-image-qwen-edit.json', 'workflows/text-to-image/text-to-image-qwen-edit.json')
except Exception as e:
    print(f"Warning: No se pudo cargar el workflow de Qwen: {e}")
    print("El modelo Qwen no estará disponible")

def get_workflow_by_model(model='lumina'):
    """Obtener el workflow según el modelo seleccionado
    
    Args:
        model: Modelo a usar ('lumina', 'chroma' o 'qwen')
    
    Returns:
        Workflow JSON correspondiente al modelo
    """
    model_lower = model.lower() if model else 'lumina'
    if model_lower == 'chroma':
        if CHROMA_WORKFLOW is None:
            print(f"Warning: Chroma workflow no disponible, usando Lumina por defecto")
            return BASE_WORKFLOW
        return CHROMA_WORKFLOW
    if model_lower == 'qwen':
        if QWEN_WORKFLOW is None:
            print("Warning: Qwen workflow no disponible, usando Lumina por defecto")
            return BASE_WORKFLOW
        return QWEN_WORKFLOW
    else:
        return BASE_WORKFLOW

try:
    EDIT_WORKFLOW = load_workflow(EDIT_WORKFLOW_PATH, 'workflows/edit-image/edit-image-qwen-2509-aio.json')
except Exception as e:
    print(f"Error fatal: No se pudo cargar el workflow de edición: {e}")
    print("Asegúrate de que el archivo workflows/edit-image/edit-image-qwen-2509.json existe")
    sys.exit(1)

try:
    VIDEO_WORKFLOW = load_workflow(VIDEO_WORKFLOW_PATH, 'workflows/image-to-video/video_wan2_2_14B_i2v_remix.json')
except Exception as e:
    print(f"Warning: No se pudo cargar el workflow de video: {e}")
    VIDEO_WORKFLOW = None

