
import os
import traceback
from openai import OpenAI

# --- LM-Studio Client Initialization ---

# 環境変数からLM-StudioのベースURLを取得
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
LM_STUDIO_MODEL= os.getenv("LM_STUDIO_MODEL", "mlx-community/gemma-3-1b-it-qat")

# LM-Studioのクライアントを初期化 (APIキーは "not-needed" など適当な文字列でOK)
try:
    client = OpenAI(base_url=LM_STUDIO_BASE_URL, api_key="not-needed")
except Exception as e:
    print(f"AIハンドラの初期化中にエラーが発生しました: {e}")
    client = None

def _call_llm(prompt: str, temperature: float = 0.7) -> str | None:
    """LLMにリクエストを送信し、テキスト応答を取得する内部関数"""
    if not client:
        print("AIクライアントが初期化されていません。")
        return None
    try:
        # シンプルなuser-assistant形式の会話
        messages = [
            {"role": "user", "content": prompt}
        ]
        
        response = client.chat.completions.create(
            model=LM_STUDIO_MODEL,  # LM-Studioでロードしているモデルに依存
            messages=messages,
            temperature=temperature,
        )
        return response.choices[0].message.content
    except Exception:
        print("LLMへのリクエスト中に予期せぬエラーが発生しました:")
        print(traceback.format_exc())
        return None

def _build_generation_prompt(text_content: str, feedback: str = None) -> str:
    """ナレッジ生成用のプロンプトを構築する"""
    feedback_instruction = ""
    if feedback:
        feedback_instruction = f"""# 追加指示
前回の要約に対する評価は以下の通りです。このフィードバックを反映して、より質の高い要約を生成してください。

[前回の要約への評価]
{feedback}
"""

    prompt = f"""# Role
あなたは、プロの議事録作成アシスタントです。会話のログから、要点、決定事項、そして誰が何をすべきかを正確に抽出する能力に長けています。

# Context
以下のDiscordの会話ログを分析し、指定されたフォーマットでマークダウン形式の要約を作成してください。

# Data
---
{text_content}
---

{feedback_instruction}

# Instruction
この会話ログを分析し、以下のフォーマットでマークダウン形式の要約を作成してください。
1.  **このスレッドの目的・議題:** この議論が何について話しているかを1〜2行で簡潔にまとめてください。
2.  **議論の要点:** 主要な意見や議論の流れを3〜5個の箇条書きでまとめてください。
3.  **最終的な決定事項:** 結論が出ている事柄を明確に記述してください。もし結論が出ていない場合は「結論は出ていない」と記述してください。
4.  **発生したタスク (Action Items):** 「誰が」「何をすべきか」が明確なタスクを全て抽出し、リストアップしてください。担当者が不明な場合は「担当者未定」と記載してください。
"""
    return prompt

def _build_evaluation_prompt(text_content: str, generated_summary: str) -> str:
    """自己評価用のプロンプトを構築する"""
    prompt = f"""# Context
- 元の会話ログ: ```{text_content}```
- AIが生成した要約: ```{generated_summary}```

# Instruction
あなたは品質評価の専門家です。提示された「AIが生成した要約」が、以下の品質基準を全て満たしているかチェックし、Yes/Noで答えてください。もしNoの場合は、どの点がどのように不足しているかを具体的に指摘してください。

- **網羅性:** 元の会話ログで出た重要な反対意見や懸念事項は、要約に含まれていますか？
- **正確性:** 決定事項やタスクの担当者、期限は正確に抽出されていますか？
- **中立性:** 特定の個人の意見に偏らず、議論全体を客観的に要約できていますか？
- **明瞭性:** 発生したタスクは、誰が見ても誤解なく理解できる形で記述されていますか？

# Answer
(ここにYes/Noと具体的な指摘を記述)
"""
    return prompt


def generate_knowledge_from_text(text_content: str) -> str | None:
    """
    テキストコンテンツを受け取り、自己評価ループを経て高品質なナレッジを生成する
    """
    print("AIによるナレッジ生成を開始します...")

    # 1. 一次生成 (v1)
    print("  - ステップ1/3: 要約の一次生成中...")
    generation_prompt_v1 = _build_generation_prompt(text_content)
    summary_v1 = _call_llm(generation_prompt_v1)
    if not summary_v1:
        print("  - 一次生成に失敗しました。")
        return None
    
    # 2. 自己評価
    print("  - ステップ2/3: 生成された要約の自己評価中...")
    evaluation_prompt = _build_evaluation_prompt(text_content, summary_v1)
    # 評価はより決定的な結果を求めるため、temperatureを低めに設定
    evaluation_result = _call_llm(evaluation_prompt, temperature=0.1)
    if not evaluation_result:
        print("  - 自己評価に失敗しました。一次生成の結果をそのまま利用します。")
        return summary_v1

    print(f"  - 自己評価の結果: {evaluation_result}")
    # 簡単な評価結果の解析 (ここでは 'no' が含まれていたら再生成)
    if 'no' in evaluation_result.lower():
        print("  - ステップ3/3: 自己評価に基づき、要約を再生成中...")
        # 3. 修正・再生成 (v2)
        generation_prompt_v2 = _build_generation_prompt(text_content, feedback=evaluation_result)
        summary_v2 = _call_llm(generation_prompt_v2)
        if not summary_v2:
            print("  - 再生成に失敗しました。一次生成の結果をそのまま利用します。")
            return summary_v1
        
        print("  - 再生成が完了しました。")
        return summary_v2
    else:
        print("  - ステップ3/3: 自己評価をクリアしました。")
        return summary_v1
