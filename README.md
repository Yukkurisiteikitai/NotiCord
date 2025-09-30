# Notion-Discord 双方向連携Bot

Discordチャンネルの会話とファイルをNotionデータベースに自動で記録し、逆にNotionでのアイデアをDiscordに通知する、双方向連携システムです。

## 主な機能

- **Discord → Notion同期**:
  - 指定したDiscordチャンネル（テキスト/フォーラム形式に対応）のメッセージをNotionに保存します。
  - 添付された画像やファイルは、Google Driveに永続化してNotionにリンクを記録します。
  - メッセージ本文、投稿者、投稿日時も合わせて記録されます。

- **Notion → Discord同期**:
  - （将来的な拡張用）Notionで作成されたページをDiscordの指定チャンネルに通知します。

- **同期トリガー**:
  - **手動実行**: Discord上で `/sync` コマンドを実行することで、いつでも同期を開始できます。
  - **定時実行**: 毎日12:00と0:00（日本時間）に自動で同期処理が実行されます。

## 技術スタック

- Python 3.8+
- discord.py
- notion-client
- Google Drive API
- APScheduler (定時実行用)

---

## 導入と設定方法

### 1. 前提条件

- Python 3.8以上がインストールされていること。
- Discord Bot、Notionインテグレーション、Google Cloud Platformの事前準備が完了していること。
  - 詳細はプロジェクトの仕様書（`GEMINI.md`）を参照してください。

### 2. インストール

まず、このリポジトリをクローンし、必要なライブラリをインストールします。

```bash
pip install -r requirements.txt
```

### 3. 環境変数の設定

プロジェクトルートに `.env` ファイルを作成し、以下の内容を記述・設定してください。

```env
# Discord設定
DISCORD_BOT_TOKEN="your_discord_bot_token" # Discord Botのトークン
TARGET_CHANNEL_ID="your_discord_channel_id"  # 同期したいDiscordチャンネルのID
IDEA_CHANNEL_ID="your_discord_idea_channel_id"    # Notionからの通知先チャンネルID
GUILD_ID="your_guild_id" # 【開発者向け・任意】コマンドを即時反映させたいサーバーID

# Notion設定
NOTION_API_KEY="your_notion_api_key" # Notionインテグレーションのトークン
FORM_DATABASE_ID="your_form_database_id" # メッセージ履歴を保存するDBのID
ASSETS_DATABASE_ID="your_assets_database_id" # ファイル情報を保存するDBのID

# Google Drive設定
GOOGLE_DRIVE_CREDENTIALS="credentials.json" # GCPサービスアカウントの認証情報ファイル名
GOOGLE_DRIVE_FOLDER_ID="your_google_drive_folder_id" # ファイルのアップロード先フォルダID
```

**※注意**: `credentials.json` ファイルは、このプロジェクトのルートディレクトリに配置してください。

### 4. Notionデータベースの準備

このBotが正しく動作するためには、Notionデータベースのプロパティ（列）の名前と種類がコードの想定と完全に一致している必要があります。

#### ① Formテーブル

メッセージの履歴を保存するデータベースです。

| プロパティ名 | 種類 | 説明 |
| :--- | :--- | :--- |
| **`名前`** | **タイトル** | Botが自動生成 (`時刻 | ユーザー名`) |
| `メッセージ本文` | テキスト | Discordのメッセージ本文 |
| `投稿日時` | 日付 | メッセージの投稿日時 |
| `投稿者` | テキスト | メッセージの投稿者名 |
| `関連アセット` | リレーション | Assetsテーブルへの関連付け |

#### ② Assetsテーブル

添付ファイルを管理するデータベースです。

| プロパティ名 | 種類 | 説明 |
| :--- | :--- | :--- |
| **`ファイル名`** | **タイトル** | アップロードされたファイル名 |
| `ファイルURL` | URL | Google Drive上のファイルへのリンク |
| `ファイル種別` | セレクト | `image`, `text` などのファイル形式 |
| `ファイルサイズ` | 数値 | ファイルサイズ（バイト） |
| `投稿日時` | 日付 | 元メッセージの投稿日時 |

**【重要】**
- 各データベースを作成したら、必ず右上の「・・・」メニューから「コネクトの追加」を選び、あなたのNotionインテグレーションを連携させてください。
- 「タイトル」プロパティは、データベース作成時に最初から存在する主要な列を指します。その名前を上記に合わせて変更してください。

---

## 使い方

すべての設定が完了したら、以下のコマンドでBotを起動します。

```bash
python main.py
```

Botが正常に起動すると、コンソールにログインメッセージが表示され、定時実行とコマンド待機状態になります。
