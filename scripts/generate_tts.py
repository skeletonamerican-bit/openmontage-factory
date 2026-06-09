import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOICE_SPEAKERS = {
    "twistedtruths": "0",
    "crimeledger": "0",
    "mindtactics": "0",
}


def load_script(channel):
    script_path = ROOT / "projects" / channel / "script.json"
    if not script_path.exists():
        sys.exit(f"ERROR: Script file not found: {script_path}")
    return json.loads(script_path.read_text(encoding="utf-8"))


def synthesize_with_espeak(text, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["espeak", "-w", str(output_path), text],
        check=True,
        stderr=subprocess.DEVNULL,
        timeout=30
    )


def main():
    channel = os.getenv("CHANNEL")
    if not channel:
        sys.exit("ERROR: Missing CHANNEL environment variable")

    script = load_script(channel)
    output_dir = ROOT / "projects" / channel / "audio"
    output_dir.mkdir(parents=True, exist_ok=True)

    for scene in script.get("scenes", []):
        scene_id = scene.get("id")
        if scene_id is None:
            print("WARNING: skipping scene without id")
            continue
        narration = str(scene.get("narration", "")).strip()
        if not narration:
            print(f"WARNING: skipping scene {scene_id} with empty narration")
            continue

        output_path = output_dir / f"{scene_id}.wav"
        if output_path.exists():
            print(f"Skipping existing audio: {output_path}")
            continue

        print(f"Synthesizing scene {scene_id}")
        synthesize_with_espeak(narration, output_path)
        print(f"Saved audio: {output_path}")


if __name__ == "__main__":
    main()
