import json
import os
import sys
from urllib import error, parse, request


def main():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    artifact_url = os.getenv("ARTIFACT_URL")
    channel = os.getenv("CHANNEL")
    topic = os.getenv("TOPIC")

    if not bot_token or not chat_id:
        sys.exit("ERROR: Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables")

    if not artifact_url:
        artifact_url = "Artifact URL not set"

    message = (
        f"✅ Video factory finished for channel: {channel or 'unknown'}\n"
        f"Topic: {topic or 'unknown'}\n"
        f"Artifact: {artifact_url}"
    )

    payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    req = request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

    try:
        with request.urlopen(req, timeout=30) as response:
            response.read()
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        sys.exit(f"ERROR: Telegram request failed ({exc.code}): {body}")
    except Exception as exc:
        sys.exit(f"ERROR: Telegram request failed: {exc}")

    print("Telegram notification sent.")


if __name__ == "__main__":
    main()
