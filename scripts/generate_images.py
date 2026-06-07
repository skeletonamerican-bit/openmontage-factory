import base64
import json
import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent


def load_script(channel):
    script_file = ROOT / "projects" / channel / "script.json"
    if not script_file.exists():
        raise FileNotFoundError(f"Script file not found: {script_file}")
    return json.loads(script_file.read_text())


def save_image(output_path, image_data):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_data)


def render_image(prompt, api_key):
    url = "https://generativelanguage.googleapis.com/v1beta2/images:generate"
    payload = {
        "model": "imagen-1.0",
        "prompt": prompt,
        "size": "1920x1080",
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(f"{url}?key={api_key}", json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    data = response.json()
    image_b64 = data["data"][0]["image"]
    return base64.b64decode(image_b64)


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    channel = os.getenv("CHANNEL")
    if not all([api_key, channel]):
        raise SystemExit("Missing GEMINI_API_KEY or CHANNEL environment variables")

    script = load_script(channel)
    output_dir = ROOT / "projects" / channel / "images"
    output_dir.mkdir(parents=True, exist_ok=True)

    for scene in script["scenes"]:
        scene_id = scene["id"]
        scene_prompt = (
            f"{scene['image_prompt']}. Cinematic dark drama style, moody lighting, dramatic contrast, cinematic film composition, "
            f"deep shadows and subtle rim light, 16:9, high detail, atmospheric storytelling."
        )
        output_path = output_dir / f"{scene_id}.png"
        if output_path.exists():
            print(f"Skipping existing image: {output_path}")
            continue

        for attempt in range(1, 4):
            try:
                print(f"Rendering image for {scene_id} (attempt {attempt})")
                image_bytes = render_image(scene_prompt, api_key)
                save_image(output_path, image_bytes)
                print(f"Saved image: {output_path}")
                break
            except Exception as exc:
                print(f"Image generation failed for {scene_id}: {exc}")
                if attempt == 3:
                    raise
                time.sleep(2)


if __name__ == "__main__":
    main()
