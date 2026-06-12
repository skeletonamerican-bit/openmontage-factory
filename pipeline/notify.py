import os, requests
from pathlib import Path


def _progress_bar(pct, width=10):
    filled = int(pct * width)
    empty = width - filled
    return "█" * filled + "░" * empty


def send_telegram(channel, video_path=None, thumbnail_path=None, error=None, stage=None, progress=None, stats=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print(f"TELEGRAM: no credentials configured (token={'set' if token else 'missing'}, chat_id={'set' if chat_id else 'missing'})")
        return

    if error:
        text = f"❌ *{channel} ERROR*\n{error}"
    elif stage and progress is not None:
        bar = _progress_bar(progress)
        pct = int(progress * 100)
        text = f"{bar} {pct}% — {stage}"
    elif stage:
        text = stage
    elif video_path and os.path.exists(video_path):
        size_mb = os.path.getsize(video_path) / (1024 * 1024)
        dur_str = _format_duration(stats.get("duration", 0)) if stats else ""
        scenes = stats.get("scenes", 0) if stats else 0
        ai_video = stats.get("ai_video_count", 0) if stats else 0
        ken_burns = stats.get("ken_burns_count", 0) if stats else 0

        text = (
            f"✅ *{channel} ГОТОВО*\n"
            f"🎬 {scenes} сцен | {ai_video} AI видео | {ken_burns} Ken Burns\n"
            f"📏 {dur_str} | 📦 {size_mb:.1f}MB"
        )
        if thumbnail_path and os.path.exists(thumbnail_path):
            _send_photo(token, chat_id, thumbnail_path, text)
            return
    else:
        text = f"ℹ️ *{channel}* stage: {stage or 'unknown'}"

    _send_message(token, chat_id, text)


def _send_message(token, chat_id, text):
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
        print(f"Telegram message: {resp.status_code}", flush=True)
    except Exception as e:
        print(f"Telegram send failed: {e}", flush=True)


def _send_photo(token, chat_id, photo_path, caption):
    try:
        with open(photo_path, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"},
                files={"photo": f},
                timeout=30,
            )
        print(f"Telegram photo: {resp.status_code}", flush=True)
    except Exception as e:
        print(f"Telegram photo send failed: {e}, falling back to text", flush=True)
        _send_message(token, chat_id, caption)


def _format_duration(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d} мин"
