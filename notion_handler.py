
import os
from typing import Set, List, Dict, Any

from notion_client import Client

# .envから各データベースIDを取得
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
FORM_DATABASE_ID = os.getenv("FORM_DATABASE_ID")
ASSETS_DATABASE_ID = os.getenv("ASSETS_DATABASE_ID")
DONE_MESSAGES_DATABASE_ID = os.getenv("DONE_MESSAGES_DATABASE_ID")

# Notionクライアントの初期化
notion = Client(auth=NOTION_API_KEY)


def _get_text_from_rich_text(rich_text: List[Dict[str, Any]]) -> str:
    """リッチテキストオブジェクトから結合されたテキストを抽出する"""
    return "".join([t.get("plain_text", "") for t in rich_text])


def _get_all_blocks_recursive(block_id: str) -> List[Dict[str, Any]]:
    """指定されたブロックIDの子ブロックを再帰的にすべて取得する"""
    all_blocks = []
    has_more = True
    start_cursor = None
    while has_more:
        response = notion.blocks.children.list(
            block_id=block_id, start_cursor=start_cursor, page_size=100
        )
        blocks = response.get("results", [])
        all_blocks.extend(blocks)
        has_more = response.get("has_more", False)
        start_cursor = response.get("next_cursor")

    for block in all_blocks:
        if block.get("has_children"):
            block["children"] = _get_all_blocks_recursive(block["id"])

    return all_blocks


def get_all_text_from_page(page_id: str) -> str:
    """ページの全ブロックからテキストを抽出し、一つの文字列として結合して返す"""
    try:
        all_blocks = _get_all_blocks_recursive(page_id)
        text_parts = []

        def extract_text(blocks: List[Dict[str, Any]]):
            for block in blocks:
                block_type = block.get("type")
                if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item", "quote", "callout", "toggle"]:
                    text_parts.append(_get_text_from_rich_text(block[block_type]["rich_text"]))
                
                if block.get("has_children"):
                    extract_text(block.get("children", []))

        extract_text(all_blocks)
        print(f"ページID {page_id} からテキストの抽出が完了しました。")
        return "\n".join(text_parts)
    except Exception as e:
        print(f"ページ {page_id} からのテキスト抽出中にエラー: {e}")
        return ""


def add_summary_to_page(page_id: str, summary_text: str):
    """指定されたページの末尾に、AIによる要約を見出し付きで追記する"""
    try:
        # 2000文字ごとにチャンクに分割（Notionのブロック上限を考慮）
        chunks = [summary_text[i:i + 2000] for i in range(0, len(summary_text), 2000)]
        quote_blocks = [{"object": "block", "type": "quote", "quote": {"rich_text": [{"type": "text", "text": {"content": chunk}}]}} for chunk in chunks]

        blocks_to_append = [
            {
                "object": "block", 
                "type": "divider", 
                "divider": {}
            },
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                        "rich_text": [
                            {
                                "type": "text", 
                                "text": {
                                    "content": "🤖 AIによる要約"
                                }
                            }
                        ]
                    }
            },
            *quote_blocks
        ]
        notion.blocks.children.append(block_id=page_id, children=blocks_to_append)
        print(f"ページ {page_id} にAIによる要約を追記しました。")
    except Exception as e:
        print(f"ページ {page_id} への要約追記中にエラー: {e}")


def query_done_message_ids() -> Set[str]:
    processed_ids = set()
    has_more = True
    start_cursor = None
    while has_more:
        response = notion.databases.query(
            database_id=DONE_MESSAGES_DATABASE_ID,
            start_cursor=start_cursor,
            page_size=100,
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
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": first_message_content}}]
                              }
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
    try:
        header_text = f"--- {post_time} | {author_name} ---"
        blocks = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": header_text}}]}
            }
            ,
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
    try:
        properties = {
            "メッセージID": {"title": [{"text": {"content": message_id}}],},
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
    try:
        properties = {
            "ファイル名": {"title": [{"text": {"content": file_name}}],},
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
