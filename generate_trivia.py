#!/usr/bin/env python3
"""毎日の雑学を Claude で生成し、Slack のチャンネルへ投稿するスクリプト。

仕組みの概要:
1. 今日の曜日からジャンルを決める
2. 過去に出した雑学 (history.jsonl) を読み、重複を避ける
3. Claude API に Web 検索させ、出典つきの雑学を生成する
4. Slack に「雑学本体」を投稿し、そのスレッドに「深掘り解説」をぶら下げる
5. 出した雑学を history.jsonl に追記する

※ 普段あなたが触る可能性があるのは、すぐ下の「設定」ブロックだけです。
   それより下のロジックは、基本的にいじらなくて大丈夫です。
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

import anthropic

# ============================================================
# 設定（ここだけ触れば OK）
# ============================================================

# 1 日に届ける雑学の件数
ITEMS_PER_DAY = 3

# 使うモデル。コストを下げたいなら "claude-haiku-4-5-20251001" に変えても OK
MODEL = "claude-sonnet-4-6"

# 曜日ごとのジャンル（0=月曜 … 6=日曜）。自由に書き換え可能
GENRES_BY_WEEKDAY = {
    0: "歴史",
    1: "科学・宇宙",
    2: "IT・テクノロジー",
    3: "ゲーム・エンタメ",
    4: "暮らしの雑学",
    5: "世界・地理",
    6: "言葉・カルチャー",
}

# 過去の雑学を何件ぶんまで「重複チェック」に使うか
HISTORY_LOOKBACK = 200

# 履歴ファイルのパス
HISTORY_PATH = "history.jsonl"

# ============================================================
# ここから下はロジック（基本いじらない）
# ============================================================

JST = timezone(timedelta(hours=9))


def today_jst():
    return datetime.now(JST)


def pick_genre(dt):
    return GENRES_BY_WEEKDAY.get(dt.weekday(), "雑学")


def load_recent_titles():
    """history.jsonl から直近のタイトル一覧を読む。"""
    if not os.path.exists(HISTORY_PATH):
        return []
    titles = []
    with open(HISTORY_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("title"):
                titles.append(rec["title"])
    return titles[-HISTORY_LOOKBACK:]


def build_prompt(genre, recent_titles):
    avoid = "\n".join(f"- {t}" for t in recent_titles) if recent_titles else "（まだありません）"
    today = today_jst()
    today_str = today.strftime("%-m月%-d日")  # 例: 6月16日
    return f"""あなたは毎朝、日本語で雑学を届けるキュレーターです。
今日のジャンルは「{genre}」です。このジャンルに沿った雑学を {ITEMS_PER_DAY} 個、用意してください。

# 内容の方針（最重要）
- 読んだ人が「へぇ〜！」「そうなの！？」と声を上げるような、意外性・驚きのある内容を選ぶ。
- 専門家でなくても楽しめる、万人向けの親しみやすさを保つ。
- 最近 2 年以内の時事ニュースや最新の研究発表は避ける。長年知られてきた面白い事実・仕組み・歴史的エピソードを優先する。
- {ITEMS_PER_DAY} 件は必ず互いに異なるサブジャンルから選ぶ（例：「科学・宇宙」なら「宇宙」「生物」「物理」のように分散させる）。同じサブジャンルを複数出さない。


# 厳守ルール
- 必ず Web 検索で裏を取ること。検索で確認できない雑学は絶対に出さない。
- 各雑学には、信頼できる実在のソース URL を最低 1 つ付ける。URL を推測で書かない。
- 「世界初」「世界一」などの断定は、ソースで確認できた場合のみ使う。
- 下の「最近出した雑学」と内容が重複しないようにする。
- 各雑学に、もう一歩踏み込んだ「深掘り解説」を付ける（背景・理由・関連する面白い話など 2〜4 文）。

# 最近出した雑学（これらは避ける）
{avoid}

# 出力形式
検索が終わったら、最後の発言は次の JSON だけを ```json コードブロックで出力すること。
前後に説明文を一切付けない。

```json
{{
  "items": [
    {{
      "title": "雑学の見出し（15〜25 文字程度）",
      "fact": "雑学の本体（2〜3 文）",
      "detail": "深掘り解説（2〜4 文）",
      "sources": ["https://..."]
    }}
  ]
}}
```
"""


def call_claude(genre, recent_titles):
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY を環境変数から自動で読む
    prompt = build_prompt(genre, recent_titles)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
        tools=[
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 3,
                "user_location": {
                    "type": "approximate",
                    "city": "Tokyo",
                    "country": "JP",
                    "timezone": "Asia/Tokyo",
                },
            }
        ],
    )
    # 検索結果ブロックなどを除き、テキスト部分だけを連結する
    return "".join(
        block.text for block in resp.content if getattr(block, "type", "") == "text"
    )


def extract_json(text):
    """応答テキストから JSON 部分を取り出してパースする。"""
    m = re.search(r"```json\s*(.*?)```", text, re.DOTALL)
    if not m:
        m = re.search(r"```\s*(.*?)```", text, re.DOTALL)
    raw = m.group(1).strip() if m else None
    if raw is None:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = text[start : end + 1]
    if raw is None:
        raise ValueError("応答から JSON を取り出せませんでした")
    return json.loads(raw)


SLACK_API = "https://slack.com/api/chat.postMessage"


def slack_post(token, channel, text, thread_ts=None):
    """Slack にメッセージを投稿し、その ts（スレッドの起点 ID）を返す。"""
    payload = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    req = urllib.request.Request(
        SLACK_API,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urllib.request.urlopen(req) as res:
        body = json.loads(res.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError(f"Slack 投稿に失敗しました: {body.get('error')}")
    return body["ts"]


def main():
    token = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("SLACK_CHANNEL_ID")
    if not token or not channel:
        print("SLACK_BOT_TOKEN と SLACK_CHANNEL_ID を設定してください", file=sys.stderr)
        sys.exit(1)

    dt = today_jst()
    date_str = dt.strftime("%Y-%m-%d")
    genre = pick_genre(dt)
    recent = load_recent_titles()

    # 生成（最大 2 回まで試す）
    data = None
    for attempt in range(2):
        try:
            text = call_claude(genre, recent)
            data = extract_json(text)
            if data.get("items"):
                break
        except Exception as e:  # noqa: BLE001
            print(f"生成に失敗（試行 {attempt + 1}）: {e}", file=sys.stderr)
            data = None
    if not data or not data.get("items"):
        print("雑学を生成できませんでした", file=sys.stderr)
        sys.exit(1)

    items = data["items"][:ITEMS_PER_DAY]

    # チャンネルへのヘッダー投稿
    header = f"おはようございます。今日の雑学（{genre}）{len(items)} 本です。"
    slack_post(token, channel, header)

    # 雑学本体を投稿し、そのスレッドに深掘り解説をぶら下げる
    new_records = []
    for i, item in enumerate(items, 1):
        title = item.get("title", "（無題）")
        fact = item.get("fact", "")
        detail = item.get("detail", "")
        sources = item.get("sources") or []

        src_line = ""
        if sources:
            src_line = "\n出典: " + " / ".join(f"<{u}>" for u in sources)

        body = f"*{i}. {title}*\n{fact}{src_line}"
        ts = slack_post(token, channel, body)

        if detail:
            slack_post(token, channel, f"もっと詳しく:\n{detail}", thread_ts=ts)

        new_records.append({"date": date_str, "genre": genre, "title": title})

    # 履歴に追記
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        for rec in new_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"{len(items)} 件を投稿しました（{date_str} / {genre}）")


if __name__ == "__main__":
    main()
