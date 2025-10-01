import os
import re
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
import discord.app_commands

import google_drive_handler
import notion_handler
import AI_handler
from utils import split_message

# 環境変数から設定を取得
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))
IDEA_CHANNEL_ID = int(os.getenv("IDEA_CHANNEL_ID"))
GUILD_ID = os.getenv("GUILD_ID")  # 即時反映させたいサーバーID(任意)

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
    """/syncコマンドの実装。詳細な結果を返すように変更。"""
    await interaction.response.defer(ephemeral=True)
    try:
        result = await sync_messages()

        if result["status"] == "SUCCESS":
            summary = result.get("summary", [])
            if not summary:
                await interaction.followup.send("同期対象となる新しいメッセージはありませんでした。")
                return

            message_lines = ["同期成功です。"]
            message_lines.extend(f"- {s}" for s in summary[:3])
            if len(summary) > 3:
                message_lines.append(f"...他{len(summary) - 3}件の処理を行いました。")
            await interaction.followup.send("\n".join(message_lines))

        elif result["status"] == "NO_NEW_MESSAGES":
            await interaction.followup.send("全て同期済みです。")

        elif result["status"] == "ERROR":
            error_msg = result.get("error_message", "不明なエラー")
            await interaction.followup.send(f"同期エラーが発生しました:\n`{error_msg}`")

    except Exception as e:
        print(f"sync_commandで予期せぬエラーが発生しました: {e}")
        await interaction.followup.send(f"予期せぬ重大なエラーが発生しました:\n`{e}`")


@bot.tree.command(name="summarize", description="指定したNotionページの議論をAIが要約します。")
@discord.app_commands.describe(url="要約したいNotionページのURL")
async def summarize_command(interaction: discord.Interaction, url: str):
    """/summarizeコマンドの実装"""
    await interaction.response.defer(ephemeral=True)
    await interaction.followup.send(f"要約処理を開始します...これには数分かかる場合があります。")

    # 1. URLからNotionのページIDを抽出
    match = re.search(r'([a-f0-9]{32})$', url.split('?')[0])
    if not match:
        await interaction.edit_original_response(content="無効なNotionページURLです。URLの末尾が32文字のIDであることを確認してください。")
        return
    page_id = match.group(1)

    try:
        # 2. Notionからページの全テキストを取得
        print(f"Notionページ ({page_id}) からテキストを取得中...")
        text_content = notion_handler.get_all_text_from_page(page_id)
        if not text_content:
            await interaction.edit_original_response(content=f"ページにテキストが見つかりませんでした。 (ID: {page_id})")
            return

        # 3. AIハンドラに要約を依頼
        print("AIに要約を依頼中...")
        summary = AI_handler.generate_knowledge_from_text(text_content)
        if not summary:
            await interaction.edit_original_response(content="AIによる要約の生成に失敗しました。LM-Studioのログを確認してください。")
            return

        # 4. 要約をNotionページに追記
        print("要約をNotionページに書き込み中...")
        notion_handler.add_summary_to_page(page_id, summary)

        # 5. 完了を通知
        await interaction.edit_original_response(content=f"要約が完了しました！\nNotionページに結果を追記しましたので、ご確認ください。\n{url}")

    except Exception as e:
        print(f"要約処理中にエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        await interaction.edit_original_response(content=f"要約処理中にエラーが発生しました。詳細はBotのログを確認してください。\n`{e}`")


# --- 同期ロジック ---
async def get_today_messages(channel):
    jst = timezone(timedelta(hours=+9), 'JST')
    today = datetime.now(jst).date()
    start_of_day = datetime.combine(today, datetime.min.time(), tzinfo=jst)
    messages = []
    async def fetch_and_filter(iterable):
        async for message in iterable:
            if message.author != bot.user:
                messages.append(message)
    if isinstance(channel, discord.ForumChannel):
        print("LoadType: Forumチャンネルからメッセージを読み込んでいます...")
        for thread in channel.threads:
            await fetch_and_filter(thread.history(after=start_of_day, oldest_first=True))
        async for thread in channel.archived_threads(limit=None):
            if thread.last_message_id and discord.utils.snowflake_time(thread.last_message_id).astimezone(jst) >= start_of_day:
                await fetch_and_filter(thread.history(after=start_of_day, oldest_first=True))
    elif hasattr(channel, 'history'):
        print("LoadType: Textチャンネルからメッセージを読み込んでいます...")
        await fetch_and_filter(channel.history(after=start_of_day, oldest_first=True))
    else:
        print(f"エラー: チャンネル '{channel.name}' ({channel.type}) はメッセージ履歴をサポートしていません。")
        return []
    messages.sort(key=lambda m: m.created_at)
    return messages


async def sync_messages() -> dict:
    """同期処理を行い、結果を辞書型で返す"""
    try:
        print("DiscordからNotionへのIDベース同期処理を開始します...")
        summary_logs = []

        processed_message_ids = notion_handler.query_done_message_ids()

        channel = bot.get_channel(TARGET_CHANNEL_ID)
        if not channel:
            return {"status": "ERROR", "error_message": f"チャンネルが見つかりません: {TARGET_CHANNEL_ID}"}
        
        messages = await get_today_messages(channel)
        if not messages:
            print("同期対象の新しいメッセージはありません。")
            return {"status": "NO_NEW_MESSAGES"}

        unprocessed_messages = [m for m in messages if str(m.id) not in processed_message_ids]
        print(f"{len(unprocessed_messages)}件の未処理メッセージを処理します。")
        if not unprocessed_messages:
            return {"status": "SUCCESS", "summary": []}

        for message in unprocessed_messages:
            if not isinstance(message.channel, discord.Thread):
                continue

            thread_id = str(message.channel.id)
            thread_name = message.channel.name
            form_page_id = notion_handler.query_form_page_by_thread_id(thread_id)
            jst_time = message.created_at.astimezone(timezone(timedelta(hours=+9), 'JST'))

            if not form_page_id:
                form_page_id = notion_handler.create_form_page(
                    thread_name=thread_name, thread_id=thread_id,
                    first_message_content=message.content, post_date=jst_time.isoformat(),
                    author_name=message.author.display_name
                )
                if not form_page_id:
                    summary_logs.append(f"スレッド「{thread_name}」のページ作成に失敗しました。")
                    continue
                summary_logs.append(f"スレッド「{thread_name}」を新規作成し、メッセージを追加しました。")
            else:
                notion_handler.append_text_to_page(
                    page_id=form_page_id, content=message.content,
                    author_name=message.author.display_name, post_time=jst_time.strftime('%H:%M')
                )
                summary_logs.append(f"スレッド「{thread_name}」に{message.author.display_name}のメッセージを追加しました。")

            if message.attachments:
                asset_page_ids = []
                for attachment in message.attachments:
                    file_url = await google_drive_handler.upload_to_drive(attachment)
                    if file_url:
                        asset_id = notion_handler.create_asset_page(
                            file_name=attachment.filename, file_url=file_url,
                            file_type=attachment.content_type or 'Unknown',
                            file_size=attachment.size, post_date=jst_time.isoformat()
                        )
                        if asset_id:
                            asset_page_ids.append(asset_id)
                if asset_page_ids:
                    notion_handler.relate_asset_to_form(form_page_id, asset_page_ids)
                    summary_logs[-1] += f"（添付ファイル{len(asset_page_ids)}件を含む）"

            notion_handler.add_done_message(str(message.id), form_page_id)

        print("同期処理が正常に完了しました。")
        return {"status": "SUCCESS", "summary": summary_logs}

    except Exception as e:
        print(f"sync_messagesでエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "ERROR", "error_message": str(e)}


async def send_message_to_discord(content: str):
    channel = bot.get_channel(IDEA_CHANNEL_ID)
    if not channel:
        print(f"エラー: アイデアチャンネルが見つかりません: {IDEA_CHANNEL_ID}")
        return
    for chunk in split_message(content):
        await channel.send(chunk)