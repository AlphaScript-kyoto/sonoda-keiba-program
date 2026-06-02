"""完了報告メール送信（環境変数 GMAIL_APP_PASSWORD または SMTP_* が必要）。"""

from __future__ import annotations

import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TO = "akimine11010@gmail.com"
SUBJECT = "[sonoda-keiba] 会社PC作業完了・GitHub push済み (ca8a241)"


def _body() -> str:
    status_path = ROOT / "docs" / "PROJECT_STATUS.md"
    status = status_path.read_text(encoding="utf-8") if status_path.exists() else "(PROJECT_STATUS なし)"
    return f"""園田競馬プロジェクト — 会社PC作業完了報告

GitHub push 完了
  リポジトリ: https://github.com/gurashiroozisan/sonoda-keiba-program
  コミット: ca8a241
  ブランチ: main

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
今回完了した処理
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 脚質キャッシュ バックフィル … 3756件完了
2. 三連複ROI向け重みチューニング … config/tuned_weights_sanrenpuku.json 生成
3. 馬券ロジック変更
   - 複勝: 荒レース（win_profile==荒）は見送り
   - 堅/荒判定: 下位クラス(C1-C3/B2)・1700m+ を追加
4. tune_weights.py に --objective sanrenpuku 追加
5. docs/PROJECT_STATUS.md 更新

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
主な結果
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【三連複ROIチューニング — 2026年5月のみ】
  style（現行・採用中） … 三連複回収率 85.7%
  sanrenpuku（新・未採用） … 三連複回収率 61.4%
  → 5月だけ見て採用しない。1〜5月通しで再評価すること。

【新馬券ロジック バックテスト — 2026年5月】
  単勝◎(堅のみ) … 95.9%（114R）
  複勝◎ … 91.8%（114R）
  三連複 … 66.5%（124R）
  三連単 … 125.3%（109R）
  ワイド … 71.1%（124R）

【domainモデル比較 — 2026年5月】
  脚質のみ … 単勝109.8% / 三連複85.7% / 三連単140.4% ← 最良
  脚質+ドメイン … 三連複82.5%
  現行ベース … 三連複70.8%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
次にやること（優先順）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. build_features.py … 脚質を horses_master.csv に反映
2. backtest_bets.py --from 20260101 --to 20260531 … 通期で初見評価
3. style vs sanrenpuku 重みの A/B 比較
4. 1〜3月 / 4〜5月 分割バックテスト（5月過学習チェック）
5. 2025通年 holdout

家のPC: git pull 後、docs/PROJECT_STATUS.md を読めば続き可能。
venv は .\\.venv\\Scripts\\python.exe 直叩き（PowerShell Activate 不可の場合）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
docs/PROJECT_STATUS.md 全文
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{status}
"""


def main() -> int:
    body = _body()
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER") or os.environ.get("GMAIL_USER")
    smtp_pass = os.environ.get("SMTP_PASSWORD") or os.environ.get("GMAIL_APP_PASSWORD")
    from_addr = os.environ.get("SMTP_FROM") or smtp_user or "akimine11010@gmail.com"

    if not smtp_pass or not smtp_user:
        print("ERROR: SMTP_USER + SMTP_PASSWORD (または GMAIL_APP_PASSWORD) が未設定", file=sys.stderr)
        print("  例: $env:GMAIL_USER='akimine11010@gmail.com'", file=sys.stderr)
        print("      $env:GMAIL_APP_PASSWORD='xxxx xxxx xxxx xxxx'", file=sys.stderr)
        # 本文をファイルに保存して終了
        out = ROOT / "completion_email_draft.txt"
        out.write_text(f"To: {TO}\nSubject: {SUBJECT}\n\n{body}", encoding="utf-8")
        print(f"Draft saved: {out}")
        return 1

    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = TO
    msg["Subject"] = SUBJECT
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_addr, [TO], msg.as_string())

    print(f"Sent to {TO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
