import os, json, time, sys
from config import get_channel_config, LLM_MODELS, TEST_MODE
from llm_router import LLMRouter

def generate_script(channel, topic):
    cfg = get_channel_config(channel)
    router = LLMRouter()

    if TEST_MODE:
        return _mock_script(channel, topic, cfg, num_scenes=TEST_MODE if isinstance(TEST_MODE, int) else 1)

    num_scenes = cfg["scenes"]
    style = cfg["style"]

    system_prompt = """You are a professional video scriptwriter. Generate a structured script for a faceless YouTube video.

SCENE FORMAT (return a valid JSON array):
[
  {
    "scene": 1,
    "narration": "Narrator text for this scene (15-25 seconds when spoken)",
    "image_prompt": "detailed text-to-image prompt for this scene's visual",
    "image_style": "visual style description",
    "keywords": ["comma-separated", "search", "keywords"]
  }
]

Rules:
- Each scene narration = 15-25 seconds of speech
- Image prompts must be detailed, cinematic, self-contained
- Keywords are for stock photo search (Pixabay fallback)
- Return ONLY the JSON array, no other text"""

    user_prompt = f"""Channel: {channel}
Topic: {topic}
Number of scenes: {num_scenes}
Visual style: {style}

IMPORTANT: Scene 0 is the HOOK — the very first scene. It must grab attention immediately.
For scene 0:
  video_prompt must include: "dramatic reveal, extreme close-up, high contrast, shocking moment, cinematic opener" combined with the channel's visual style
  narration must be a gripping question or shocking fact that hooks the viewer
  Mark scene 0 with HOOK=True

Generate a complete script as a JSON array of {num_scenes} scene objects.
Return ONLY valid JSON array, no other text."""

    print(f"[{channel}] Generating {num_scenes} scenes in one request...")
    sys.stdout.flush()

    raw = router.call(system_prompt, user_prompt)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    script = json.loads(raw)
    if isinstance(script, dict) and "scenes" in script:
        script = script["scenes"]
    if not isinstance(script, list):
        raise ValueError(f"Script must be a list, got {type(script)}")

    if script and isinstance(script[0], dict):
        style = cfg["style"]
        script[0]["video_prompt"] = f"dramatic reveal, extreme close-up, high contrast, shocking moment, cinematic opener, {style}"
        script[0]["HOOK"] = True

    for i, scene in enumerate(script):
        print(f"[{channel}] Генерация сцены {i+1}/{len(script)}...")
        sys.stdout.flush()
        time.sleep(2)

    return script


def _mock_script(channel, topic, cfg, num_scenes=1):
    results = []
    for i in range(num_scenes):
        results.append({
            "scene": i,
            "narration": f"This is scene {i+1} of {num_scenes} for {channel} about {topic}. The following scenes will explore this fascinating topic in depth." if i > 0 else f"Did you know that {topic} hides a truth most people never see? This is {channel}.",
            "video_prompt": f"dramatic reveal, extreme close-up, high contrast, shocking moment, cinematic opener, {cfg['style']}, {topic}" if i == 0 else f"{cfg['style']}, {topic} scene {i+1}, cinematic lighting",
            "image_prompt": f"{cfg['style']}, {topic} concept art, cinematic lighting",
            "image_style": cfg["style"],
            "keywords": [topic, channel, "documentary"],
            "HOOK": True if i == 0 else False,
        })
    return results
