import os, json

CHANNELS = {
    "weirdhistory": {
        "scenes": 84,
        "voice": "am_michael",
        "edge_voice": "en-US-GuyNeural",
        "style": "chiaroscuro lighting, 35mm film grain, dark medieval, candlelight, gothic architecture, historical archive photo style, amber shadows, ultra detailed",
        "color_grade": "eq=brightness=-0.05:contrast=1.35:saturation=0.55,curves=m=0/0:0.5/0.45:1/0.85,noise=alls=10:allf=t,vignette=angle=PI/4",
        "sfx": "boom",
        "music_bpm": 70,
    },
    "crimeledger": {
        "scenes": 72,
        "voice": "am_adam",
        "edge_voice": "en-US-GuyNeural",
        "style": "Fincher aesthetic, cold blue teal grade, forensic overhead lighting, crime scene documentation, desaturated, sharp focus, ultra detailed",
        "color_grade": "eq=brightness=-0.02:contrast=1.25:saturation=0.35,colorchannelmixer=rr=0.75:gg=0.85:bb=1.20,unsharp=lx=5:ly=5:la=0.8",
        "sfx": "thud",
        "music_bpm": 80,
    },
    "mindtactics": {
        "scenes": 60,
        "voice": "af_bella",
        "edge_voice": "en-US-JennyNeural",
        "style": "analog horror photography, VHS artifact texture, monochrome with red accent, deep shadows, psychological thriller, claustrophobic framing, ultra detailed",
        "color_grade": "hue=s=0.15,eq=contrast=1.45:brightness=-0.03,curves=m=0/0:0.3/0.55:1/1.0,noise=alls=15:allf=t",
        "sfx": "static",
        "music_bpm": 60,
    }
}

SCENE_DUR = 15
PHOTO_DUR = 5
VIDEO_DUR = 5
PHOTO_COUNT = 3
CROSSFADE = 0.3
FPS = 30
RESOLUTION = "1920x1080"
CRF = 23
AUDIO_BITRATE = "192k"

LLM_MODELS = [
    "qwen/qwen3-coder:free",
    "deepseek/deepseek-v4-flash:free",
    "openai/gpt-oss-20b:free",
    "nvidia/nemotron-3-ultra:free",
    "google/gemini-2.0-flash-exp:free",
]

KAGGLE_USERNAME = os.environ.get("KAGGLE_USERNAME", "forts845")
KAGGLE_KERNEL = f"{KAGGLE_USERNAME}/openmontage-sana-ltx-runner"
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")

_test_mode_env = os.environ.get("TEST_MODE", "")
if _test_mode_env and _test_mode_env.isdigit():
    TEST_MODE = int(_test_mode_env)
elif _test_mode_env:
    TEST_MODE = True
else:
    TEST_MODE = False

def get_channel_config(channel):
    return CHANNELS.get(channel, CHANNELS["weirdhistory"])
