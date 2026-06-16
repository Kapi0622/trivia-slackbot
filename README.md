# daily-trivia-bot

毎朝、Claude が Web 検索で裏取りした雑学を **3 本**、Slack の専用チャンネルに届けます。
各雑学はチャンネルに投稿され、その **スレッドに「深掘り解説」** がぶら下がります。

- ジャンルは曜日ごとに自動で切り替わります（月＝歴史、木＝ゲームなど）
- 出典 URL つきなので、誤情報をそのまま信じてしまうリスクを抑えられます
- 一度出した雑学は記録され、翌日以降は重複しないようになっています
- サーバーは不要。GitHub の無料の仕組み（GitHub Actions）だけで動きます

---

## 必要なもの

1. GitHub アカウント（このリポジトリを置く場所）
2. Anthropic の API キー（Claude を使うため）
3. Slack ワークスペースと、雑学を流したいチャンネル

---

## セットアップ手順

最初の一回だけ、下の 4 ステップをやれば完了です。あとは放っておけば毎朝届きます。

### 1. このリポジトリを自分の GitHub に置く

このフォルダ一式を、自分の GitHub リポジトリとして作成します（非公開リポジトリで OK）。

### 2. Anthropic API キーを用意する

1. https://console.anthropic.com を開く
2. 「API Keys」からキーを発行してコピーする（`sk-ant-...` で始まる文字列）

このキーがあとで `ANTHROPIC_API_KEY` になります。

### 3. Slack の Bot を用意する

スレッドに投稿するため、Slack の「Bot Token」を使います。

1. https://api.slack.com/apps を開き、**Create New App → From scratch** を選ぶ
2. アプリ名（例: 雑学Bot）とワークスペースを選んで作成
3. 左メニューの **OAuth & Permissions** を開く
4. 「Bot Token Scopes」に **`chat:write`** を追加する
5. ページ上部の **Install to Workspace** を押して許可する
6. 表示された **Bot User OAuth Token**（`xoxb-...`）をコピーする
   → これが `SLACK_BOT_TOKEN` になります
7. Slack で雑学を流したいチャンネルを開き、`/invite @雑学Bot` で **Bot をチャンネルに招待** する
8. チャンネルの **ID** を調べる
   → チャンネル名をクリック → 一番下に出る `C` から始まる ID、
     または「リンクをコピー」した URL の末尾が ID です
   → これが `SLACK_CHANNEL_ID` になります

### 4. GitHub に 3 つの秘密情報を登録する

リポジトリの **Settings → Secrets and variables → Actions → New repository secret** から、
以下の 3 つを登録します（名前は完全に一致させてください）。

| 名前 | 中身 |
| --- | --- |
| `ANTHROPIC_API_KEY` | 手順 2 のキー |
| `SLACK_BOT_TOKEN` | 手順 3 の `xoxb-...` |
| `SLACK_CHANNEL_ID` | 手順 3 のチャンネル ID |

---

## 動作確認

定時を待たずに、手動で 1 回動かして確認できます。

1. リポジトリの **Actions** タブを開く
2. 左の **daily-trivia** を選ぶ
3. **Run workflow** ボタンを押す

数十秒〜1 分ほどで、Slack のチャンネルに雑学が届けば成功です。

---

## カスタマイズ（触るのはここだけ）

普段いじる可能性があるのは、`generate_trivia.py` の上部「設定」ブロックと、
ワークフローの届く時刻だけです。

### 届く時刻を変える

`.github/workflows/daily-trivia.yml` の `cron` を編集します。
時刻は UTC（世界標準時）なので、日本時間より 9 時間前で書きます。

| 日本時間で届けたい時刻 | cron の書き方 |
| --- | --- |
| 朝 6:00 | `"0 21 * * *"` |
| 朝 7:00（初期設定） | `"0 22 * * *"` |
| 朝 8:00 | `"0 23 * * *"` |

### 件数・ジャンル・モデルを変える

`generate_trivia.py` の上部を編集します。

- `ITEMS_PER_DAY` … 1 日に届く件数（初期値 3）
- `GENRES_BY_WEEKDAY` … 曜日ごとのジャンル（自由に書き換え可）
- `MODEL` … 使うモデル。コストを抑えたいなら `"claude-haiku-4-5-20251001"` に変更

---

## コストの目安

1 日 1 回、3 本ぶんの生成と数回の Web 検索を行うだけなので、
通常は **月あたり数百円以内** に収まることがほとんどです。
正確な料金は使うモデルと検索回数で変わります。最新の単価は Anthropic の料金ページで確認してください。

---

## 仕組み（参考）

1. GitHub Actions が毎朝決まった時刻にスクリプトを起動する
2. その日の曜日からジャンルを決める
3. `history.jsonl`（過去の雑学）を読み、重複しない雑学を Claude に生成させる
   - このとき Web 検索で裏取りし、出典 URL を付けさせている
4. Slack に雑学を投稿し、スレッドに深掘り解説をぶら下げる
5. 出した雑学を `history.jsonl` に追記し、自動でコミットする

---

## うまく動かないとき

- **Slack に届かない**：Bot をチャンネルに招待したか、`SLACK_CHANNEL_ID` が正しいかを確認
- **`not_in_channel` エラー**：手順 3-7 の招待（`/invite`）を忘れている可能性大
- **生成に失敗する**：`ANTHROPIC_API_KEY` の登録ミス、または API の残高切れを確認
- それでも直らない場合は、Actions の実行ログ（赤い × の行）を見ると原因が分かります
