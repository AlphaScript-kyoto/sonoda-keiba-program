"""Send completion report email. Requires GMAIL_USER and GMAIL_APP_PASSWORD."""
import os, smtplib, sys
from email.mime.text import MIMEText
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
TO = os.environ.get("COMPLETION_REPORT_TO") or os.environ.get("GMAIL_USER") or ""
SUBJECT = "[sonoda-keiba] 会社PC作業完了 push済"
def main():
    p = ROOT / "docs" / "COMPLETION_REPORT_20260601.md"
    body = p.read_text(encoding="utf-8") if p.exists() else "See docs/PROJECT_STATUS.md"
    user = os.environ.get("GMAIL_USER") or os.environ.get("SMTP_USER")
    pw = os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("SMTP_PASSWORD")
    if not user or not pw or not TO:
        print("Set GMAIL_USER, GMAIL_APP_PASSWORD, and COMPLETION_REPORT_TO", file=sys.stderr); return 1
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = SUBJECT; msg["From"] = user; msg["To"] = TO
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as s:
        s.starttls(); s.login(user, pw); s.send_message(msg)
    print("Sent to", TO); return 0
if __name__ == "__main__": sys.exit(main())
