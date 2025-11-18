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

def generate_images(positive_prompt, negative_prompt=None, width=1024, height=1024, steps=20, seed=None, model='lumina', checkpoint=None, lora=None):
    """Generar imágenes usando ComfyUI
    
    Args:
        positive_prompt: Prompt positivo para la generación
        negative_prompt: Prompt negativo (opcional)
        width: Ancho de la imagen
        height: Alto de la imagen
        steps: Número de pasos de inferencia
        seed: Semilla para la generación (opcional)
        model: Modelo a usar ('lumina' o 'chroma')
        checkpoint: Nombre del archivo del checkpoint a usar
        lora: Nombre del archivo del LoRA a usar
    """
    client_id = str(uuid.uuid4())
    
    # Cargar workflow según el modelo seleccionado
    base_workflow = get_workflow_by_model(model)
    workflow = json.loads(json.dumps(base_workflow))

    # --- Modificación para Checkpoint y LoRA dinámicos ---
    checkpoint_loader_node = None
    lora_loader_node = None
    # Encuentra los nodos de Checkpoint y LoRA
    for node_id, node_data in workflow.items():
        if node_data.get("class_type") == "CheckpointLoaderSimple":
            checkpoint_loader_node = node_id
        if node_data.get("class_type") == "LoraLoader":
            lora_loader_node = node_id

    # Actualiza el checkpoint si se proporciona
    if checkpoint and checkpoint_loader_node:
        workflow[checkpoint_loader_node]["inputs"]["ckpt_name"] = checkpoint

    # Actualiza el LoRA o lo omite
    if lora_loader_node:
        if lora:
            workflow[lora_loader_node]["inputs"]["lora_name"] = lora
        else:
            # Si no se proporciona LoRA, se debe "puentear" la conexión
            # Encuentra el nodo que recibe la salida del LoRA
            for node_id, node_data in workflow.items():
                inputs = node_data.get("inputs", {})
                for input_name, input_value in inputs.items():
                    if isinstance(input_value, list) and input_value[0] == lora_loader_node:
                        # Conecta la salida del CheckpointLoader directamente a este nodo
                        input_value[0] = checkpoint_loader_node
            # Elimina el nodo LoRA del workflow
            del workflow[lora_loader_node]
    # --- Fin de la modificación ---


    # Detectar nodos automáticamente según el tipo de workflow
    positive_nodes = []
    negative_nodes = []
    latent_nodes = []
    sampler_nodes = []
    scheduler_nodes = []
    noise_nodes = []
    
    # Nodos conocidos por modelo (fallback)
    known_positive_nodes = {"lumina": ["6", "15"], "chroma": ["748"]}
    known_negative_nodes = {"lumina": ["7", "16"], "chroma": ["749"]}
    known_latent_nodes = {"lumina": ["13", "5"], "chroma": ["737"]}
    known_scheduler_nodes = {"lumina": ["3", "10", "11"], "chroma": ["734"]}
    known_noise_nodes = {"lumina": [], "chroma": ["718"]}
    
    for node_id, node_data in workflow.items():
        if isinstance(node_data, dict):
            class_type = node_data.get("class_type", "")
            inputs = node_data.get("inputs", {})
            meta = node_data.get("_meta", {})
            title = meta.get("title", "").lower() if meta else ""
            
            # Detectar nodos de prompts por class_type y título
            if class_type == "CLIPTextEncode":
                text = inputs.get("text", "").lower()
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

