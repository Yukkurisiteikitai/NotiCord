import os
import traceback
from openai import OpenAI

# --- Message Splitting ---
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

# --- LM-Studio Client ---

# 環境変数からLM-StudioのベースURLを取得、なければデフォルト値を設定
# ★★★ 変更点: URLの末尾から /v1 を削除 ★★★
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234")
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "mlx-community/gemma-3-1b-it-qat")

# LM-Studioのクライアントを初期化
# APIキーは不要なため "" を設定
client = OpenAI(base_url=LM_STUDIO_BASE_URL, api_key="")

def get_completion(prompt: str):
    """LM-Studioから補完を取得する"""
    try:
        response = client.chat.completions.create(
            model=LM_STUDIO_MODEL, # model名はLM-Studioでロードしているモデルに依存
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception:
        print("LM-Studioへのリクエスト中に予期せぬエラーが発生しました:")
        print(traceback.format_exc()) # スタックトレースを詳細に出力
        return None
