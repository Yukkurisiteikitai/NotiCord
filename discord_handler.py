import os
import discord
from discord import app_commands
from datetime import datetime, timedelta, timezone

import notion_handler
import google_drive_handler

# 環境変数から情報を取得
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@tree.command(name="sync", description="DiscordのメッセージをNotionに同期します")
async def sync_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await sync_messages()
    await interaction.followup.send("同期が完了しました。")

async def get_today_messages(channel):
    """指定されたチャンネルから今日のメッセージを取得する"""
    jst = timezone(timedelta(hours=+9), 'JST')
    today = datetime.now(jst).date()
    start_of_day = datetime.combine(today, datetime.min.time(), tzinfo=jst)
    
    messages = []
    async for message in channel.history(after=start_of_day, oldest_first=True):
        messages.append(message)
    return messages

async def sync_messages():
    """メッセージをNotionに同期するメインロジック"""
    channel = client.get_channel(TARGET_CHANNEL_ID)
    if not channel:
        print(f"チャンネルが見つかりません: {TARGET_CHANNEL_ID}")
        return

    messages = await get_today_messages(channel)

    for message in messages:
        jst_time = message.created_at.astimezone(timezone(timedelta(hours=+9), 'JST'))
        post_date = jst_time.isoformat()
        title = f"{jst_time.strftime('%H:%M')} | {message.author.display_name}"
        
        asset_page_ids = []
        if message.attachments:
            for attachment in message.attachments:
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

        notion_handler.create_form_page(
            title=title,
            message_content=message.content,
            post_date=post_date,
            author_name=message.author.display_name,
            asset_page_ids=asset_page_ids
        )

@client.event
async def on_ready():
    print(f'{client.user} としてログインしました')
    await tree.sync()
    print("コマンドツリーを同期しました。")

def run_bot():
    # client.run()はブロッキング呼び出しのため、
    # スケジューラと並行で動かすには工夫が必要です。
    # main.pyで非同期に実行します。
    pass
