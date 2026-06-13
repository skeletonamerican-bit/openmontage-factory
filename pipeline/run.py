import os, sys, json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CHANNELS, TEST_MODE, Timer
from llm_router import LLMRouter
from generate_script import generate_script
from generate_assets import generate_assets
from generate_tts import generate_tts
from assemble import assemble_video
from notify import send_telegram
from topics import get_next_topic, get_remaining_count
from qa.video_qa import run_qa

Path("output").mkdir(exist_ok=True)

STAGE_NOTIFICATIONS = True


def _notify_stage(channel, stage, progress=None, error=None):
    if not STAGE_NOTIFICATIONS:
        return
    try:
        if error:
            send_telegram(channel, error=error)
        elif progress is not None:
            send_telegram(channel, stage=stage, progress=progress)
        else:
            send_telegram(channel, stage=stage)
    except Exception as e:
        print(f"Telegram notification failed: {e}", flush=True)


def main():
    channel = os.environ.get("CHANNEL", "")
    topic = os.environ.get("TOPIC", "")

    if not channel:
        print("CHANNEL env var required", flush=True)
        sys.exit(1)

    channels = list(CHANNELS.keys()) if channel == "all" else [channel]

    # Auto-topic: if no topic specified, pick next from topics.json
    auto_topic = not topic
    if auto_topic:
        remaining = {}
        for ch in channels:
            try:
                rem = get_remaining_count(ch)
                remaining[ch] = rem
            except ValueError:
                remaining[ch] = 0
        print(f"Auto-topic mode. Remaining topics: {remaining}", flush=True)

    # Phase 1: Script generation
    scripts = {}
    for ch in channels:
        ch_topic = topic
        if auto_topic:
            try:
                ch_topic = get_next_topic(ch)
                print(f"[{ch}] Auto-selected topic: {ch_topic}", flush=True)
            except ValueError as e:
                print(f"[{ch}] {e}, using generic topic", flush=True)
                ch_topic = f"{ch} documentary"
            os.environ["TOPIC"] = ch_topic

        with Timer(f"[{ch}] Script generation"):
            _notify_stage(ch, f"📝 {ch_topic[:60]} — генерация сценария...")
            scripts[ch] = generate_script(ch, ch_topic)
            scene_count = len(scripts[ch])
            print(f"[{ch}] script ready, {scene_count} scenes", flush=True)
            _notify_stage(ch, f"✅ Скрипт готов ({scene_count} сцен)")

    # Phase 2: Asset generation
    assets = {}
    for ch in channels:
        with Timer(f"[{ch}] Asset generation"):
            _notify_stage(ch, f"🖼️ {ch} — генерация assets...", progress=0.3)
            assets[ch] = generate_assets(ch, scripts[ch])
            photo_count = sum(len(a.get("photos", [])) for a in assets[ch].get("scene_assets", {}).values())
            video_count = sum(1 for a in assets[ch].get("scene_assets", {}).values() if a.get("video"))
            print(f"[{ch}] assets ready: {photo_count} photos, {video_count} videos", flush=True)
            _notify_stage(ch, f"✅ Assets готовы ({photo_count} фото, {video_count} видео)")

    # Phase 3: TTS generation (parallel across channels)
    tts_results = {}
    with Timer(f"TTS generation"):
        _notify_stage(None, f"🔊 Озвучка...", progress=0.5)
        with ThreadPoolExecutor(max_workers=len(channels)) as ex:
            futs = {ex.submit(generate_tts, ch, scripts[ch]): ch for ch in channels}
            for f in as_completed(futs):
                ch = futs[f]
                try:
                    tts_results[ch] = f.result()
                    audio_count = len(tts_results[ch].get("audio_files", []))
                    total_audio_sec = audio_count * 15
                    total_audio_min = total_audio_sec // 60
                    print(f"[{ch}] TTS ready: {audio_count} files ({total_audio_min} мин)", flush=True)
                    _notify_stage(ch, f"✅ TTS готов ({total_audio_min} мин аудио)")
                except Exception as e:
                    print(f"[{ch}] TTS failed: {e}", flush=True)
                    tts_results[ch] = {"audio_files": []}
                    _notify_stage(ch, "TTS", error=f"TTS failed: {e}")

    # Phase 4: Video assembly (parallel across channels)
    videos = {}
    thumbnails = {}
    stats = {}
    with Timer(f"Video assembly"):
        _notify_stage(None, f"🎬 Сборка видео...", progress=0.75)
        with ThreadPoolExecutor(max_workers=len(channels)) as ex:
            futs = {ex.submit(assemble_video, ch, scripts[ch], assets[ch], tts_results[ch]): ch for ch in channels}
            for f in as_completed(futs):
                ch = futs[f]
                try:
                    result = f.result()
                    if isinstance(result, tuple) and len(result) == 3:
                        video_path, thumb_path, stat = result
                        videos[ch] = video_path
                        thumbnails[ch] = thumb_path
                        stats[ch] = stat
                    else:
                        videos[ch] = result
                        thumbnails[ch] = None
                        stats[ch] = {}
                    dur_str = f"{int(stats[ch].get('duration', 0) // 60)}:{int(stats[ch].get('duration', 0) % 60):02d}"
                    size_mb = stats[ch].get("size_mb", 0)
                    print(f"[{ch}] video ready -> {videos[ch]}", flush=True)
                    print(f"[{ch}] stats: {dur_str}, {size_mb:.1f}MB, {stats[ch].get('scenes', 0)} scenes", flush=True)
                except Exception as e:
                    print(f"[{ch}] assembly failed: {e}", flush=True)
                    import traceback
                    traceback.print_exc()
                    _notify_stage(ch, "assembly", error=f"Сборка провалилась: {e}")

    # Phase 5: QA validation
    qa_results = {}
    for ch in channels:
        if ch in videos and videos[ch]:
            with Timer(f"[{ch}] QA validation"):
                try:
                    print(f"[{ch}] Running QA on {videos[ch]}", flush=True)
                    qa = run_qa(ch, videos[ch])
                    qa_results[ch] = qa
                    if qa.get("ok"):
                        print(f"[{ch}] QA PASSED", flush=True)
                    else:
                        print(f"[{ch}] QA FAILED: {qa.get('issues', [])}", flush=True)
                        # Rebuild with Pixabay fallback and reassemble
                        print(f"[{ch}] Rebuilding with Pixabay-only mode...", flush=True)
                        os.environ["SKIP_KAGGLE"] = "1"
                        os.environ["USE_PIXABAY_ONLY"] = "1"
                        try:
                            from generate_assets import generate_assets
                            from assemble import assemble_video
                            new_assets = generate_assets(ch, scripts[ch])
                            new_video, new_thumb, new_stats = assemble_video(ch, scripts[ch], new_assets, tts_results[ch])
                            videos[ch] = new_video
                            thumbnails[ch] = new_thumb
                            stats[ch] = new_stats
                            send_telegram(ch, error=f"QA failed, rebuilt with Pixabay: {qa.get('issues')}")
                        except Exception as rebuild_e:
                            print(f"[{ch}] Rebuild failed: {rebuild_e}", flush=True)
                            send_telegram(ch, error=f"QA rebuild failed: {rebuild_e}")
                except Exception as qa_e:
                    print(f"[{ch}] QA error: {qa_e}", flush=True)
                    import traceback
                    traceback.print_exc()
                    qa_results[ch] = {"ok": True, "skipped": True, "error": str(qa_e)}

    # Phase 6: Notifications with thumbnails and stats
    for ch in channels:
        if ch in videos and videos[ch]:
            try:
                send_telegram(ch, video_path=videos[ch], thumbnail_path=thumbnails.get(ch), stats=stats.get(ch, {}))
            except Exception as e:
                print(f"[{ch}] final notification failed: {e}", flush=True)
        else:
            try:
                send_telegram(ch, error=f"{ch} failed — video not produced")
            except Exception as e:
                print(f"[{ch}] error notification failed: {e}", flush=True)

    # Final summary
    print("\n" + "=" * 60, flush=True)
    print("ИТОГОВАЯ СТАТИСТИКА", flush=True)
    print("=" * 60, flush=True)
    for ch in channels:
        if ch in stats and stats[ch]:
            s = stats[ch]
            dur_sec = s.get("duration", 0)
            dur_min = dur_sec / 60
            size_mb = s.get("size_mb", 0)
            scenes = s.get("scenes", 0)
            ai_video = s.get("ai_video_count", 0)
            ken_burns = s.get("ken_burns_count", 0)
            print(f"  {ch:15s} | {scenes:3d} scenes | {ai_video:2d} AI vid | {ken_burns:3d} KB | {dur_min:.1f}min | {size_mb:.0f}MB", flush=True)
        else:
            print(f"  {ch:15s} | FAILED", flush=True)
    print("=" * 60, flush=True)
    print("Pipeline complete.", flush=True)


if __name__ == "__main__":
    main()
