import json
import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent


def build_prompt(channel, topic):
    return (
        f"Create a highly engaging YouTube video script for the channel '{channel}' about the topic: '{topic}'.\n"
        "The script must contain exactly 14 scenes. For each scene provide a JSON object with:"
        "id, duration, narration, image_prompt, pexels_queries (5 items), type (ai_photo or broll),"
        "act (Act 1..Act 5), ken_burns (true or false). Return valid JSON only."
    )


def parse_response(response):
    if hasattr(response, "output_text") and response.output_text:
        return response.output_text

    output = getattr(response, "output", None)
    if output and isinstance(output, list):
        parts = []
        for item in output:
            content = getattr(item, "content", None)
            if isinstance(content, list):
                for block in content:
                    parts.append(getattr(block, "text", ""))
            else:
                parts.append(str(content))
        return "".join(parts)

    text = getattr(response, "text", None)
    if text:
        return text

    raise ValueError("Could not parse Gemini response")


def generate_script_with_sdk(api_key, channel, topic):
    try:
        from google import genai
    except ImportError:
        return None

    client = genai.Client(api_key=api_key)
    prompt = build_prompt(channel, topic)
    response = client.responses.create(
        model="gemini-1.5-pro",
        input=prompt,
        temperature=0.2,
        max_output_tokens=1100,
    )
    return parse_response(response)


def generate_script_with_rest(api_key, channel, topic):
    url = "https://generativelanguage.googleapis.com/v1beta2/models/gemini-1.5-pro:generate"
    prompt = build_prompt(channel, topic)
    payload = {
        "prompt": prompt,
        "temperature": 0.2,
        "maxOutputTokens": 1100,
    }
    response = requests.post(f"{url}?key={api_key}", json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    if "output" in data and data["output"]:
        return data["output"][0].get("content", "")
    return json.dumps(data)


def save_script(channel, payload):
    output_dir = ROOT / "projects" / channel
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "script.json"
    output_path.write_text(json.dumps(payload, indent=2))
    print(f"Saved script to {output_path}")


def validate_script(payload):
    if not isinstance(payload, dict) or "scenes" not in payload:
        raise ValueError("Script JSON must contain a top-level scenes array")
    scenes = payload["scenes"]
    if len(scenes) != 14:
        raise ValueError(f"Expected exactly 14 scenes, got {len(scenes)}")
    for idx, scene in enumerate(scenes, start=1):
        if not all(key in scene for key in ["id", "duration", "narration", "image_prompt", "pexels_queries", "type", "act", "ken_burns"]):
            raise ValueError(f"Scene {idx} is missing required fields")


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    channel = os.getenv("CHANNEL")
    topic = os.getenv("TOPIC")
    if not all([api_key, channel, topic]):
        raise SystemExit("Missing GEMINI_API_KEY, CHANNEL, or TOPIC environment variables")

    text = generate_script_with_sdk(api_key, channel, topic)
    if not text:
        print("SDK unavailable or failed, falling back to REST API")
        text = generate_script_with_rest(api_key, channel, topic)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Failed to decode JSON from Gemini response: {exc}\n{text}")

    validate_script(payload)
    save_script(channel, payload)


if __name__ == "__main__":
    main()
