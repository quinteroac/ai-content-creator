"""
Routes for video generation
"""
from flask import Blueprint, request, jsonify, render_template, session
from domains.video import generate_video_from_image
from domains.video import generate_video_from_image as generate_video
from utils.video_utils import extract_last_frame, combine_videos_with_extension, get_video_resolution
from utils.media import resolve_local_media_path, upload_image_data_url_to_comfy
from auth import login_required, api_login_required

def create_video_blueprint(app):
    """Crear blueprint de generación de video"""
    video_bp = Blueprint('video', __name__)

    @video_bp.route('/video')
    @login_required(app)
    def video_page():
        """Página para la generación de video"""
        filename = request.args.get('filename', '')
        subfolder = request.args.get('subfolder', '')
        image_type = request.args.get('type', 'output')
        prompt = request.args.get('prompt', '')
        resolution = request.args.get('resolution', '1024x1024')
        local_path = request.args.get('local_path', '')
        prompt_id = request.args.get('prompt_id', '')

        video_data = {
            "filename": filename,
            "subfolder": subfolder,
            "imageType": image_type,
            "prompt": prompt,
            "resolution": resolution,
            "localPath": local_path,
            "promptId": prompt_id,
        }

        return render_template('video.html', video_data=video_data, user_email=session.get('user_email'))

    @video_bp.route('/api/generate-video', methods=['POST'])
    @api_login_required(app)
    def api_generate_video():
        """API endpoint para generar videos a partir de una imagen"""
        try:
            data = request.get_json()
            prompt = (data.get('prompt') or '').strip()
            if not prompt:
                return jsonify({"success": False, "error": "Prompt is required"}), 400

            image_info = data.get('image') or {}
            if not image_info.get('filename'):
                if image_info.get('data_url'):
                    try:
                        upload_name = upload_image_data_url_to_comfy(
                            data_url=image_info.get('data_url'),
                            filename=image_info.get('filename') or image_info.get('original_name') or "upload.png",
                            mime_type_override=image_info.get('mime_type'),
                            mode='video'
                        )
                        image_info = {
                            "filename": upload_name,
                            "subfolder": "input",
                            "type": "input"
                        }
                    except Exception as e:
                        return jsonify({"success": False, "error": f"Unable to upload source image: {e}"}), 500
                else:
                    return jsonify({"success": False, "error": "Source image is required"}), 400

            width = data.get('width')
            height = data.get('height')
            negative_prompt = (data.get('negative_prompt') or '').strip() or None
            length = data.get('length')
            fps = data.get('fps')
            nsfw = data.get('nsfw', False)

            if width is not None:
                try:
                    width = int(width)
                except (TypeError, ValueError):
                    return jsonify({"success": False, "error": "Invalid width"}), 400

            if height is not None:
                try:
                    height = int(height)
                except (TypeError, ValueError):
                    return jsonify({"success": False, "error": "Invalid height"}), 400

            result = generate_video(
                positive_prompt=prompt,
                source_image=image_info,
                width=width,
                height=height,
                negative_prompt=negative_prompt,
                length=length,
                fps=fps,
                nsfw=nsfw
            )

            return jsonify(result)
        except ValueError as e:
            import traceback
            print(f"[ERROR] ValueError in api_generate_video: {e}")
            traceback.print_exc()
            return jsonify({"success": False, "error": str(e)}), 400
        except Exception as e:
            import traceback
            print(f"[ERROR] Exception in api_generate_video: {e}")
            traceback.print_exc()
            return jsonify({"success": False, "error": str(e)}), 500

    @video_bp.route('/api/video/extend', methods=['POST'])
    @api_login_required(app)
    def api_extend_video():
        """Extender un video existente generando un nuevo tramo y concatenándolo."""
        try:
            data = request.get_json(force=True, silent=False) or {}
        except Exception:
            return jsonify({"success": False, "error": "Invalid JSON payload"}), 400

        prompt = (data.get('prompt') or '').strip()
        if not prompt:
            return jsonify({"success": False, "error": "Prompt is required to extend the video."}), 400

        video_info = data.get('video') or {}
        local_reference = (
            video_info.get('local_path')
            or video_info.get('filename')
        )
        if not local_reference:
            return jsonify({"success": False, "error": "Base video reference not provided."}), 400

        try:
            base_video_path = resolve_local_media_path(local_reference)
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

        width = data.get('width')
        height = data.get('height')
        if width is None or height is None:
            try:
                width, height = get_video_resolution(base_video_path)
            except Exception as exc:
                return jsonify({"success": False, "error": f"Unable to determine base video resolution: {exc}"}), 400
        else:
            try:
                width = int(width)
                height = int(height)
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": "Invalid width or height values."}), 400

        negative_prompt = (data.get('negative_prompt') or '').strip() or None
        length = data.get('length')
        fps = data.get('fps')
        nsfw = data.get('nsfw', False)

        try:
            last_frame_info = extract_last_frame(base_video_path)
        except Exception as exc:
            return jsonify({"success": False, "error": f"Unable to extract the last frame: {exc}"}), 500

        frame_source_image = {
            "filename": last_frame_info["filename"],
            "local_path": last_frame_info["local_path"],
            "type": "local",
            "mime_type": last_frame_info.get("mime_type"),
        }

        try:
            generation_result = generate_video(
                positive_prompt=prompt,
                source_image=frame_source_image,
                width=width,
                height=height,
                negative_prompt=negative_prompt,
                length=length,
                fps=fps,
                nsfw=nsfw
            )
        except Exception as exc:
            return jsonify({"success": False, "error": f"Unable to generate extension video: {exc}"}), 500

        if not generation_result.get("success"):
            return jsonify({"success": False, "error": generation_result.get("error") or "Video generation failed."}), 500

        generated_videos = generation_result.get("videos") or []
        if not generated_videos:
            return jsonify({"success": False, "error": "Video extension generation returned no results."}), 500

        extension_video = generated_videos[0]
        extension_reference = extension_video.get("local_path") or extension_video.get("filename")
        if not extension_reference:
            return jsonify({"success": False, "error": "Generated video lacks a valid local reference."}), 500

        try:
            extension_video_path = resolve_local_media_path(extension_reference)
        except ValueError as exc:
            return jsonify({"success": False, "error": f"Invalid extension video reference: {exc}"}), 500

        try:
            combined_video = combine_videos_with_extension(
                base_video_path,
                extension_video_path,
                base_metadata=video_info,
                new_metadata=extension_video,
            )
        except Exception as exc:
            return jsonify({"success": False, "error": f"Unable to combine videos: {exc}"}), 500

        return jsonify({
            "success": True,
            "frame_image": last_frame_info,
            "generated_video": extension_video,
            "combined_video": combined_video,
            "prompt_id": generation_result.get("prompt_id"),
        })

    return video_bp

