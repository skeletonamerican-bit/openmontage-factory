import json, os, subprocess, sys, numpy as np
from pathlib import Path

VOICE_MAP = {
    "weirdhistory": "af_heart",
    "crimeledger": "am_adam",
    "mindtactics": "af_bella",
}

FALLBACK_VOICES = {
    "weirdhistory": "en_US-amy-medium",
    "crimeledger": "en_US-joe-medium",
    "mindtactics": "en_US-amy-medium",
}

def load_script(channel):
    script_path = Path("projects") / channel / "script.json"
    if not script_path.exists():
        sys.exit(f"ERROR: {script_path}")
    return json.loads(script_path.read_text(encoding="utf-8"))

def try_kokoro(text, out_path, voice):
    try:
        import kokoro
        from kokoro import KPipeline
        import soundfile as sf
        pipeline = KPipeline(lang_code="a")
        audio_chunks = []
        for gs, ps, audio in pipeline(text, voice=voice, speed=1.0):
            audio_chunks.append(audio)
        if audio_chunks:
            combined = np.concatenate(audio_chunks)
            sf.write(str(out_path), combined, 24000)
            return True
    except Exception:
        pass
    return False

def try_piper(text, out_path, voice):
    model_path = Path("models/piper/en_US-lessac-high.onnx")
    if not model_path.exists():
        return False
    try:
        tmp = out_path.with_suffix(".tmp.wav")
        cmd = f'echo "{text}" | piper --model {model_path} --output_file {tmp}'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and tmp.exists():
            subprocess.run([
                "ffmpeg", "-y", "-i", str(tmp),
                "-af", "loudnorm=I=-14:TP=-1:LRA=11",
                "-ar", "44100", str(out_path)
            ], capture_output=True, timeout=60)
            tmp.unlink(missing_ok=True)
            return True
    except Exception:
        pass
    return False

def try_espeak(text, out_path):
    try:
        subprocess.run([
            "espeak-ng", "-w", str(out_path),
            "-s", "145", "-p", "45", "-a", "180", text
        ], check=True, capture_output=True, timeout=60)
        return True
    except Exception:
        pass
    return False

def normalize_audio(src, dst):
    subprocess.run([
        "ffmpeg", "-y", "-i", str(src),
        "-af", "atrim=start=0.05,loudnorm=I=-14:TP=-1:LRA=11",
        "-ar", "44100", str(dst)
    ], capture_output=True, check=True, timeout=120)

def main():
    channel = os.getenv("CHANNEL", "").strip()
    if not channel:
        sys.exit("ERROR: CHANNEL not set")

    script = load_script(channel)
    out_dir = Path("projects") / channel / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)

    kokoro_voice = VOICE_MAP.get(channel, "af_heart")
    scenes = script.get("scenes", [])
    print(f"Channel: {channel} | Kokoro voice: {kokoro_voice} | {len(scenes)} scenes")

    for scene in scenes:
        sid = scene.get("id")
        text = str(scene.get("narration", "")).strip()
        if not sid or not text:
            print(f"  SKIP scene {sid}: no narration")
            continue
        final = out_dir / f"{sid}.wav"
        if final.exists():
            print(f"  SKIP {sid} (exists)")
            continue
        print(f"  Scene {sid}...", end=" ", flush=True)
        raw = out_dir / f"{sid}_raw.wav"
        ok = try_kokoro(text, raw, kokoro_voice)
        if not ok:
            ok = try_piper(text, raw, kokoro_voice)
        if not ok:
            ok = try_espeak(text, raw)
        if not ok:
            print("FAILED all TTS engines")
            continue
        normalize_audio(raw, final)
        raw.unlink(missing_ok=True)
        kb = final.stat().st_size // 1024
        print(f"OK ({kb}KB)")

    wavs = list(out_dir.glob("*.wav"))
    print(f"\nDone: {len(wavs)}/{len(scenes)} audio files generated")

if __name__ == "__main__":
    main()
