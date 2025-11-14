"""
Authentication routes
"""
import uuid
import pyotp
from flask import Blueprint, render_template, request, redirect, url_for, session, abort
from authlib.integrations.flask_client import OAuth
from auth import (
    is_user_allowed, get_user_totp_secret, ensure_user_totp_secret,
    get_next_url, generate_qr_code,
    TOTP_SECRETS, save_totp_secrets, auth_logger
)
import traceback

def create_auth_blueprint(app, oauth):
    """Crear blueprint de autenticación"""
    auth_bp = Blueprint('auth', __name__)

    @auth_bp.route('/login')
    def login_page():
        if not app.config.get('ENABLE_OAUTH_LOGIN'):
            return redirect(url_for('index'))
        if is_authenticated(app):
            return redirect(url_for('index'))

        error_code = request.args.get('error')
        error_messages = {
            'unauthorized': 'Access denied for this account.',
            'oauth_error': 'Authentication failed. Please try again.',
            '2fa_failed': 'Invalid verification code. Please try again.',
        }
        error_message = error_messages.get(error_code)
        next_url = request.args.get('next') or session.get('next_url') or '/'
        return render_template('login.html', error=error_message, next_url=next_url)

    @auth_bp.route('/auth/google')
    def auth_google():
        if not app.config.get('ENABLE_OAUTH_LOGIN'):
            return redirect(url_for('auth.login_page'))
        next_url = request.args.get('next') or request.referrer or '/'
        session['next_url'] = next_url
        if not (app.config.get('GOOGLE_CLIENT_ID') and app.config.get('GOOGLE_CLIENT_SECRET')):
            abort(503, description="Google OAuth is not configured.")
        google = oauth.create_client('google')
        redirect_uri = url_for('auth.auth_google_callback', _external=True)
        nonce = uuid.uuid4().hex
        session['oauth_nonce'] = nonce
        return google.authorize_redirect(redirect_uri, nonce=nonce)

    @auth_bp.route('/auth/google/callback')
    def auth_google_callback():
        if not app.config.get('ENABLE_OAUTH_LOGIN'):
            return redirect(url_for('auth.login_page'))
        if not (app.config.get('GOOGLE_CLIENT_ID') and app.config.get('GOOGLE_CLIENT_SECRET')):
            abort(503, description="Google OAuth is not configured.")
        google = oauth.create_client('google')
        try:
            token = google.authorize_access_token()
            nonce = session.pop('oauth_nonce', None)
            userinfo = google.parse_id_token(token, nonce=nonce)
            if not userinfo:
                userinfo = google.get('userinfo').json()
            auth_logger.info(
                "OAuth callback success. token_keys=%s userinfo_keys=%s",
                list((token or {}).keys()),
                list((userinfo or {}).keys()),
            )
        except Exception as exc:
            auth_logger.error("OAuth callback error: %s", exc)
            auth_logger.error("Traceback: %s", traceback.format_exc())
            session.clear()
            return redirect(url_for('auth.login_page', error='oauth_error'))

        email = (userinfo or {}).get('email')
        sub = (userinfo or {}).get('sub')
        if not email or not sub:
            auth_logger.warning("OAuth callback missing email/sub. userinfo=%s", userinfo)
            session.clear()
            return redirect(url_for('auth.login_page', error='oauth_error'))

        if not is_user_allowed(email):
            auth_logger.info("OAuth login rejected (not allowed): %s", email)
            session.clear()
            return redirect(url_for('auth.login_page', error='unauthorized'))

        auth_logger.info("OAuth login accepted for %s (sub=%s)", email.lower(), sub)

        session['user_email'] = email.lower()
        session['google_sub'] = sub
        session['pending_2fa'] = True
        session.pop('2fa_verified', None)

        secret = get_user_totp_secret(email)
        if secret:
            session.pop('needs_2fa_setup', None)
            return redirect(url_for('auth.two_factor'))

        ensure_user_totp_secret(email)
        session['needs_2fa_setup'] = True
        return redirect(url_for('auth.two_factor_setup'))

    @auth_bp.route('/2fa', methods=['GET', 'POST'])
    def two_factor():
        if not app.config.get('ENABLE_OAUTH_LOGIN'):
            return redirect(url_for('index'))
        email = session.get('user_email')
        if not session.get('pending_2fa') or not email:
            return redirect(url_for('auth.login_page'))

        if session.get('needs_2fa_setup'):
            return redirect(url_for('auth.two_factor_setup'))

        secret = get_user_totp_secret(email)
        if not secret:
            session['needs_2fa_setup'] = True
            return redirect(url_for('auth.two_factor_setup'))

        error = None
        if request.method == 'POST':
            code = (request.form.get('code') or '').strip()
            totp = pyotp.TOTP(secret)
            if totp.verify(code, valid_window=1):
                auth_logger.info("2FA verification success for %s", email)
                session['2fa_verified'] = True
                session['pending_2fa'] = False
                session.pop('needs_2fa_setup', None)
                return redirect(get_next_url(url_for('index')))
            error = 'Invalid verification code. Try again.'
            auth_logger.warning("2FA verification failed for %s", email)

        return render_template('two_factor_verify.html', error=error)

    @auth_bp.route('/2fa/setup', methods=['GET', 'POST'])
    def two_factor_setup():
        if not app.config.get('ENABLE_OAUTH_LOGIN'):
            return redirect(url_for('index'))
        email = session.get('user_email')
        if not session.get('pending_2fa') or not email:
            return redirect(url_for('auth.login_page'))

        secret = ensure_user_totp_secret(email)
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(name=email, issuer_name=app.config.get('TOTP_ISSUER', 'AI Content Creator'))

        qr_b64 = generate_qr_code(provisioning_uri)

        error = None
        if request.method == 'POST':
            code = (request.form.get('code') or '').strip()
            if totp.verify(code, valid_window=1):
                auth_logger.info("2FA setup complete for %s", email)
                session['2fa_verified'] = True
                session['pending_2fa'] = False
                session.pop('needs_2fa_setup', None)
                return redirect(get_next_url(url_for('index')))
            error = 'Invalid verification code. Try again.'
            auth_logger.warning("2FA setup failed (bad code) for %s", email)

        return render_template(
            'two_factor_setup.html',
            qr_code=qr_b64,
            provisioning_uri=provisioning_uri,
            error=error,
        )

    @auth_bp.route('/logout')
    def logout():
        if not app.config.get('ENABLE_OAUTH_LOGIN'):
            session.clear()
            return redirect(url_for('index'))
        session.clear()
        return redirect(url_for('auth.login_page'))

    return auth_bp

