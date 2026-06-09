import json
import os
import re
import sys
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parent.parent
CEREBRAS_API_URL = "https://api.cerebras.ai/v1/chat/completions"
CHANNEL_CONFIGS = {
    "twistedtruths": {"style": "corporate betrayal and revenge drama", "scene_count": 12, "total_seconds": 12 * 60},
    "crimeledger": {"style": "financial crime documentary", "scene_count": 14, "total_seconds": 18 * 60},
    "mindtactics": {"style": "dark psychology and manipulation", "scene_count": 10, "total_seconds": 10 * 60},
}
PROMPT_TEMPLATE = (
    "Generate a YouTube video script in strict JSON format. "
    "Return only valid JSON, without markdown fences or commentary. "
    "The output must be an object with keys: title, description, tags, scenes. "
    "Each scene must contain: id, title, narration, visual, duration_seconds, emotion. "
    "Do not include any extra keys. "
    "Channel style: {style}. Topic: {topic}. "
    "Create exactly {scene_count} scenes totaling {total_seconds} seconds. "
    "Use compelling, documentary-style language suitable for YouTube." 
)


def get_env(key):
    value = os.environ.get(key, "").strip()
    if not value:
        sys.exit(f"ERROR: Missing env var: {key}")
    return value


def http_post(url, api_key, payload):
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Cerebras HTTP {exc.code}: {body}")
    except Exception as exc:
        raise RuntimeError(f"Cerebras request failed: {exc}")


def generate_fallback_script(channel, topic, config):
    title = f"{topic}: A {config['style']} Story"
    description = (
        f"A compelling {config['style']} documentary-style video about {topic}. "
        "This script is created as a fallback to keep the pipeline running when API access is unavailable."
    )
    tags = [topic.lower().replace(" ", "-"), channel, "documentary", "betrayal", "drama"]
    scenes = []
    for idx in range(1, config["scene_count"] + 1):
        visual_desc = f"Stock footage scene {idx} with dramatic lighting, tense characters, and cinematic motion."
        scenes.append({
            "id": idx,
            "title": f"Chapter {idx}",
            "narration": (
                f"Scene {idx} of a {config['style']} true story about {topic}. "
                "This narration sets the mood, describes the action, and builds suspense for the next scene."
            ),
            "visual": visual_desc,
            "image_prompt": f"Dramatic cinematic scene {idx} of a story about {topic}, moody lighting, intense characters",
            "duration_seconds": max(10, config["total_seconds"] // config["scene_count"]),
            "emotion": "suspense",
        })
    remainder = config["total_seconds"] - sum(scene["duration_seconds"] for scene in scenes)
    scenes[-1]["duration_seconds"] += remainder
    return {"title": title, "description": description, "tags": tags, "scenes": scenes}


def strip_markdown(text):
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^>.*$", "", text, flags=re.M)
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    return text.strip()


def extract_json(text):
    text = strip_markdown(text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Could not locate JSON object in response")
    return text[start:end + 1]


def normalize_scene(scene, index):
    if not isinstance(scene, dict):
        raise ValueError(f"Scene {index} is not an object")

    scene_id = scene.get("id")
    if isinstance(scene_id, str) and scene_id.isdigit():
        scene_id = int(scene_id)
    if not isinstance(scene_id, int):
        scene_id = index

    title = str(scene.get("title", "")).strip() or f"Scene {index}"
    narration = str(scene.get("narration", "")).strip()
    visual = str(scene.get("visual", "")).strip() or narration[:100]
    image_prompt = str(scene.get("image_prompt", scene.get("visual", visual))).strip()
    emotion = str(scene.get("emotion", "")).strip() or "suspense"
    duration_seconds = scene.get("duration_seconds")
    try:
        duration_seconds = int(duration_seconds)
    except (TypeError, ValueError):
        duration_seconds = 60
    if duration_seconds < 10:
        duration_seconds = 60

    if not narration:
        raise ValueError(f"Scene {index} is missing narration")

    return {
        "id": scene_id,
        "title": title,
        "narration": narration,
        "visual": visual,
        "image_prompt": image_prompt,
        "duration_seconds": duration_seconds,
        "emotion": emotion,
    }


def adjust_durations(scenes, target_seconds):
    total = sum(scene["duration_seconds"] for scene in scenes)
    if total <= 0:
        per_scene = max(10, target_seconds // len(scenes))
        for scene in scenes:
            scene["duration_seconds"] = per_scene
    else:
        ratio = float(target_seconds) / total
        for scene in scenes:
            scene["duration_seconds"] = max(10, int(round(scene["duration_seconds"] * ratio)))
    diff = target_seconds - sum(scene["duration_seconds"] for scene in scenes)
    scenes[-1]["duration_seconds"] += diff
    return scenes


def validate_script(payload, config):
    if not isinstance(payload, dict):
        raise ValueError("Script must be a JSON object")
    for key in ("title", "description", "tags", "scenes"):
        if key not in payload:
            raise ValueError(f"Missing top-level key: {key}")
    if not isinstance(payload["tags"], list):
        raise ValueError("tags must be a list")
    scenes = payload["scenes"]
    if not isinstance(scenes, list):
        raise ValueError("scenes must be a list")
    if len(scenes) != config["scene_count"]:
        raise ValueError(f"Expected exactly {config['scene_count']} scenes, got {len(scenes)}")
    return [normalize_scene(scene, idx) for idx, scene in enumerate(scenes, start=1)]


def main():
    channel = os.environ.get("CHANNEL", "twistedtruths").strip().lower()
    topic = get_env("TOPIC")
    api_key = os.environ.get("CEREBRAS_API_KEY", "").strip()

    if channel not in CHANNEL_CONFIGS:
        sys.exit(f"ERROR: Unsupported CHANNEL '{channel}'")

    config = CHANNEL_CONFIGS[channel]
    prompt = f"You are a YouTube documentary scriptwriter. Create a faceless documentary script.\nStyle: {config['style']}\nTopic: {topic}\nTotal duration: {config['total_seconds']} seconds, {config['scene_count']} scenes.\n\nReturn ONLY valid JSON, no markdown:\n{{\"title\":\"compelling title\",\"description\":\"description\",\"tags\":[],\"scenes\":[{{\"id\":1,\"title\":\"scene title\",\"narration\":\"narration text\",\"visual\":\"stock footage description\",\"duration_seconds\":60,\"emotion\":\"suspense\"}}]}}"
    
    print(f"📝 Channel : {channel}")
    print(f"📌 Topic   : {topic}")

    payload = None
    if api_key:
        print("⏳ Generating script via Cerebras...")
        try:
            response = http_post(CEREBRAS_API_URL, api_key, {
                "model": "llama-3.3-70b",
                "messages": [{"role": "user", "content": prompt}],
                "max_completion_tokens": 2048,
                "temperature": 0.2
            })
            raw_text = None
            if isinstance(response, dict):
                choices = response.get("choices", [])
                if choices:
                    raw_text = choices[0].get("message", {}).get("content")
            if raw_text is None:
                raise RuntimeError("Cerebras response did not contain textual output")
            script_text = extract_json(raw_text)
            payload = json.loads(script_text)
        except Exception as exc:
            print(f"WARNING: Cerebras generation failed: {exc}")
    else:
        print("WARNING: CEREBRAS_API_KEY is not set. Skipping Cerebras request.")

    if payload is None:
        print("WARNING: Falling back to local script generation.")
        payload = generate_fallback_script(channel, topic, config)

    scenes = validate_script(payload, config)
    scenes = adjust_durations(scenes, config["total_seconds"])
    payload["scenes"] = scenes
    payload["title"] = payload.get("title", topic)
    payload["description"] = payload.get("description", "")
    payload["tags"] = payload.get("tags", [topic])

    out_dir = ROOT / "projects" / channel
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "script.json"
    out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Script saved: {out_file}")
    print(f"   Scenes : {len(scenes)}")
    total_sec = sum(scene["duration_seconds"] for scene in scenes)
    print(f"   Duration: ~{total_sec // 60}m {total_sec % 60}s")


if __name__ == "__main__":
    main()
