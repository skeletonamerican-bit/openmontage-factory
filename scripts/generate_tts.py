import json
import os
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOICE_MAP = {
    "twistedtruths": "af",
    "crimeledger": "en-us",
    "mindtactics": "af",
}
KOKORO_VOICE = {
    "twistedtruths": "af_heart",
    "crimeledger": "am_adam",
    "mindtactics": "af_bella",
}


def load_script(channel):
    script_path = ROOT / "projects" / channel / "script.json"
    if not script_path.exists():
        raise FileNotFoundError(f"Script file not found: {script_path}")
    return json.loads(script_path.read_text())


def synthesize_with_espeak(text, voice, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "espeak",
        "-v",
        voice,
        "-w",
        str(output_path),
        text,
    ]
    subprocess.run(command, check=True)


def main():
    channel = os.getenv("CHANNEL")
    if not channel:
        raise SystemExit("Missing CHANNEL environment variable")

    voice = VOICE_MAP.get(channel, "en-us")
    scene_voice = KOKORO_VOICE.get(channel, voice)
    script = load_script(channel)
    output_dir = ROOT / "projects" / channel / "audio"
    output_dir.mkdir(parents=True, exist_ok=True)

    for scene in script["scenes"]:
        scene_id = scene["id"]
        narration = scene["narration"].strip()
        output_path = output_dir / f"{scene_id}.wav"
        if output_path.exists():
            print(f"Skipping existing audio: {output_path}")
            continue

        print(f"Synthesizing {scene_id} with voice {scene_voice}")
        synthesize_with_espeak(narration, voice, output_path)
        print(f"Saved audio: {output_path}")


if __name__ == "__main__":
    main()
