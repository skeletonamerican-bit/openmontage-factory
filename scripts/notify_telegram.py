import os, sys, json, urllib.request
from pathlib import Path

CHANNEL_NAMES = {
    "weirdhistory": "Weird History",
    "crimeledger": "Crime Ledger",
    "mindtactics": "Mind Tactics",
}

def send_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({
        "chat_id": chat_id, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": True
    }).encode()
    req = urllib.request.Request(url, data=data)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"sendMessage failed: {e}")
        return None

def send_video(token, chat_id, video_path, caption):
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    video_data = Path(video_path).read_bytes()
    filename = Path(video_path).name
    body_parts = []
    body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}")
    body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}")
    body_parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"video\"; filename=\"{filename}\"\r\nContent-Type: video/mp4\r\n\r\n")
    body = "\r\n".join(body_parts).encode() + video_data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"sendVideo failed: {e}")
        return None

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    channel = os.environ.get("CHANNEL", "weirdhistory").strip()
    topic = os.environ.get("TOPIC", "").strip()
    run_id = os.environ.get("RUN_ID", "").strip()
    status = os.environ.get("STATUS", "success").strip()

    if not token or not chat_id:
        print("ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        sys.exit(1)

    ch_name = CHANNEL_NAMES.get(channel, channel.upper())
    video_files = list(Path("projects").glob("*/render/FINAL_v3.mp4"))

    if status != "success" or not video_files:
        icon = "✅" if status == "success" else "❌"
        text = (
            f"{icon} <b>OpenMontage Factory</b>\n"
            f"Channel: {ch_name}\n"
            f"Topic: {topic or 'N/A'}\n"
            f"Status: {status}\n"
            f"Run: #{run_id}"
        )
        send_message(token, chat_id, text)
        print("Message sent")
        return

    video_path = video_files[0]
    size_mb = video_path.stat().st_size / 1048576
    print(f"Sending: {video_path} ({size_mb:.1f}MB)")

    caption = (
        f"🎬 {ch_name} — {topic or 'New Video'}\n"
        f"Run #{run_id}"
    )

    if size_mb > 50:
        send_message(token, chat_id,
            f"🎬 {ch_name}\n"
            f"Video ready ({size_mb:.1f}MB) — too large for Telegram\n"
            f"Topic: {topic}\n"
            f"Run: #{run_id}"
        )
    else:
        result = send_video(token, chat_id, str(video_path), caption)
        if result and result.get("ok"):
            print("Video sent to Telegram!")
        else:
            send_message(token, chat_id,
                f"🎬 {ch_name}\n"
                f"Video ready\nTopic: {topic}\nRun: #{run_id}"
            )

if __name__ == "__main__":
    main()
