
import os
from typing import Set

from notion_client import Client

# .envから各データベースIDを取得
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
FORM_DATABASE_ID = os.getenv("FORM_DATABASE_ID")
ASSETS_DATABASE_ID = os.getenv("ASSETS_DATABASE_ID")
DONE_MESSAGES_DATABASE_ID = os.getenv("DONE_MESSAGES_DATABASE_ID")

# Notionクライアントの初期化
notion = Client(auth=NOTION_API_KEY)


def query_done_message_ids() -> Set[str]:
    """DoneMessagesテーブルから処理済みの全メッセージIDを取得してセットで返す"""
    processed_ids = set()
    has_more = True
    start_cursor = None
    while has_more:
        response = notion.databases.query(
            database_id=DONE_MESSAGES_DATABASE_ID,
            start_cursor=start_cursor,
            page_size=100, # 1回のAPIコールで最大100件取得
        )
        for page in response.get("results", []):
            title_list = page.get("properties", {}).get("メッセージID", {}).get("title", [])
            if title_list:
                message_id = title_list[0].get("text", {}).get("content")
                if message_id:
                    processed_ids.add(message_id)
        has_more = response.get("has_more", False)
        start_cursor = response.get("next_cursor")
    print(f"Notionから{len(processed_ids)}件の処理済みメッセージIDを取得しました。")
    return processed_ids


def query_form_page_by_thread_id(thread_id: str) -> str | None:
    """スレッドIDを使ってFormテーブルを検索し、ページIDを返す"""
    try:
        response = notion.databases.query(
            database_id=FORM_DATABASE_ID,
            filter={"property": "スレッドID", "rich_text": {"equals": thread_id}},
        )
        results = response.get("results", [])
        if results:
            return results[0]["id"]
        return None
    except Exception as e:
        print(f"スレッドIDでのページ検索中にエラー: {e}")
        return None


def create_form_page(
    thread_name: str, thread_id: str, first_message_content: str, post_date: str, author_name: str
) -> str | None:
    """Formテーブルに新しいページを作成し、ページIDを返す"""
    try:
        properties = {
            "名前": {"title": [{"text": {"content": thread_name}}]},
            "スレッドID": {"rich_text": [{"text": {"content": thread_id}}]},
            "投稿日時": {"date": {"start": post_date}},
            "投稿者": {"rich_text": [{"text": {"content": author_name}}]}
        }
        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": first_message_content}}]}
            }
        ]
        response = notion.pages.create(
            parent={"database_id": FORM_DATABASE_ID},
            properties=properties,
            children=children
        )
        return response["id"]
    except Exception as e:
        print(f"Formページの新規作成中にエラー: {e}")
        return None


def append_text_to_page(page_id: str, content: str, author_name: str, post_time: str):
    """指定されたページに新しいテキストブロックを追記する"""
    try:
        header_text = f"--- {post_time} | {author_name} ---"
        blocks = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": header_text}}]}
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": content}}]}
            }
        ]
        notion.blocks.children.append(block_id=page_id, children=blocks)
    except Exception as e:
        print(f"ページ {page_id} へのブロック追記中にエラー: {e}")

def add_done_message(message_id: str, form_page_id: str):
    """DoneMessagesテーブルに処理済みメッセージを記録する"""
    try:
        properties = {
            "メッセージID": {"title": [{"text": {"content": message_id}}]},
            "関連スレッド": {"relation": [{"id": form_page_id}]}
        }
        notion.pages.create(
            parent={"database_id": DONE_MESSAGES_DATABASE_ID},
            properties=properties
        )
    except Exception as e:
        print(f"DoneMessageの記録中にエラー: {e}")

def create_asset_page(
    file_name: str, file_url: str, file_type: str, file_size: int, post_date: str
) -> str | None:
    """Assetsテーブルに新規ページを作成し、ページIDを返す"""
    try:
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
    except Exception as e:
        print(f"Assetページの作成中にエラー: {e}")
        return None

def relate_asset_to_form(form_page_id: str, asset_page_ids: list):
    """FormページとAssetページをリレーションで紐付ける"""
    if not asset_page_ids:
        return
    try:
        notion.pages.update(
            page_id=form_page_id,
            properties={
                "関連アセット": {"relation": [{"id": page_id} for page_id in asset_page_ids]}
            }
        )
    except Exception as e:
        print(f"FormとAssetのリレーション設定中にエラー: {e}")
