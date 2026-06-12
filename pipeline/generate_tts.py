import os, subprocess, json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import get_channel_config, TEST_MODE, retry, Timer

AUDIO_DIR = Path("output/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


@retry(max_attempts=3, delay=3)
def _gen_one_tts(edge_voice, narration, out_path, idx):
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
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
    assert os.path.getsize(str(out_path)) > 1000, f"TTS file too small: {out_path}"
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
        tasks.append((str(out_path), (edge_voice, narration, i)))

    audio_files = [None] * len(tasks)

    def process(idx, info):
        out_path, params = info
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

    audio_files = [f for f in audio_files if f is not None and os.path.getsize(f) > 1000]

    metadata = {"audio_files": audio_files, "voice": edge_voice, "channel": channel}
    meta_path = AUDIO_DIR / "audio_manifest.json"
    json.dump(metadata, open(meta_path, "w"))
    return metadata


def _kokoro_fallback(text, out_path):
    try:
        from kokoro import KPipeline
        import soundfile as sf
        import numpy as np

        pipeline = KPipeline(lang_code="a")
        gen = pipeline(text, voice="af_heart")
        audio_frames = []
        for result in gen:
            audio_frames.append(result[0])
        if audio_frames:
            audio = np.concatenate(audio_frames)
            sf.write(out_path, audio, 24000)
        else:
            raise RuntimeError("Kokoro produced no audio frames")
    except Exception as e:
        raise RuntimeError(f"Kokoro also failed: {e}")
