import os, subprocess, json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import get_channel_config, TEST_MODE

AUDIO_DIR = Path("output/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def _gen_one_tts(edge_voice, narration, out_path, idx):
    if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
        return str(out_path)
    try:
        subprocess.run(
            ["edge-tts", "--voice", edge_voice, "--text", narration,
             "--write-media", str(out_path)],
            check=True, capture_output=True, timeout=120,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            subprocess.run(
                ["python", "-m", "edge_tts", "--voice", edge_voice,
                 "--text", narration, "--write-media", str(out_path)],
                check=True, capture_output=True, timeout=120,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"edge-tts failed for scene {idx}, trying kokoro... {e}")
            _kokoro_fallback(narration, str(out_path))
    return str(out_path)


def generate_tts(channel, script):
    cfg = get_channel_config(channel)
    edge_voice = cfg["edge_voice"]
    scenes = script if isinstance(script, list) else script.get("scenes", script)

    tasks = []
    for i, scene in enumerate(scenes):
        narration = scene.get("narration", "")
        if not narration:
            continue
        out_path = AUDIO_DIR / f"scene_{i+1:03d}.mp3"
        if TEST_MODE and not os.environ.get("FORCE_TTS"):
            Path(out_path).write_text("")
            tasks.append((str(out_path), None))
        else:
            tasks.append((str(out_path), (edge_voice, narration, i)))

    audio_files = [None] * len(tasks)

    def process(idx, info):
        out_path, params = info
        if params is None:
            return idx, out_path
        voice, narration, si = params
        return idx, _gen_one_tts(voice, narration, out_path, si)

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(process, idx, info): idx for idx, info in enumerate(tasks)}
        for f in as_completed(futures):
            try:
                idx, path = f.result()
                audio_files[idx] = path
            except Exception as e:
                print(f"TTS task failed: {e}")

    audio_files = [f for f in audio_files if f is not None]

    metadata = {"audio_files": audio_files, "voice": edge_voice, "channel": channel}
    meta_path = AUDIO_DIR / "audio_manifest.json"
    json.dump(metadata, open(meta_path, "w"))
    return metadata


def _kokoro_fallback(text, out_path):
    try:
        import kokoro
        import soundfile as sf
        import numpy as np

        pipeline = kokoro.KokoroPipeline(lang_code="a")
        audio = pipeline(text, voice="af_heart")[0]
        sf.write(out_path, audio, 24000)
    except Exception as e:
        raise RuntimeError(f"Kokoro also failed: {e}")
