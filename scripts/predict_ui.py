# ASCII-only launcher -> src/predictor/predict_ui_app.py
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.predictor.predict_ui_app import main

main()