"""園田競馬・netkeiba 用の定数とパス設定。"""

from pathlib import Path

# プロジェクトルート（config/ の親）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 園田競馬場（netkeiba 地方競馬）
JYO_CD = "50"
NAR_BASE_URL = "https://nar.netkeiba.com"

URL_RACECOURSE = f"{NAR_BASE_URL}/racecourse/racecourse_page.html?jyo_cd={JYO_CD}"
URL_RESULT = f"{NAR_BASE_URL}/race/result.html?race_id={{race_id}}"
URL_SHUTUBA = f"{NAR_BASE_URL}/race/shutuba.html?race_id={{race_id}}"
URL_ODDS_WIN = f"{NAR_BASE_URL}/odds/?race_id={{race_id}}&type=b1"

# データ保存先
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# 全レース・全特徴量を1ファイルにまとめたマスタ
HORSES_MASTER_PATH = DATA_PROCESSED_DIR / "horses_master.csv"
HORSES_FEATURES_PATH = DATA_PROCESSED_DIR / "horses_features.csv"

# スクレイピング（netkeiba 負荷軽減のためリクエスト間に待機）
REQUEST_INTERVAL_MIN_SEC = 7.0
REQUEST_INTERVAL_MAX_SEC = 10.0
REQUEST_MAX_PER_HOUR = 300
REQUEST_TIMEOUT_SEC = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
