import pandas as pd
from pathlib import Path

def fix_all_csvs():
    raw_dir = Path("data/raw")
    # すべてのCSVを走査して読み込み、再保存する
    for csv_file in raw_dir.glob("*.csv"):
        # 全列を文字列(str)として読み込むことで、日付変換を阻止する
        df = pd.read_csv(csv_file, dtype=str)
        
        # CSVを再保存する際、quoting=1 を指定して全データを " " で囲む
        # これによりExcelが「文字列」として認識しやすくなる
        df.to_csv(csv_file, index=False, encoding='utf-8-sig', quoting=1)
        print(f"修正完了: {csv_file.name}")

if __name__ == "__main__":
    fix_all_csvs()