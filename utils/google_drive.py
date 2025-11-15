"""
Google Drive integration utilities
Functions for uploading files to Google Drive
"""
import os
import io
import requests
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError

# Scopes necesarios para Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_drive_service(credentials_dict):
    """Crear un servicio de Google Drive a partir de credenciales"""
    try:
        creds = Credentials.from_authorized_user_info(credentials_dict, SCOPES)
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        print(f"[GOOGLE_DRIVE] Error creating drive service: {e}")
        return None

def find_or_create_folder(service, folder_name, parent_folder_id=None):
    """Buscar una carpeta por nombre, o crearla si no existe"""
    try:
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_folder_id:
            query += f" and '{parent_folder_id}' in parents"
        else:
            query += " and 'root' in parents"
        
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        folders = results.get('files', [])
        
        if folders:
            # La carpeta ya existe
            return folders[0]['id']
        else:
            # Crear la carpeta
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_folder_id:
                folder_metadata['parents'] = [parent_folder_id]
            
            folder = service.files().create(
                body=folder_metadata,
                fields='id, name'
            ).execute()
            
            print(f"[GOOGLE_DRIVE] Created folder: {folder_name} (ID: {folder.get('id')})")
            return folder.get('id')
    except Exception as e:
        print(f"[GOOGLE_DRIVE] Error finding/creating folder '{folder_name}': {e}")
        return None

def get_upload_folder_id(service):
    """Obtener el ID de la carpeta de destino: ai_creator/ddmmyyyy"""
    try:
        # Crear o encontrar la carpeta base 'ai_creator'
        base_folder_id = find_or_create_folder(service, 'ai_creator')
        if not base_folder_id:
            return None
        
        # Crear o encontrar la carpeta de fecha (formato: ddmmyyyy)
        date_str = datetime.now().strftime('%d%m%Y')
        date_folder_id = find_or_create_folder(service, date_str, base_folder_id)
        
        return date_folder_id
    except Exception as e:
        print(f"[GOOGLE_DRIVE] Error getting upload folder ID: {e}")
        return None

def upload_file_to_drive(service, file_content, filename, mime_type='image/png', folder_id=None):
    """Subir un archivo a Google Drive"""
    try:
        # Si no se especifica folder_id, usar la carpeta por defecto ai_creator/ddmmyyyy
        if folder_id is None:
            folder_id = get_upload_folder_id(service)
            if not folder_id:
                return {
                    'success': False,
                    'error': 'Failed to get or create upload folder'
                }
        
        file_metadata = {'name': filename}
        if folder_id:
            file_metadata['parents'] = [folder_id]
        
        media = MediaIoBaseUpload(
            io.BytesIO(file_content),
            mimetype=mime_type,
            resumable=True
        )
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()
        
        return {
            'success': True,
            'file_id': file.get('id'),
            'file_name': file.get('name'),
            'web_view_link': file.get('webViewLink')
        }
    except HttpError as e:
        print(f"[GOOGLE_DRIVE] Error uploading file: {e}")
        return {
            'success': False,
            'error': str(e)
        }
    except Exception as e:
        print(f"[GOOGLE_DRIVE] Unexpected error: {e}")
        return {
            'success': False,
            'error': str(e)
        }

def get_authorization_url(redirect_uri, client_id, client_secret):
    """Obtener URL de autorización para Google Drive"""
    try:
        print(f"[GOOGLE_DRIVE] Building authorization URL with:")
        print(f"  - Redirect URI: {redirect_uri}")
        print(f"  - Client ID: {client_id}")
        print(f"  - Scopes: {SCOPES}")
        
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri]
                }
            },
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='false',
            prompt='consent'
        )
        print(f"[GOOGLE_DRIVE] Authorization URL generated successfully")
        print(f"[GOOGLE_DRIVE] State: {state}")
        return authorization_url, state
    except Exception as e:
        print(f"[GOOGLE_DRIVE] Error getting authorization URL: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def exchange_code_for_credentials(code, redirect_uri, client_id, client_secret, scopes=None):
    """Intercambiar código de autorización por credenciales"""
    try:
        effective_scopes = scopes or SCOPES
        print(f"[GOOGLE_DRIVE] Exchanging code with scopes: {effective_scopes}")
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri]
                }
            },
            scopes=effective_scopes,
            redirect_uri=redirect_uri
        )
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        return {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
    except Exception as e:
        print(f"[GOOGLE_DRIVE] Error exchanging code: {e}")
        return None

