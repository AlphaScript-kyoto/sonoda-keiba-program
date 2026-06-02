import subprocess
from datetime import datetime
import os
import sys

# toolsディレクトリをインポート
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tools'))
from line_bot import send_line_message

base_dir = os.path.dirname(os.path.abspath(__file__))
target_script = os.path.join(base_dir, 'scripts', 'fetch_daily.py')
today = datetime.now().strftime('%Y%m%d')

print(f"本日の日付 {today} でデータを取得します...")

# capture_output=True にすることで、エラー内容をプログラム内で受け取れるようになります
try:
    result = subprocess.run(
        ['.\\.venv\\Scripts\\python.exe', target_script, '--date', today],
        check=True,
        capture_output=True,
        text=True
    )
    send_line_message(f"園田競馬のデータ取得が完了しました ({today})")

except subprocess.CalledProcessError as e:
    # エラーが発生した場合、エラーメッセージ（stderr）を抽出してLINEで送信
    error_message = e.stderr.strip() or "詳細なエラーメッセージなし"
    send_line_message(f"【失敗】園田競馬データ取得エラー ({today})\n理由: {error_message}")
    print(f"エラーが発生しました: {error_message}")