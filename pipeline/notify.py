import os, requests

def send_telegram(channel, video_path=None, error=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print(f"TELEGRAM: no credentials configured (token={'set' if token else 'missing'}, chat_id={'set' if chat_id else 'missing'})")
        return

    if error:
        text = f"❌ {channel} ERROR:\n{error}"
    else:
        size_mb = os.path.getsize(video_path) / (1024 * 1024) if video_path and os.path.exists(video_path) else 0
        text = (
            f"✅ {channel} COMPLETE\n"
            f"Size: {size_mb:.0f}MB\n"
            f"Download from GitHub Actions Artifacts:\n"
            f"→ Actions → latest run → Artifacts"
        )

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        print(f"Telegram: {resp.status_code}")
    except Exception as e:
        print(f"Telegram send failed: {e}")
