import os
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

import google_drive_handler
import notion_handler
from utils import split_message

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
    # GUILD_IDが設定されていれば、そのサーバーに即時反映
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        await bot.tree.sync(guild=guild)
        print(f"コマンドをサーバー {GUILD_ID} に同期しました。")
    else:
        # グローバルに同期（反映に時間がかかる場合があります）
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

async def sync_messages():
    """Discord → Notionへの同期を実行するメインロジック"""
    print("DiscordからNotionへの同期処理を開始します...")
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not channel:
        print(f"エラー: チャンネルが見つかりません: {TARGET_CHANNEL_ID}")
        return

    messages = await get_today_messages(channel)
    print(f"{len(messages)}件の新規メッセージが見つかりました。")

    for message in messages:
        jst_time = message.created_at.astimezone(timezone(timedelta(hours=+9), 'JST'))
        post_date = jst_time.isoformat()
        title = f"{jst_time.strftime('%H:%M')} | {message.author.display_name}"
        
        asset_page_ids = []
        if message.attachments:
            print(f"  - 添付ファイルが{len(message.attachments)}件あります。")
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
    print("同期処理が完了しました。")

async def send_message_to_discord(content: str):
    """Notion → Discordへの同期を実行するロジック"""
    channel = bot.get_channel(IDEA_CHANNEL_ID)
    if not channel:
        print(f"エラー: アイデアチャンネルが見つかりません: {IDEA_CHANNEL_ID}")
        return
        
    # 2000文字を超える場合は分割して送信
    for chunk in split_message(content):
        await channel.send(chunk)