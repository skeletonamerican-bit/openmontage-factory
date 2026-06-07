import os
import requests


def main():
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    artifact_url = os.getenv("ARTIFACT_URL")
    channel = os.getenv("CHANNEL")
    topic = os.getenv("TOPIC")

    if not all([bot_token, chat_id]):
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables")

    if not artifact_url:
        artifact_url = "Artifact URL not set in environment"

    message = (
        f"✅ Video factory finished for channel: {channel}\n"
        f"Topic: {topic}\n"
        f"Artifact: {artifact_url}"
    )

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    response = requests.post(url, json={"chat_id": chat_id, "text": message})
    response.raise_for_status()
    print("Telegram notification sent.")


if __name__ == "__main__":
    main()
