import os
import discord
from discord.ext import commands, tasks
import httpx
from dotenv import load_dotenv

# .env ファイルから環境変数を読み込む
load_dotenv()

# 環境変数から設定を取得
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
LM_STUDIO_API_URL = os.getenv("LM_STUDIO_API_URL")
MODEL = os.getenv("MODEL")

# Discord Intents の設定
# メッセージ内容を読み取るために MessageContent Intent が必須です
intents = discord.Intents.default()
intents.message_content = True
intents.members = True # メンバー情報を取得するために必要 (ここでは直接使わないが、念のため)

# BotのプレフィックスとIntentsを指定
bot = commands.Bot(command_prefix='!', intents=intents)

# 監視対象のチャンネルIDを保持する辞書
# {guild_id: channel_id}
active_channels = {}

# LM Studioにリクエストを送信する関数
async def get_lm_studio_response(messages: list[dict], model: str = MODEL):
    headers = {
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.0, # あなたの考察に基づき調整
        "top_p": 0.2,      # あなたの考察に基づき調整
        "top_k": 20,        # あなたの考察に基づき調整
        "repeat_penalty": 1.0, # あなたの考察に基づき調整
        "stop": ["</s>", "Human:", "Assistant:"], # LM Studioのモデルに合わせて調整
        "max_tokens": 500, # 応答の最大トークン数
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(LM_STUDIO_API_URL, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status() # エラーレスポンスの場合に例外を発生させる
            return response.json()["choices"][0]["message"]["content"]
    except httpx.RequestError as e:
        print(f"LM Studio APIリクエストエラー: {e}")
        return f"エラー: LM Studioへの接続に失敗しました ({e})"
    except KeyError:
        print(f"LM Studio API応答の解析エラー: {response.json()}")
        return "エラー: LM Studioからの応答形式が不正です。"
    except Exception as e:
        print(f"予期せぬエラー: {e}")
        return "エラー: 予期せぬ問題が発生しました。"


# Botが起動したときのイベント
@bot.event
async def on_ready():
    print(f'{bot.user.name} がログインしました！')
    # 定期実行タスクを開始
    check_and_motivate.start()

# /call コマンド
# Botが指定されたチャンネルを監視対象に追加する
@bot.command(name='call', description="このチャンネルを監視対象にし、けつ叩きモードを開始します。")
async def call_bot(ctx: commands.Context):
    if ctx.guild:
        active_channels[ctx.guild.id] = ctx.channel.id
        await ctx.send(f"このチャンネル `{ctx.channel.name}` でけつ叩きモードを開始します。")
        print(f"Guild {ctx.guild.id}: Channel {ctx.channel.id} がアクティブになりました。")
    else:
        await ctx.send("このコマンドはサーバーのチャンネルでのみ使用できます。")

# /stop_call コマンド
# Botが指定されたチャンネルの監視を停止する
@bot.command(name='stop_call', description="このチャンネルのけつ叩きモードを停止します。")
async def stop_call_bot(ctx: commands.Context):
    if ctx.guild and ctx.guild.id in active_channels and active_channels[ctx.guild.id] == ctx.channel.id:
        del active_channels[ctx.guild.id]
        await ctx.send(f"このチャンネル `{ctx.channel.name}` のけつ叩きモードを停止します。")
        print(f"Guild {ctx.guild.id}: Channel {ctx.channel.id} が非アクティブになりました。")
    else:
        await ctx.send("このチャンネルは現在けつ叩きモードではありません。")

# 定期実行タスク
@tasks.loop(minutes=1)
async def check_and_motivate():
    print("定期チェックを開始します...")
    for guild_id, channel_id in list(active_channels.items()):
        try:
            guild = bot.get_guild(guild_id)
            if not guild:
                print(f"DEBUG: ギルド {guild_id} が見つかりません。")
                continue
            
            print(f"DEBUG: ギルド {guild_id} からチャンネルID {channel_id} を取得試行中...")
            channel = guild.get_channel(channel_id) # まずキャッシュから
                
            if not channel:
                print(f"DEBUG: キャッシュに見つかりませんでした。Discord APIから直接取得を試みます (ID: {channel_id})...")
                try:
                    channel = await bot.fetch_channel(channel_id) # 直接APIを叩く
                    if channel:
                        print(f"DEBUG: 直接取得に成功しました: {channel.name} ({channel.id})")
                        print(f"チャンネルの比較、\nd:{channel}\nc:{channel_id}")
                        print(channel)
                        print(channel_id)
                    else:
                        print(f"DEBUG: 直接取得も失敗しました。チャンネルが存在しないか、アクセスできません。")
                except discord.NotFound:
                    print(f"DEBUG: discord.NotFoundエラー: チャンネルID {channel_id} は存在しません。")
                    channel = None # 明示的にNoneに設定
                except discord.Forbidden:
                    print(f"DEBUG: discord.Forbiddenエラー: チャンネルID {channel_id} へのアクセスが拒否されました。")
                    channel = None # 明示的にNoneに設定
                except Exception as e:
                    print(f"DEBUG: fetch_channel中に予期せぬエラー: {e}")
                    channel = None

            if not channel: # ここで改めてchannelがNoneかどうかチェック
                print(f"DEBUG: 最終的にチャンネル {channel_id} がギルド {guild_id} で見つかりませんでした。active_channelsから削除します。")
                del active_channels[guild_id] 
                continue
            
            # 直近20件のメッセージを取得
            messages = []
            async for message in channel.history(limit=20):
                # Bot自身のメッセージは除外
                if message.author == bot.user:
                    continue
                # LM StudioのAPI形式に合わせて整形
                role = "user" if not message.author.bot else "assistant"
                messages.insert(0, {"role": role, "content": message.content}) # 古いメッセージが先頭に来るように

            if not messages:
                print(f"チャンネル '{channel.name}' に有効なメッセージがありませんでした。")
                continue

            # システムプロンプトを追加
            system_prompt = """
            あなたは、ユーザーのプロジェクト進捗を促し、迷いや停滞が見られる場合に、過去の会話履歴を分析して、建設的なフィードバックや次の一歩を促す「けつ叩きAI」です。
            時には優しく、時には厳しく、しかし常にユーザーの成長を助ける視点で応答してください。
            ユーザーが思考停止している兆候（例：同じような質問の繰り返し、進捗が見られない、迷いを表明する）があれば、具体的に次のアクションを促すか、思考を整理する助けをしてください。
            ただし、常に返答する必要はありません。意味のある介入が必要な場合にのみ応答してください。
            最後に、LM Studioのモデルであるあなたの回答は、ユーザーの「けつ叩き」になるような、簡潔かつ明確なものにしてください。
            """
            
            # プロンプトの先頭にシステムメッセージを追加
            lm_messages = [{"role": "system", "content": system_prompt}] + messages

            print(f"LM Studioに送信するメッセージ数: {len(lm_messages)}")
            
            # LM Studioにリクエストを送信
            ai_response = await get_lm_studio_response(lm_messages)

            if ai_response and "エラー:" not in ai_response: # エラーではない場合のみ投稿
                await channel.send(f"**けつ叩きBotからのメッセージです:**\n{ai_response}")
            else:
                print(f"AIからの応答がありませんでした、またはエラーが発生しました: {ai_response}")

        except Exception as e:
            print(f"定期チェック中にエラーが発生しました (チャンネルID: {channel_id}): {e}")

# Botを実行
if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print("エラー: Discord Bot Tokenが設定されていません。'.env' ファイルを確認してください。")
    elif not LM_STUDIO_API_URL:
        print("エラー: LM Studio API URLが設定されていません。'.env' ファイルを確認してください。")
    else:
        bot.run(DISCORD_BOT_TOKEN)