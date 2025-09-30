import os
from notion_client import Client

# 環境変数から情報を取得
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
FORM_DATABASE_ID = os.getenv("FORM_DATABASE_ID")
ASSETS_DATABASE_ID = os.getenv("ASSETS_DATABASE_ID")

# Notionクライアントの初期化
notion = Client(auth=NOTION_API_KEY)

def create_asset_page(file_name: str, file_url: str, file_type: str, file_size: int, post_date) -> str:
    """Assetsテーブルに新規ページを作成し、ページIDを返す"""
    properties = {
        "ファイル名": {"title": [{"text": {"content": file_name}}]},
        "ファイルURL": {"url": file_url},
        "ファイル種別": {"select": {"name": file_type}},
        "ファイルサイズ": {"number": file_size},
        "投稿日時": {"date": {"start": post_date}}
    }
    
    response = notion.pages.create(
        parent={"database_id": ASSETS_DATABASE_ID},
        properties=properties
    )
    return response["id"]

def create_form_page(title: str, message_content: str, post_date, author_name: str, asset_page_ids: list = None):
    """Formテーブルに新規ページを作成する"""
    properties = {
        "名前": {"title": [{"text": {"content": title}}]},
        "メッセージ本文": {"rich_text": [{"text": {"content": message_content}}]},
        "投稿日時": {"date": {"start": post_date}},
        "投稿者": {"rich_text": [{"text": {"content": author_name}}]}
    }

    if asset_page_ids:
        properties["関連アセット"] = {"relation": [{"id": page_id} for page_id in asset_page_ids]}

    notion.pages.create(
        parent={"database_id": FORM_DATABASE_ID},
        properties=properties
    )

def get_new_pages_from_notion():
    """Notionから新規または更新されたページを取得する"""
    # この機能は、最終同期時刻を記録・比較するロジックが必要なため、
    # まずはプレースホルダーとして関数を定義します。
    # 実際のロジックはmain.pyでの状態管理と合わせて実装します。
    pass
