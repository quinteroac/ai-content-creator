"""
Routes for image generation
"""
from flask import Blueprint, request, jsonify
from domains.generate import generate_images
from auth import api_login_required
from utils.comfy import interrupt_comfy_execution

def create_generate_blueprint(app):
    """Crear blueprint de generación de imágenes"""
    generate_bp = Blueprint('generate', __name__)

    @generate_bp.route('/api/generate', methods=['POST'])
    @api_login_required(app)
    def api_generate():
        """API endpoint para generar imágenes"""
        try:
            data = request.get_json()
            prompt = data.get('prompt', '').strip()
            width = data.get('width', 1024)
            height = data.get('height', 1024)
            steps = data.get('steps', 20)
            seed = data.get('seed', None)
            mode = (data.get('mode') or 'generate').strip().lower()
            model = data.get('model', 'lumina').strip().lower() if data.get('model') else 'lumina'
            
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
            
            # Validar modelo solo en modo generate
            if mode == 'generate':
                if model not in ('lumina', 'chroma'):
                    return jsonify({"success": False, "error": "Invalid model. Must be 'lumina' or 'chroma'"}), 400

                checkpoint = data.get('checkpoint')
                lora = data.get('lora')

                result = generate_images(prompt, width=width, height=height, steps=steps, seed=seed, model=model, checkpoint=checkpoint, lora=lora)
            else:
                from domains.edit import generate_image_edit
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

    @generate_bp.route('/api/generate/stop', methods=['POST'])
    @api_login_required(app)
    def api_generate_stop():
        """Detener la generación actual en ComfyUI."""
        try:
            data = request.get_json(silent=True) or {}
            mode = (data.get('mode') or 'generate').strip().lower()
            interrupt_comfy_execution(mode if mode in ('generate', 'edit') else 'generate')
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    return generate_bp

