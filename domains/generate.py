"""
Domain logic for image generation (text-to-image)
"""
import json
import uuid
from utils.workflow import get_workflow_by_model, find_save_image_nodes
from utils.comfy import queue_prompt, wait_for_completion
from utils.media import persist_media_locally

CHROMA_DEFAULT_NEGATIVE = (
    "Blurry, Low res, Bad Quality, Low Quality, blurry, low quality, pixelated, noisy, distorted, "
    "mutated hands, mutated fingers, extra limbs, extra arms, extra legs, extra heads, extra eyes, "
    "deformed face, unrealistic anatomy, unnatural proportions, poorly drawn, doll-like, plastic skin, "
    "waxy texture, cartoon, 3d render, cgi, clay, low resolution, watermark, text, signature, cut off, "
    "cropped head, missing limbs, asymmetry, glowing skin, unnatural colors, oversaturated, out of focus, "
    "bad perspective, malformed body, bad composition, amateur drawing"
)

def generate_random_seed():
    """Generar una semilla aleatoria para la generación de imágenes"""
    import random
    return random.randint(0, 2**32 - 1)

def _get_prompt_text(inputs):
    """Obtener el campo de texto/prompt disponible."""
    if not isinstance(inputs, dict):
        return ""
    return inputs.get("text") or inputs.get("prompt") or ""


def _set_prompt_text(inputs, value):
    """Actualizar el texto/prompt respetando el campo disponible."""
    if not isinstance(inputs, dict):
        return
    if "text" in inputs:
        inputs["text"] = value
    elif "prompt" in inputs:
        inputs["prompt"] = value
    else:
        inputs["text"] = value


def generate_images(positive_prompt, negative_prompt=None, width=1024, height=1024, steps=20, seed=None, model='lumina'):
    """Generar imágenes usando ComfyUI
    
    Args:
        positive_prompt: Prompt positivo para la generación
        negative_prompt: Prompt negativo (opcional)
        width: Ancho de la imagen
        height: Alto de la imagen
        steps: Número de pasos de inferencia
        seed: Semilla para la generación (opcional)
        model: Modelo a usar ('lumina', 'chroma' o 'qwen')
    """
    client_id = str(uuid.uuid4())
    
    # Cargar workflow según el modelo seleccionado
    base_workflow = get_workflow_by_model(model)
    workflow = json.loads(json.dumps(base_workflow))

    # Detectar nodos automáticamente según el tipo de workflow
    positive_nodes = []
    negative_nodes = []
    latent_nodes = []
    sampler_nodes = []
    scheduler_nodes = []
    noise_nodes = []
    
    # Nodos conocidos por modelo (fallback)
    known_positive_nodes = {"lumina": ["6", "15"], "chroma": ["748"], "qwen": ["10"]}
    known_negative_nodes = {"lumina": ["7", "16"], "chroma": ["749"], "qwen": ["7"]}
    known_latent_nodes = {"lumina": ["13", "5"], "chroma": ["737"], "qwen": ["5"]}
    known_scheduler_nodes = {"lumina": ["3", "10", "11"], "chroma": ["734"], "qwen": ["3"]}
    known_noise_nodes = {"lumina": [], "chroma": ["718"], "qwen": []}
    
    for node_id, node_data in workflow.items():
        if isinstance(node_data, dict):
            class_type = node_data.get("class_type", "")
            inputs = node_data.get("inputs", {})
            meta = node_data.get("_meta", {})
            title = meta.get("title", "").lower() if meta else ""
            
            # Detectar nodos de prompts por class_type y título
            if class_type in ("CLIPTextEncode", "TextEncodeQwenImageEditPlus"):
                text = _get_prompt_text(inputs).lower()
                if "positive" in text or "positive" in title or node_id in known_positive_nodes.get(model, []):
                    positive_nodes.append(node_id)
                elif "negative" in text or "negative" in title or node_id in known_negative_nodes.get(model, []):
                    negative_nodes.append(node_id)
            
            # Detectar nodos de latente
            if class_type in ["EmptyLatentImage", "EmptySD3LatentImage"]:
                latent_nodes.append(node_id)
            
            # Detectar nodos de sampler
            if class_type in ["KSampler", "KSamplerAdvanced", "SamplerCustomAdvanced"]:
                sampler_nodes.append(node_id)
            
            # Detectar nodos de scheduler
            if class_type == "BasicScheduler" or (class_type == "KSampler" and "steps" in inputs):
                scheduler_nodes.append(node_id)
            
            # Detectar nodos de noise/seed
            if class_type == "RandomNoise":
                noise_nodes.append(node_id)
            elif "noise_seed" in inputs:
                noise_nodes.append(node_id)

    # Usar valores por defecto si no se detectaron nodos
    if not positive_nodes:
        positive_nodes = known_positive_nodes.get(model, ["6"])
    if not negative_nodes:
        negative_nodes = known_negative_nodes.get(model, ["7"])
    if not latent_nodes:
        latent_nodes = known_latent_nodes.get(model, ["13"])
    if not scheduler_nodes:
        scheduler_nodes = known_scheduler_nodes.get(model, ["3"])
    if not noise_nodes:
        noise_nodes = known_noise_nodes.get(model, [])

    # Actualizar prompts positivos
    base_positive = ""
    for node_id in positive_nodes:
        base_positive = _get_prompt_text(workflow.get(node_id, {}).get("inputs", {}))
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
            _set_prompt_text(workflow[node_id]["inputs"], new_positive)
    
    # Aplicar negative prompt por defecto para Chroma
    if model == 'chroma':
        if negative_prompt:
            negative_prompt = f"{negative_prompt}, {CHROMA_DEFAULT_NEGATIVE}"
        else:
            negative_prompt = CHROMA_DEFAULT_NEGATIVE

    # Actualizar prompts negativos si se proporciona
    if negative_prompt:
        base_negative = ""
        for node_id in negative_nodes:
            base_negative = _get_prompt_text(workflow.get(node_id, {}).get("inputs", {}))
            if base_negative:
                break
        if base_negative:
            new_negative = f"{base_negative} {negative_prompt}".strip()
        else:
            new_negative = negative_prompt

        for node_id in negative_nodes:
            if node_id in workflow and "inputs" in workflow[node_id]:
                _set_prompt_text(workflow[node_id]["inputs"], new_negative)

    # Actualizar resolución
    for node_id in latent_nodes:
        if node_id in workflow and "inputs" in workflow[node_id]:
            workflow[node_id]["inputs"]["width"] = int(width)
            workflow[node_id]["inputs"]["height"] = int(height)

    # Actualizar configuración de muestreo (steps y seed)
    steps_value = int(steps)
    seed_value = int(seed) if seed is not None else generate_random_seed()

    # Actualizar steps en scheduler nodes
    for node_id in scheduler_nodes:
        if node_id in workflow and "inputs" in workflow[node_id]:
            sampler_inputs = workflow[node_id]["inputs"]
            if "steps" in sampler_inputs:
                sampler_inputs["steps"] = steps_value

    # Actualizar seed en sampler nodes y noise nodes
    for node_id in sampler_nodes + noise_nodes:
        if node_id in workflow and "inputs" in workflow[node_id]:
            sampler_inputs = workflow[node_id]["inputs"]
            if "noise_seed" in sampler_inputs:
                sampler_inputs["noise_seed"] = seed_value
            if "seed" in sampler_inputs:
                sampler_inputs["seed"] = seed_value
    
    # Detectar automáticamente los nodos SaveImage en el workflow
    save_image_nodes = find_save_image_nodes(workflow)
    print(f"[INFO] Model: {model}, Detected SaveImage nodes: {save_image_nodes}")
    
    try:
        # Enviar a la cola usando modo 'generate'
        result = queue_prompt(workflow, client_id, mode='generate')
        prompt_id = result["prompt_id"]
        print(f"[INFO] Prompt queued with ID: {prompt_id}, waiting for completion with target nodes: {save_image_nodes}")
        
        # Esperar a que se complete usando los nodos detectados
        images = wait_for_completion(client_id, prompt_id, target_nodes=save_image_nodes, mode='generate')
        print(f"[INFO] Received {len(images) if images else 0} image(s) from wait_for_completion")
        
        if not images:
            print(f"[ERROR] No images returned from wait_for_completion for prompt_id: {prompt_id}")
            raise ValueError(f"No images were returned from ComfyUI for prompt_id: {prompt_id}")
        
        local_images = persist_media_locally(images, prompt_id, media_category="images", mode='generate')
        if not local_images:
            print(f"[ERROR] Failed to persist images locally for prompt_id: {prompt_id}")
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

