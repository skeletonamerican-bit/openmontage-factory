import os, json, time, sys
from config import get_channel_config, TEST_MODE
from scripts_data import SCRIPTS


def generate_script(channel, topic):
    if TEST_MODE:
        cfg = get_channel_config(channel)
        return _mock_script(channel, topic, cfg, num_scenes=TEST_MODE if isinstance(TEST_MODE, int) else 1)

    script = SCRIPTS[channel]

    print(f"[{channel}] Using hardcoded script with {len(script)} scenes", flush=True)

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
