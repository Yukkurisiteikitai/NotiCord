import io
import os

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# 環境変数から情報を取得
SCOPES = ['https://www.googleapis.com/auth/drive']
CLIENT_SECRETS_FILE = os.getenv("GOOGLE_DRIVE_CREDENTIALS")
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
TOKEN_FILE = "token.json"

def get_drive_service():
    """Google Drive APIサービスを取得する (OAuth 2.0 フロー)"""
    creds = None
    # token.json があれば、そこから認証情報を読み込む
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    # 認証情報がない、または無効な場合
    if not creds or not creds.valid:
        # 認証情報が期限切れの場合、リフレッシュする
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        # 認証情報がない場合、ユーザーに認証フローを要求する
        else:
            print("Google Driveの認証が必要です。ブラウザを開きます...")
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # 新しい認証情報を token.json に保存する
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            print(f"認証情報を {TOKEN_FILE} に保存しました。")

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

    # 公開権限設定は不要（自分のドライブ内のファイルなので、リンクを知っていれば見れる）
    # もし必要であれば、以下のコメントを解除
    # drive_service.permissions().create(
    #     fileId=file['id'],
    #     body={'type': 'anyone', 'role': 'reader'}
    # ).execute()

    return file['webViewLink']