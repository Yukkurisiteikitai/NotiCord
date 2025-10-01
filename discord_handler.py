import os
from datetime import datetime, timedelta, timezone
import re

import discord
from discord.ext import commands

import google_drive_handler
import notion_handler
from utils import split_message, get_completion

# 環境変数から設定を取得
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))
IDEA_CHANNEL_ID = int(os.getenv("IDEA_CHANNEL_ID"))
GUILD_ID = os.getenv("GUILD_ID") # 即時反映させたいサーバーID(任意)

# Intents設定
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

# Botのインスタンスを作成
bot = commands.Bot(command_prefix="/", intents=intents)

# --- イベントリスナー ---
@bot.event
async def on_ready():
    """Botが起動したときのイベント"""
    print(f"{bot.user} としてログインしました")
    
    # スラッシュコマンドを同期
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        await bot.tree.sync(guild=guild)
        print(f"コマンドをサーバー {GUILD_ID} に同期しました。")
    else:
        await bot.tree.sync()
        print("コマンドをグローバルに同期しました。")

# --- スラッシュコマンド ---
@bot.tree.command(name="sync", description="DiscordのメッセージをNotionに手動で同期します。")
async def sync_command(interaction: discord.Interaction):
    """/syncコマンドの実装"""
    await interaction.response.defer(ephemeral=True)
    try:
        await sync_messages()
        await interaction.followup.send("同期が完了しました。")
    except Exception as e:
        print(f"同期中にエラーが発生しました: {e}")
        await interaction.followup.send(f"エラーが発生しました: {e}")

# --- 同期ロジック ---
async def get_today_messages(channel):
    """指定されたチャンネルから今日のメッセージを取得する。フォーラムとテキストチャンネルに対応。"""
    jst = timezone(timedelta(hours=+9), 'JST')
    today = datetime.now(jst).date()
    start_of_day = datetime.combine(today, datetime.min.time(), tzinfo=jst)
    
    messages = []

    async def fetch_and_filter(iterable):
        """メッセージを取得し、Bot自身の投稿を除外するヘルパー関数"""
        async for message in iterable:
            if message.author != bot.user:
                messages.append(message)

    # チャンネルタイプを判定
    if isinstance(channel, discord.ForumChannel):
        print("LoadType: Forumチャンネルからメッセージを読み込んでいます...")
        # アクティブなスレッドを処理
        for thread in channel.threads:
            await fetch_and_filter(thread.history(after=start_of_day, oldest_first=True))
        
        # アーカイブされたスレッドも確認
        async for thread in channel.archived_threads(limit=None):
            if thread.last_message_id:
                last_message_time = discord.utils.snowflake_time(thread.last_message_id).astimezone(jst)
                if last_message_time >= start_of_day:
                    await fetch_and_filter(thread.history(after=start_of_day, oldest_first=True))

    elif hasattr(channel, 'history'):
        print("LoadType: Textチャンネルからメッセージを読み込んでいます...")
        await fetch_and_filter(channel.history(after=start_of_day, oldest_first=True))
        
    else:
        print(f"エラー: チャンネル '{channel.name}' ({channel.type}) はメッセージ履歴をサポートしていません。")
        return []

    # 収集した全メッセージを投稿日時でソート
    messages.sort(key=lambda m: m.created_at)
    
    return messages

def build_prompt(message_content: str, notion_pages: list) -> str:
    """AIに投げるプロンプトを生成する（改良版）"""
    pages_list_str = "\n".join([f"- ID: {page['id']}, Title: {page['title']}" for page in notion_pages])
    prompt = f"""あなたは、与えられた情報を整理する専門家です。
以下の[新しいメッセージ]の内容を読み、[既存のNotionページリスト]の中から最も関連性の高いページを一つだけ選んでください。

# 指示
- 関連するページがリストにある場合は、そのページのIDだけを回答してください。
- 関連するページがリストにない場合は、必ず 'new' とだけ回答してください。
- IDや'new'以外の、いかなる説明や前置きも絶対に含めないでください。

[新しいメッセージ]
{message_content}

[既存のNotionページリスト]
{pages_list_str}

回答:"""
    return prompt

async def create_new_notion_page(message, post_date, post_time_str):
    """Notionに新しいページを作成する処理をまとめた関数"""
    title = f"{post_time_str} | {message.author.display_name}"
    
    asset_page_ids = []
    if message.attachments:
        print(f"    - 添付ファイルが{len(message.attachments)}件あります。")
        for attachment in message.attachments:
            try:
                file_url = await google_drive_handler.upload_to_drive(attachment)
                file_type = attachment.content_type.split('/')[0] if attachment.content_type else 'Unknown'
                asset_id = notion_handler.create_asset_page(
                    file_name=attachment.filename,
                    file_url=file_url,
                    file_type=file_type,
                    file_size=attachment.size,
                    post_date=post_date
                )
                asset_page_ids.append(asset_id)
            except Exception as e:
                print(f"    - 添付ファイルのアップロード中にエラー: {e}")

    notion_handler.create_form_page(
        title=title,
        message_content=message.content,
        post_date=post_date,
        author_name=message.author.display_name,
        asset_page_ids=asset_page_ids
    )

async def sync_messages():
    """Discord → Notionへの同期を実行するメインロジック（AI判断・検証機能あり）"""
    print("DiscordからNotionへのAI同期処理を開始します...")
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not channel:
        print(f"エラー: チャンネルが見つかりません: {TARGET_CHANNEL_ID}")
        return

    messages = await get_today_messages(channel)
    if not messages:
        print("同期対象の新しいメッセージはありません。")
        return

    print(f"{len(messages)}件の新規メッセージを処理します。")
    
    # Notionの既存ページリストを取得
    notion_pages = notion_handler.query_form_database()
    print(f"Notionから{len(notion_pages)}件の既存ページを取得しました。")
    # 検証のために、IDのセットを作成
    existing_page_ids = {p['id'] for p in notion_pages}

    for message in messages:
        jst_time = message.created_at.astimezone(timezone(timedelta(hours=+9), 'JST'))
        post_date = jst_time.isoformat()
        post_time_str = jst_time.strftime('%H:%M')

        # AIに関連ページを問い合わせ
        prompt = build_prompt(message.content, notion_pages)
        ai_response = get_completion(prompt)
        
        print(f"  - AI raw response: {ai_response}")

        if not ai_response:
            print(f"  - メッセージID {message.id} のAI判断を取得できませんでした。スキップします。")
            continue

        # 回答からページIDらしきものを抽出
        page_id_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', ai_response)
        
        page_to_update = None
        if page_id_match:
            potential_id = page_id_match.group(1)
            # ★★★ AIの回答を検証 ★★★
            if potential_id in existing_page_ids:
                page_to_update = potential_id
            else:
                print(f"  - AIの判断は幻覚でした (存在しないID: {potential_id})。新規ページを作成します。")

        if page_to_update:
            print(f"  - AIの判断: 既存ページに追記 (ID: {page_to_update})")
            notion_handler.append_block_to_page(
                page_id=page_to_update,
                content=message.content,
                author_name=message.author.display_name,
                post_time=post_time_str
            )
        else:
            if not page_id_match:
                 print(f"  - AIの判断: 新規ページ作成 (AIの応答: '{ai_response.strip()}')")
            await create_new_notion_page(message, post_date, post_time_str)

    print("同期処理が完了しました。")

async def send_message_to_discord(content: str):
    """Notion → Discordへの同期を実行するロジック"""
    channel = bot.get_channel(IDEA_CHANNEL_ID)
    if not channel:
        print(f"エラー: アイデアチャンネルが見つかりません: {IDEA_CHANNEL_ID}")
        return
        
    for chunk in split_message(content):
        await channel.send(chunk)