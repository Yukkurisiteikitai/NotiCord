import os
import asyncio
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# 環境変数を読み込んだ後にモジュールをインポートする
import discord_handler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

async def main():
    """スケジューラとDiscord Botをセットアップして実行する"""
    # スケジューラの初期化とジョブの追加
    scheduler = AsyncIOScheduler(timezone='Asia/Tokyo')
    scheduler.add_job(
        discord_handler.sync_messages, 
        CronTrigger(hour='12,0', minute='0', second='0')
    )
    scheduler.start()
    print("スケジューラを開始しました。")

    # Discord Botの起動
    # client.start()は非同期にBotを起動する
    await discord_handler.bot.start(discord_handler.DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    print("アプリケーションを起動します...")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("アプリケーションを終了します。")