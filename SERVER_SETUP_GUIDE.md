# サーバーPC 引っ越し・運用指南書

Cursor Agent がなくても、この文書だけでセットアップ・動作確認・タスク登録ができるようにまとめています。
（手元PCのタスク設定を 2026-08-01 時点で書き起こしたものです）

---

## 0. いまやること（チェックリスト）

- [ ] ZIPを展開する
- [ ] Python を入れる（手元と同じく **3.10〜3.14** 推奨。手元実測: **3.14.2**）
- [ ] `.venv` を作り直して `pip install`
- [ ] スモークテスト（後述 §3）を全部 OK にする
- [ ] タスクスケジューラを3本登録する（§5）
- [ ] **手元PC側の同じ3タスクを無効化**する（二重通知防止・最重要）
- [ ] サーバーPCは開催日にスリープしない設定にする

---

## 1. 展開の置き場所

例（ユーザー名はサーバー側に合わせてください）:

```text
C:\Users\<ユーザー>\Desktop\programming\sonoda-keiba-program
```

展開後、フォルダ直下に次があることを確認します。

| あるべきもの | 説明 |
|--------------|------|
| `run_today.py` | 夜間のデータ取得 |
| `scripts\watch_race_day.py` | 当日監視（T-10予想など） |
| `.env` | LINE / Discord トークン（秘密） |
| `data\processed\horses_master.csv` | 予想の本体データ |
| `data\processed\payback_cache.json` | 払戻キャッシュ |
| `data\raw\` | 生CSV（たくさん） |
| `RESTORE_SERVER.txt` | 短い復元メモ |
| `SERVER_SETUP_GUIDE.md` | **この指南書** |

**含めていないもの（わざと）:** `.venv` / `.git` / marksキャッシュ / 作業カス

---

## 2. 初回セットアップ（必須）

PowerShell を開き、展開したフォルダへ移動します。

```powershell
cd C:\Users\<ユーザー>\Desktop\programming\sonoda-keiba-program

python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

確認:

```powershell
Test-Path .\.venv\Scripts\python.exe
Test-Path .\.venv\Scripts\pythonw.exe
```

どちらも `True` であること。
タスク起動は **`pythonw.exe`**（黒い窓なし）を使うので、`pythonw` が無いと自動起動に失敗します。

### 実行ポリシーでスクリプトが止まる場合

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

---

## 3. 動作確認テスト（Cursor なし・手作業）

下から順に実行してください。失敗したらその場で止めて原因を見ます。

### テスト A — データがあるか

```powershell
cd C:\Users\<ユーザー>\Desktop\programming\sonoda-keiba-program
.\.venv\Scripts\python.exe -c "from pathlib import Path; m=Path('data/processed/horses_master.csv'); p=Path('data/processed/payback_cache.json'); print('master', m.exists(), m.stat().st_size); print('payback', p.exists(), p.stat().st_size); print('raw_csv', len(list(Path('data/raw').glob('*.csv'))))"
```

期待例:

- `master True` かつサイズが数千万バイト（手元では約 70MB）
- `payback True`
- `raw_csv` が 1000 超（手元では 1670）

### テスト B — 設定ファイル（.env）が読めるか

```powershell
.\.venv\Scripts\python.exe -c "from dotenv import load_dotenv; import os; load_dotenv(); keys=['LINE_CHANNEL_ACCESS_TOKEN','LINE_USER_ID','DISCORD_WEBHOOK_URL','DISCORD_WEBHOOK_WATCH_ALERT'];
[print(k, 'OK' if os.getenv(k) else 'MISSING') for k in keys]"
```

`LINE_*` が `MISSING` なら通知が飛びません。`.env` の中身を確認してください。

### テスト C — 当日監視（予定だけ・すぐ終わる）

```powershell
.\.venv\Scripts\python.exe scripts\watch_race_day.py --schedule-only
```

- 園田開催日ならレース一覧が出る
- 休催日なら「No schedule」やレース0件でも **異常ではない**

### テスト D — 夜間処理を手動1回（通信あり）

```powershell
.\.venv\Scripts\python.exe run_today.py
```

- 開催日: 結果取得 → master 更新 → LINE/Discord 通知の流れ
- 休催日: 「休場のため取得しません」系のメッセージが出れば成功
- 失敗時は Discord の障害チャンネル / LINE にアラートが来る設計です

### テスト E — 心拍チェック（手動）

```powershell
.\.venv\Scripts\python.exe scripts\check_watch_heartbeat.py
```

監視プロセスが動いていない日中は警告になることがあります。
**まずテスト C / 監視タスクを動かしてから**確認すると分かりやすいです。

### テスト F — 予想（任意・通信あり）

開催日でオッズが出たあと:

```powershell
.\.venv\Scripts\python.exe scripts\predict.py --date YYYYMMDD
```

デスクトップUIを使う場合（サーバーに画面があるとき）:

```powershell
.\.venv\Scripts\python.exe app\predict_desktop.py
```

---

## 4. 普段の使い方（役割分担）

### サーバーPCが担当するもの（自動）

| 時間帯 | 何が動くか | 実体 |
|--------|------------|------|
| 毎日 09:00 | 当日監視開始 | `watch_race_day.py`（発走 T-30/20/10 でスナップショット、T-10 で予想通知） |
| 09:00〜約12時間、**15分ごと** | 心拍チェック | `check_watch_heartbeat.py`（監視が止まっていたらアラート） |
| 毎日 21:00 | 夜間取得 | `run_today.py`（結果取得・master更新・成績通知） |

### 手元PCが担当すると楽なもの

- Cursor でのコード編集
- 当日予想デスクトップ / Streamlit（画面操作）
- note / X への手動投稿
- LINE Webhook + ngrok（チームメンバーの userId 収集。常時サーバー必須ではない）

### 手動でよく使うコマンド

```powershell
# 当日監視（コンソール付き・デバッグ用）
.\scripts\start_watch_race_day.cmd

# 夜間取得（コンソール付き）
.\scripts\start_run_today.cmd

# 心拍（コンソール付き）
.\scripts\start_check_watch_heartbeat.cmd
```

タスク用は同じ処理の **`.vbs`**（黒い窓が出ない版）です。

### ログの場所

```text
data\processed\logs\watch_YYYYMMDD.log
```

おかしいときはまずこのログを開きます。

### LINE 通知を一時停止したいとき

`.env` に:

```text
LINE_NOTIFY_PAUSED=1
```

Discord は止まりません。戻すときは `0` にするか行を消します。

---

## 5. タスクスケジューラの再現（手元PCの実設定）

手元PC（ユーザー `akimi`）で動いていた **3タスク** です。
サーバーではパスだけ自分の展開先に変えます。

### 5.1 一覧（そのまま再現）

#### ① 園田_当日監視

| 項目 | 値 |
|------|-----|
| トリガー | 毎日 **09:00** |
| 操作 | `wscript.exe` |
| 引数 | `"<展開先>\scripts\start_watch_race_day.vbs"` |
| 開始（作業フォルダ） | `<展開先>` |
| ユーザー | ログイン中のユーザー（対話） |
| 最長実行時間 | **無制限**（`PT0S`） |
| 失敗時再起動 | 3回 / 10分間隔 |
| 複数起動 | 新しいインスタンスを開始しない |
| バッテリー | バッテリ時は停止する（ノート注意） |

#### ② 心拍チェック(20min) ※実間隔は15分

| 項目 | 値 |
|------|-----|
| トリガー | 毎日 **09:00** 開始 |
| 繰り返し | **15分ごと** / 継続時間 **12時間** |
| 操作 | `wscript.exe` |
| 引数 | `"<展開先>\scripts\start_check_watch_heartbeat.vbs"` |
| 開始（作業フォルダ） | `<展開先>` |
| 最長実行時間 | 1時間 |
| 失敗時再起動 | 3回 / 10分間隔 |

名前は「20min」ですが、実際の設定は **15分間隔** です。そのままでOKです。

#### ③ 園田_夜間取得

| 項目 | 値 |
|------|-----|
| トリガー | 毎日 **21:00** |
| 操作 | `wscript.exe` |
| 引数 | `"<展開先>\scripts\start_run_today.vbs"` |
| 開始（作業フォルダ） | `<展開先>` |
| 最長実行時間 | **2時間** |
| 失敗時再起動 | 3回 / 15分間隔 |
| その他 | 開始を逃したらできるだけ早く実行（StartWhenAvailable） |

### 5.2 かんたん登録（推奨）

展開フォルダで PowerShell:

```powershell
cd C:\Users\<ユーザー>\Desktop\programming\sonoda-keiba-program
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\register_server_tasks.ps1
```

登録後の確認:

```powershell
Get-ScheduledTask -TaskName '園田_当日監視','園田_夜間取得','心拍チェック(20min)' |
  Format-Table TaskName, State
```

手動テスト実行:

```powershell
Start-ScheduledTask -TaskName '園田_当日監視'
```

### 5.3 GUI で手登録する場合

1. `taskschd.msc` を開く
2. 「基本タスクの作成」ではなく **「タスクの作成」**
3. 上記表どおりにトリガー・操作を入れる
4. 「最上位の特権で実行」は **不要**（手元も Limited）
5. 「ユーザーがログオンしているときのみ」＝手元と同じ。
   **サーバーを無人でログアウト運用するなら**「ログオンしていてもいなくても実行」に変更し、パスワード保存が必要です

### 5.4 XML からの参考インポート

`docs\server_migrate\task_*.xml` に手元からのエクスポートがあります。
中のパスが `C:\Users\akimi\...` 固定なので、**インポート前にメモ帳で展開先パスへ置換**するか、上記 PowerShell 登録を使ってください。

---

## 6. 手元PC側で必ずやること

1. タスクスケジューラで次を **無効**:
   - `園田_当日監視`
   - `園田_夜間取得`
   - `心拍チェック(20min)`
2. 動いている `pythonw` / `watch_race_day` があれば終了
3. 以降、データ更新の「正」はサーバー側の `data\` とする
   （両方で `run_today` すると master が分岐します）

---

## 7. サーバーPCの電源・ネットワーク

| 項目 | 推奨 |
|------|------|
| スリープ | 無効（少なくとも 8:50〜22:00） |
| ディスプレイオフ | 可（スリープとは別） |
| ネット | 有線推奨。Wi-Fi 切断に注意 |
| 時刻 | Windows 時刻同期 ON（T-10 がズレる） |
| ログイン | 手元設定は「対話ログオン」。無人なら §5.3 を変更 |

---

## 8. トラブルシュート

| 症状 | まず見る場所 |
|------|----------------|
| タスクがすぐ失敗（結果 0x1） | `.venv\Scripts\pythonw.exe` があるか |
| 通知が来ない | `.env` のトークン、`LINE_NOTIFY_PAUSED` |
| 監視だけ動かない | `data\processed\logs\watch_*.log` |
| netkeiba が弾かれる | 連続アクセスしすぎ。時間をおく |
| 休催なのに不安 | `run_today` は休場メッセージで正常終了する設計 |
| 二重に通知が来る | 手元PCのタスクがまだ有効 |

---

## 9. このZIPに入っていない・別途の話

- **Git 履歴** … 入っていません。コード更新は GitHub から `git clone` / `pull` がおすすめ
- **Cursor Agent 自動診断** … `.env` の `ALERT_CURSOR_AGENT` は通常 `0`。サーバーに Cursor API を置く場合のみ有効化
- **T-10 クリップボードコピー** … サーバーに人が座らないなら不要（`T10_CLIPBOARD=0` でも可）
- **LINE Webhook + ngrok** … チームID収集用。サーバー常駐必須ではない
- **R 分析** … 運用サーバーには不要（手元で十分）

---

## 10. 最短コマンドまとめ

```powershell
cd C:\Users\<ユーザー>\Desktop\programming\sonoda-keiba-program
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

.\.venv\Scripts\python.exe -c "from pathlib import Path; print(Path('data/processed/horses_master.csv').stat().st_size)"
.\.venv\Scripts\python.exe scripts\watch_race_day.py --schedule-only
.\.venv\Scripts\python.exe run_today.py

.\scripts\register_server_tasks.ps1
```

あとは手元PCの同名タスクを無効化して完了です。