import os, json
from config import get_channel_config, LLM_MODELS, TEST_MODE
from llm_router import LLMRouter

def generate_script(channel, topic):
    cfg = get_channel_config(channel)
    router = LLMRouter()

    if TEST_MODE:
        return _mock_script(channel, topic, cfg)

    num_scenes = 1 if TEST_MODE else cfg["scenes"]
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

Generate a complete script as a JSON array of scene objects."""

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

    if TEST_MODE:
        script = script[:1]

    return script


def _mock_script(channel, topic, cfg):
    return [
        {
            "scene": 1,
            "narration": f"This is a test video for {channel} about {topic}. The following scenes will explore this fascinating topic in depth.",
            "image_prompt": f"{cfg['style']}, {topic} concept art, cinematic lighting",
            "image_style": cfg["style"],
            "keywords": [topic, channel, "documentary"],
        }
    ]
