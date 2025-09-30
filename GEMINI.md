以下、NotionとDiscordの双方向連携システム構築のための包括的なプロンプトをまとめました。

---

# NotionとDiscordの双方向連携システム構築プロンプト

## 🎯 プロジェクト概要

DiscordサーバーとNotionデータベースを双方向に同期し、メッセージ履歴とファイルを体系的に管理するBotシステムを構築する。

---

## 📋 機能要件

### 1. 同期トリガー
- **コマンド実行**: `/sync` コマンドによる手動同期
- **定時実行**: 毎日12:00と24:00（JST）に自動同期

### 2. Discord → Notion 同期仕様

#### メッセージフォーマット
```
時刻 |¥| user_name
メッセージ内容
[画像がある場合は画像を含める]
```

#### 同期対象
- 指定チャンネル（雑談・メモ欄）の当日分メッセージ
- テキスト本文
- 添付ファイル（画像、コード、その他）
- 投稿時刻とユーザー名

### 3. Notion → Discord 同期仕様
- Notionで新規作成・更新された内容をDiscordの「雑談アイデア」チャンネルに投稿
- **文字数制限対応**: 2,000文字を超える場合は自動分割して複数メッセージで送信

---

## 🏗️ データベース設計

### Notion側のデータベース構造

#### ① **Formテーブル**（メッセージ履歴用）
| プロパティ名 | 種類 | 説明 |
|------------|------|------|
| 名前 (Title) | タイトル | `時刻 \| ユーザー名` 形式 |
| メッセージ本文 | テキスト | Discordのメッセージ本文 |
| 投稿日時 | 日付 | メッセージの投稿日時（ソート用） |
| 投稿者 | テキスト | `message.author.display_name` |
| 関連アセット | **リレーション** | Assetsテーブルへの参照 |

#### ② **Assetsテーブル**（ファイル管理用）
| プロパティ名 | 種類 | 説明 |
|------------|------|------|
| ファイル名 (Title) | タイトル | 添付ファイルの元の名前 |
| ファイルURL | URL | 永続的なストレージのURL |
| ファイル種別 | セレクト | Image / Python Script / Text など |
| ファイルサイズ | 数値 | ファイルサイズ（バイト） |
| 投稿日時 | 日付 | 元メッセージの投稿日時 |
| 関連メッセージ | リレーション | Formテーブルとの逆参照（自動生成） |

---

## 🔧 技術スタック

### 開発言語・フレームワーク
- **Python 3.8+**

### 必須ライブラリ
```bash
pip install discord.py notion-client apscheduler python-dotenv requests
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### 外部サービス
1. **Discord Bot** (MESSAGE CONTENT INTENTを有効化)
2. **Notion API** (Internal Integration)
3. **Google Drive API** (ファイル永続化用・推奨)

---

## 🔑 事前準備

### Discord Bot設定
1. [Discord Developer Portal](https://discord.com/developers/applications)で新規アプリケーション作成
2. Botユーザー作成 → トークン取得
3. **Privileged Gateway Intents**:
   - ✅ MESSAGE CONTENT INTENT
   - ✅ SERVER MEMBERS INTENT (任意)
4. OAuth2権限:
   - `bot`, `applications.commands`
   - `Read Message History`, `Send Messages`, `Attach Files`
5. 生成URLからサーバーに招待

### Notion Integration設定
1. [Notionインテグレーション管理](https://www.notion.so/my-integrations)で新規作成
2. Internal Integration Token取得
3. 同期先データベースに「コネクトの追加」でインテグレーション連携
4. データベースIDをURLから取得（`https://notion.so/workspace/DATABASE_ID?v=...`）

### Google Drive API設定（ファイル永続化用）
1. Google Cloud Platformでプロジェクト作成
2. Google Drive API有効化
3. サービスアカウント作成 → JSON認証ファイルダウンロード
4. Drive内に専用フォルダ作成 → サービスアカウントと共有
5. フォルダIDを取得

---

## 💾 環境変数設定

`.env`ファイルを作成:

```env
# Discord
DISCORD_BOT_TOKEN="your_discord_bot_token"
TARGET_CHANNEL_ID="1234567890"  # 同期元チャンネルID
IDEA_CHANNEL_ID="0987654321"    # Notion→Discord投稿先ID

# Notion
NOTION_API_KEY="secret_xxxxxxxxxxxxx"
FORM_DATABASE_ID="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
ASSETS_DATABASE_ID="yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"

# Google Drive
GOOGLE_DRIVE_CREDENTIALS="credentials.json"
GOOGLE_DRIVE_FOLDER_ID="zzzzzzzzzzzzzzzzzzz"
```

---

## 🚀 実装のワークフロー

### Discord → Notion 同期処理

```
1. 今日のメッセージを取得（古い順）
   ↓
2. 各メッセージを処理:
   
   【添付ファイルあり】
   a. Discord CDNからファイルダウンロード
   b. Google Driveにアップロード → 永続URL取得
   c. Assetsテーブルに新規ページ作成（ファイル情報記録）
   d. 作成されたページIDをリストに保存
   
   【Formテーブルへの記録】
   e. メッセージ本文でページ作成
   f. 「関連アセット」プロパティにリレーション設定
   
   【添付ファイルなし】
   - Formテーブルにメッセージ情報のみ記録
```

### Notion → Discord 同期処理

```
1. Notion APIで最終同期以降の新規/更新ページを取得
   ↓
2. ページ本文を取得・整形
   ↓
3. 文字数チェック:
   
   【2,000文字以下】
   - そのまま1メッセージで送信
   
   【2,000文字超】
   - 2,000文字ごとに分割
   - 各チャンクを順次送信（番号付き: [1/3], [2/3], [3/3]）
   ↓
4. 送信完了後、同期済みフラグを更新
```

---

## 📝 コード実装の重要ポイント

### 1. メッセージ分割ロジック
```python
def split_message(text: str, max_length: int = 2000) -> list[str]:
    """長文を指定文字数で分割（単語境界を考慮）"""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        
        # 改行または空白で分割
        split_pos = text.rfind('\n', 0, max_length)
        if split_pos == -1:
            split_pos = text.rfind(' ', 0, max_length)
        if split_pos == -1:
            split_pos = max_length
        
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip()
    
    return chunks
```

### 2. Notionリレーション設定
```python
# Assetsページ作成後のIDリスト
asset_page_ids = ['uuid-1', 'uuid-2', ...]

# Formページ作成時にリレーション設定
notion.pages.create(
    parent={"database_id": FORM_DATABASE_ID},
    properties={
        "名前": {"title": [{"text": {"content": title}}]},
        "関連アセット": {
            "relation": [{"id": pid} for pid in asset_page_ids]
        }
    }
)
```

### 3. Google Driveアップロード
```python
async def upload_to_drive(attachment: discord.Attachment) -> str:
    """ファイルをGDriveにアップロードし永続URLを返す"""
    
    # Discord CDNからダウンロード
    response = requests.get(attachment.url)
    file_content = io.BytesIO(response.content)
    
    # GDriveにアップロード
    file_metadata = {
        'name': attachment.filename,
        'parents': [DRIVE_FOLDER_ID]
    }
    media = MediaIoBaseUpload(file_content, mimetype=attachment.content_type)
    
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()
    
    # 公開権限設定
    drive_service.permissions().create(
        fileId=file['id'],
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()
    
    return file['webViewLink']
```

---

## ⚡ パフォーマンス最適化

### 設計上の工夫
1. **関心の分離**: メッセージとファイルを別テーブルで管理
2. **永続化戦略**: Discord CDNに依存せず外部ストレージ利用
3. **バッチ処理**: 定時実行で負荷分散
4. **エラーハンドリング**: 各ステップでtry-exceptとログ出力

### ボトルネック対策
- **画像/ファイル**: 最大の通信コスト → 非同期処理で並列化
- **API制限**: Notion/Discord Rate Limitに注意 → 適切なsleep挿入
- **メモリ管理**: 大量ファイル処理時はストリーム処理を検討

---

## 🛡️ セキュリティ考慮事項

1. **認証情報管理**
   - `.env`ファイルを`.gitignore`に追加
   - サービスアカウントJSONも絶対にコミットしない

2. **権限最小化**
   - Botには必要最小限の権限のみ付与
   - GDriveフォルダは専用フォルダに限定

3. **エラー情報の取り扱い**
   - ログにトークンやAPIキーを出力しない
   - ユーザーにはフレンドリーなエラーメッセージ

---

## 🎨 拡張アイデア

1. **検索機能**: `/search [キーワード]` でNotion内を検索
2. **統計レポート**: 週次で投稿数・アクティブユーザーをサマリ
3. **タグ機能**: メッセージに`#tag`でカテゴリ分類
4. **リアクション同期**: Discord絵文字リアクションをNotionに記録
5. **バックアップ**: 定期的にデータベースをエクスポート

---

## 📚 参考リソース

- [Discord.py公式ドキュメント](https://discordpy.readthedocs.io/)
- [Notion API公式ドキュメント](https://developers.notion.com/)
- [Google Drive API Python Quickstart](https://developers.google.com/drive/api/quickstart/python)

---

このプロンプトに基づいて、スケーラブルで堅牢なDiscord-Notion連携システムを構築できます。実装時は段階的に機能を追加し、各ステップでテストを行うことを推奨します。
