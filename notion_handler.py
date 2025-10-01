import os
from notion_client import Client
from typing import List, Dict, Any

# 環境変数から情報を取得
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
FORM_DATABASE_ID = os.getenv("FORM_DATABASE_ID")
ASSETS_DATABASE_ID = os.getenv("ASSETS_DATABASE_ID")

# Notionクライアントの初期化
notion = Client(auth=NOTION_API_KEY)

def create_asset_page(file_name: str, file_url: str, file_type: str, file_size: int, post_date: str) -> str:
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

def create_form_page(title: str, message_content: str, post_date: str, author_name: str, asset_page_ids: List[str] = None):
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

def query_form_database() -> List[Dict[str, Any]]:
    """Formデータベースの全ページを取得し、IDとタイトルを返す"""
    try:
        response = notion.databases.query(database_id=FORM_DATABASE_ID)
        pages = []
        for page in response.get("results", []):
            title_list = page.get("properties", {}).get("名前", {}).get("title", [])
            if title_list:
                pages.append({
                    "id": page["id"],
                    "title": title_list[0].get("text", {}).get("content", "")
                })
        return pages
    except Exception as e:
        print(f"Notionデータベースのクエリ中にエラーが発生しました: {e}")
        return []

def append_block_to_page(page_id: str, content: str, author_name: str, post_time: str):
    """指定されたページに新しいコンテンツブロックを追記する"""
    try:
        # 追記するコンテンツのヘッダー
        header_text = f"--- {post_time} | {author_name} ---"
        
        # Notion APIが受け入れるブロック形式に変換
        blocks = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": header_text}}]
                }
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                }
            }
        ]
        
        notion.blocks.children.append(block_id=page_id, children=blocks)
    except Exception as e:
        print(f"ページ {page_id} へのブロック追記中にエラーが発生しました: {e}")


def get_new_pages_from_notion():
    """Notionから新規または更新されたページを取得する"""
    # この機能は、最終同期時刻を記録・比較するロジックが必要なため、
    # まずはプレースホルダーとして関数を定義します。
    # 実際のロジックはmain.pyでの状態管理と合わせて実装します。
    pass