import os, sys, json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CHANNELS, TEST_MODE
from llm_router import LLMRouter
from generate_script import generate_script
from generate_assets import generate_assets
from generate_tts import generate_tts
from assemble import assemble_video
from notify import send_telegram

Path("output").mkdir(exist_ok=True)

def main():
    channel = os.environ.get("CHANNEL", "")
    topic = os.environ.get("TOPIC", "")

    if not channel or not topic:
        print("CHANNEL and TOPIC env vars required")
        sys.exit(1)

    channels = list(CHANNELS.keys()) if channel == "all" else [channel]

    for ch in channels:
        print(f"\n=== {ch.upper()} START ===")
        try:
            script = generate_script(ch, topic)
            print(f"{ch}: script ready, {len(script)} scenes")

            assets = generate_assets(ch, script)
            print(f"{ch}: assets ready")

            tts = generate_tts(ch, script)
            print(f"{ch}: TTS ready")

            video = assemble_video(ch, script, assets, tts)
            print(f"{ch}: video ready -> {video}")

            send_telegram(ch, video)

        except Exception as e:
            print(f"ERROR {ch}: {e}", flush=True)
            import traceback
            traceback.print_exc()
            send_telegram(ch, error=str(e))
            continue

    print("\nPipeline complete.")

if __name__ == "__main__":
    main()
