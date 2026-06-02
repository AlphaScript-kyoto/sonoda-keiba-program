"""作業完了サマリを LINE にプッシュ送信。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.line_bot import send_line_message

# LINE テキスト上限に収める要約（ぱっと見用）
SUMMARY = """【園田予想 UI 作業完了】

テスト: horse_form / marks / post / softmax 計12件 OK

■ 今回やったこと
1) 印表
  ・「勝率」(1着率) +「連対率」(2着以内)
  ・旧「戦績 10勝/44走」列は削除
  ・モデル確率＝温度T=6のレース内相対（馬券ロジックは従来のまま）

2) 馬柱（新・表とコピー文の間）
  ・印5頭それぞれ直近5走
  ・クラス/距離/馬場/騎手/斤量/馬体重/着順/着差/上がり3F/走破/ペース
  ・ペース未設定の古い走は「—」

3) predict_ui.py
  ・UTF-16化で壊れていたので UTF-8 で再生成

■ 触った主なファイル
  src/predictor/horse_form.py（新規）
  src/predictor/marks_display.py
  scripts/predict_ui.py
  tests/test_horse_form.py

■ 起動
  .venv\\Scripts\\python.exe -m streamlit run app/predict_app.py
  （data/master 必須。無いと馬柱は省略表示）

■ まだ別タスク（今回は未実施）
  三連複ROIチューニング / compare_models / 脚質BF

Git commit はしていません。必要なら声かけてください。"""


def main() -> int:
    resp = send_line_message(SUMMARY)
    if resp.status_code != 200:
        print("LINE send failed", file=sys.stderr)
        return 1
    print("LINE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
