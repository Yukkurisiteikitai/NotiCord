import io
import os

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# 環境変数から情報を取得
SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_DRIVE_CREDENTIALS")
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

def get_drive_service():
    """Google Drive APIサービスを取得する"""
    creds = None
    if SERVICE_ACCOUNT_FILE:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

async def upload_to_drive(attachment) -> str:
    """ファイルをGDriveにアップロードし永続URLを返す"""
    drive_service = get_drive_service()

    # Discord CDNからダウンロード
    response = requests.get(attachment.url)
    file_content = io.BytesIO(response.content)

    # GDriveにアップロード
    file_metadata = {
        'name': attachment.filename,
        'parents': [DRIVE_FOLDER_ID]
    }
    media = MediaIoBaseUpload(file_content, mimetype=attachment.content_type)

    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()

    # 公開権限設定
    drive_service.permissions().create(
        fileId=file['id'],
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()

    return file['webViewLink']
