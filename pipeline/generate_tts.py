import os, subprocess, json, asyncio
from pathlib import Path
from config import get_channel_config, TEST_MODE

AUDIO_DIR = Path("output/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

def generate_tts(channel, script):
    cfg = get_channel_config(channel)
    edge_voice = cfg["edge_voice"]
    scenes = script if isinstance(script, list) else script.get("scenes", script)

    audio_files = []

    for i, scene in enumerate(scenes):
        narration = scene.get("narration", "")
        if not narration:
            continue

        out_path = AUDIO_DIR / f"scene_{i+1:03d}.mp3"

        if TEST_MODE and not os.environ.get("FORCE_TTS"):
            Path(out_path).write_text("")
            audio_files.append(str(out_path))
            continue

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
                print(f"edge-tts failed, trying kokoro... {e}")
                _kokoro_fallback(narration, str(out_path))

        audio_files.append(str(out_path))

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
