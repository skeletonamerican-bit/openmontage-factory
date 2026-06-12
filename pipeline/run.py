import os, sys, json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        print("CHANNEL and TOPIC env vars required", flush=True)
        sys.exit(1)

    channels = list(CHANNELS.keys()) if channel == "all" else [channel]

    # Phase 1: Script generation (fast, sequential)
    scripts = {}
    for ch in channels:
        print(f"=== {ch.upper()} script generation ===", flush=True)
        scripts[ch] = generate_script(ch, topic)
        print(f"[{ch}] script ready, {len(scripts[ch])} scenes", flush=True)

    # Phase 2: Asset generation (Kaggle, sequential per channel)
    assets = {}
    for ch in channels:
        print(f"\n=== {ch.upper()} asset generation ===", flush=True)
        assets[ch] = generate_assets(ch, scripts[ch])
        print(f"[{ch}] assets ready", flush=True)

    # Phase 3: TTS generation (parallel across channels)
    tts_results = {}
    print(f"\n=== TTS generation ({len(channels)} channels parallel) ===", flush=True)
    with ThreadPoolExecutor(max_workers=len(channels)) as ex:
        futs = {ex.submit(generate_tts, ch, scripts[ch]): ch for ch in channels}
        for f in as_completed(futs):
            ch = futs[f]
            try:
                tts_results[ch] = f.result()
                print(f"[{ch}] TTS ready", flush=True)
            except Exception as e:
                print(f"[{ch}] TTS failed: {e}", flush=True)
                tts_results[ch] = {"audio_files": []}

    # Phase 4: Video assembly (parallel across channels)
    videos = {}
    print(f"\n=== Video assembly ({len(channels)} channels parallel) ===", flush=True)
    with ThreadPoolExecutor(max_workers=len(channels)) as ex:
        futs = {ex.submit(assemble_video, ch, scripts[ch], assets[ch], tts_results[ch]): ch for ch in channels}
        for f in as_completed(futs):
            ch = futs[f]
            try:
                videos[ch] = f.result()
                print(f"[{ch}] video ready -> {videos[ch]}", flush=True)
            except Exception as e:
                print(f"[{ch}] assembly failed: {e}", flush=True)
                import traceback
                traceback.print_exc()

    # Phase 5: Notifications (parallel)
    print(f"\n=== Notifications ===", flush=True)
    with ThreadPoolExecutor(max_workers=len(channels)) as ex:
        for ch in channels:
            if ch in videos and videos[ch]:
                ex.submit(send_telegram, ch, videos[ch])
            else:
                ex.submit(send_telegram, ch, error=f"{ch} failed")

    print("\nPipeline complete.", flush=True)

if __name__ == "__main__":
    main()
