# routes/social_routes.py
from flask import Blueprint, request, jsonify, current_app, session, redirect, url_for
import os
import tweepy
from auth import api_login_required

def create_social_blueprint(app):
    social_blueprint = Blueprint('social', __name__)

    def get_twitter_api():
        consumer_key = os.getenv('TWITTER_CONSUMER_KEY')
        consumer_secret = os.getenv('TWITTER_CONSUMER_SECRET')
        access_token = session.get('twitter_access_token')
        access_token_secret = session.get('twitter_access_token_secret')

        if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
            return None

        auth = tweepy.OAuth1UserHandler(consumer_key, consumer_secret, access_token, access_token_secret)
        return tweepy.API(auth)

    @social_blueprint.route('/api/social/twitter/authorize', methods=['GET'])
    @api_login_required(app)
    def twitter_authorize():
        consumer_key = os.getenv('TWITTER_CONSUMER_KEY')
        consumer_secret = os.getenv('TWITTER_CONSUMER_SECRET')

        if not consumer_key or not consumer_secret:
            return jsonify({'success': False, 'error': 'Twitter API credentials not configured.'}), 500

        auth = tweepy.OAuth1UserHandler(consumer_key, consumer_secret, callback=url_for('social.twitter_callback', _external=True))

        try:
            redirect_url = auth.get_authorization_url()
            session['twitter_request_token'] = auth.request_token
            return jsonify({'success': True, 'authorization_url': redirect_url})
        except tweepy.errors.TweepyException as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @social_blueprint.route('/api/social/twitter/callback', methods=['GET'])
    def twitter_callback():
        request_token = session.pop('twitter_request_token', None)
        verifier = request.args.get('oauth_verifier')

        if not request_token or not verifier:
            return redirect(url_for('index', social_auth='failed'))

        consumer_key = os.getenv('TWITTER_CONSUMER_KEY')
        consumer_secret = os.getenv('TWITTER_CONSUMER_SECRET')
        auth = tweepy.OAuth1UserHandler(consumer_key, consumer_secret)
        auth.request_token = request_token

        try:
            access_token, access_token_secret = auth.get_access_token(verifier)
            session['twitter_access_token'] = access_token
            session['twitter_access_token_secret'] = access_token_secret
            return redirect(url_for('index', social_auth='success'))
        except tweepy.errors.TweepyException as e:
            return redirect(url_for('index', social_auth='failed'))

    @social_blueprint.route('/api/social/twitter/upload', methods=['POST'])
    @api_login_required(app)
    def twitter_upload():
        data = request.get_json()
        image_url = data.get('image_url')
        status = data.get('status', 'Generated with AI Content Creator!')

        if not image_url:
            return jsonify({'success': False, 'error': 'Image URL is required.'}), 400

        api = get_twitter_api()
        if not api:
            return jsonify({'success': False, 'error': 'User is not authenticated with Twitter.', 'requires_auth': True}), 401

        try:
            from urllib.parse import urlparse, parse_qs
            from utils.media import resolve_local_media_path

            parsed_url = urlparse(image_url)
            filename = os.path.basename(parsed_url.path)

            # Asumimos que la imagen es local y usamos la misma lógica que /api/image para resolver la ruta
            local_path = resolve_local_media_path(filename)

            if not os.path.exists(local_path):
                 return jsonify({'success': False, 'error': 'Image file not found on server.'}), 404

            with open(local_path, 'rb') as image_file:
                media = api.media_upload(filename=filename, file=image_file)
                api.update_status(status=status, media_ids=[media.media_id_string])

            return jsonify({'success': True, 'message': 'Image uploaded to Twitter successfully.'})
        except tweepy.errors.TweepyException as e:
            return jsonify({'success': False, 'error': str(e)}), 500
        except Exception as e:
            return jsonify({'success': False, 'error': 'An unexpected error occurred.'}), 500

    return social_blueprint
