import pandas as pd
from pathlib import Path

def repair_csv_files():
    raw_dir = Path("data/raw")
    # すべてのCSVを走査
    for csv_file in raw_dir.glob("*.csv"):
        print(f"修復中: {csv_file.name}")
        
        # 1. 読み込む（dtypeで明示的に文字列として扱う）
        df = pd.read_csv(csv_file, dtype=str)
        
        # 2. '着差' 列で「1月2日」のようになっているものを「1/2」に戻す変換
        # 日付になってしまったデータは '2026-01-02' 等に変わっている可能性があるため
        def fix_margin(val):
            # もし日付型（datetime）っぽくなっていたら変換する
            if isinstance(val, str) and "-" in val and len(val) == 10:
                parts = val.split("-") # 2026-01-02
                return f"{int(parts[1])}/{int(parts[2])}"
            return val

        if '着差' in df.columns:
            df['着差'] = df['着差'].apply(fix_margin)
            
        # 3. 修正して上書き保存
        df.to_csv(csv_file, index=False, encoding='utf-8-sig', quoting=1)

if __name__ == "__main__":
    repair_csv_files()
    print("1000個のCSVの修復が完了しました！")