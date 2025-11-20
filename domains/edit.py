"""
Domain logic for image editing
"""
import json
import uuid
from utils.workflow import EDIT_WORKFLOW, find_save_image_nodes
from utils.comfy import queue_prompt, wait_for_completion
from utils.media import (
    persist_media_locally,
    upload_image_data_url_to_comfy,
    upload_local_media_to_comfy,
    upload_image_to_comfy,
)

def generate_random_seed():
    """Generar una semilla aleatoria para la generación de imágenes"""
    import random
    return random.randint(0, 2**32 - 1)

def _find_nodes_by_class(workflow, class_types):
    """Obtener todos los nodos cuyo class_type esté en class_types."""
    class_set = set(class_types)
    return [
        node_id
        for node_id, node_data in workflow.items()
        if isinstance(node_data, dict) and node_data.get("class_type") in class_set
    ]


def _find_first_node_by_class(workflow, class_types):
    """Obtener el primer nodo que coincida con class_types."""
    nodes = _find_nodes_by_class(workflow, class_types)
    return nodes[0] if nodes else None


def _get_prompt_text(inputs):
    if not isinstance(inputs, dict):
        return ""
    return inputs.get("text") or inputs.get("prompt") or ""


def _set_prompt_text(inputs, value):
    if not isinstance(inputs, dict):
        return
    if "text" in inputs:
        inputs["text"] = value
    elif "prompt" in inputs:
        inputs["prompt"] = value
    else:
        inputs["text"] = value


def generate_image_edit(positive_prompt, source_image, width=None, height=None, steps=20, seed=None):
    """Editar una imagen existente usando el workflow Qwen AIO."""
    if not EDIT_WORKFLOW:
        raise ValueError("Edit workflow is not available")

    if not source_image or (
        not source_image.get('filename') and not source_image.get('data_url')
    ):
        raise ValueError("No source image provided for edit mode")

    workflow = json.loads(json.dumps(EDIT_WORKFLOW))

    if source_image.get('data_url'):
        upload_name = upload_image_data_url_to_comfy(
            data_url=source_image.get('data_url'),
            filename=source_image.get('filename') or "upload.png",
            mime_type_override=source_image.get('mime_type'),
            mode='edit'
        )
    elif (source_image.get('type') or '').lower() == 'local':
        upload_name = upload_local_media_to_comfy(
            source_image.get('local_path') or source_image.get('filename', ''),
            mode='edit'
        )
    else:
        upload_name = upload_image_to_comfy(
            filename=source_image.get('filename', ''),
            subfolder=source_image.get('subfolder', ''),
            image_type=source_image.get('type', 'output'),
            mode='edit'
        )

    load_image_node = _find_first_node_by_class(workflow, {"LoadImage", "LoadImageMask"})
    if load_image_node and "inputs" in workflow[load_image_node]:
        workflow[load_image_node]["inputs"]["image"] = upload_name

    positive_nodes = [
        node_id for node_id, node_data in workflow.items()
        if isinstance(node_data, dict)
        and node_data.get("class_type") in ("TextEncodeQwenImageEditPlus", "CLIPTextEncode")
        and "positive" in node_data.get("_meta", {}).get("title", "").lower()
    ]
    if not positive_nodes:
        positive_nodes = _find_nodes_by_class(workflow, {"TextEncodeQwenImageEditPlus"})

    for node_id in positive_nodes:
        _set_prompt_text(workflow.get(node_id, {}).get("inputs", {}), positive_prompt or "")

    latent_nodes = _find_nodes_by_class(workflow, {"EmptyLatentImage", "EmptySD3LatentImage"})
    if width is not None and height is not None:
        try:
            w = int(width)
            h = int(height)
            for node_id in latent_nodes:
                inputs = workflow.get(node_id, {}).get("inputs", {})
                if isinstance(inputs, dict):
                    inputs["width"] = w
                    inputs["height"] = h
        except (ValueError, TypeError):
            pass

    steps_value = int(steps)
    seed_value = int(seed) if seed is not None else generate_random_seed()

    sampler_nodes = _find_nodes_by_class(workflow, {"KSampler", "KSamplerAdvanced"})
    for node_id in sampler_nodes:
        inputs = workflow.get(node_id, {}).get("inputs", {})
        if isinstance(inputs, dict):
            if "steps" in inputs:
                inputs["steps"] = steps_value
            if "seed" in inputs:
                inputs["seed"] = seed_value

    client_id = str(uuid.uuid4())
    result = queue_prompt(workflow, client_id, mode='edit')
    prompt_id = result["prompt_id"]

    target_nodes = find_save_image_nodes(workflow)
    images = wait_for_completion(
        client_id,
        prompt_id,
        target_nodes=target_nodes,
        media_key="images",
        mode='edit'
    )

    if not images:
        raise ValueError("Edit workflow completed but returned no images")

    local_images = persist_media_locally(images, prompt_id, media_category="images", mode='edit')
    if not local_images:
        raise ValueError("No edited images were persisted locally.")

    return {
        "success": True,
        "prompt_id": prompt_id,
        "images": local_images,
        "client_id": client_id
    }

