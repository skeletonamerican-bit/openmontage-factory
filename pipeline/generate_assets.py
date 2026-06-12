import os, json, time, requests, subprocess, zipfile, re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import get_channel_config, KAGGLE_USERNAME, KAGGLE_KERNEL, PIXABAY_API_KEY, TEST_MODE, PHOTO_COUNT

ASSETS_DIR = Path("output/assets")
IMAGES_DIR = ASSETS_DIR / "images"
VIDEOS_DIR = ASSETS_DIR / "videos"
MUSIC_DIR = Path("output/music")
SFX_DIR = Path("output/sfx")

for d in [IMAGES_DIR, VIDEOS_DIR, MUSIC_DIR, SFX_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def generate_assets(channel, script):
    cfg = get_channel_config(channel)
    scenes = script if isinstance(script, list) else script.get("scenes", script)

    if TEST_MODE:
        return _generate_test_assets(channel, scenes)

    result = {"scene_assets": {}, "music": None, "sfx": None}

    try:
        kaggle_result = _run_kaggle_kernel(channel, scenes, cfg)
        result["scene_assets"] = kaggle_result
    except Exception as e:
        print(f"Kaggle failed: {e}, falling back to Pixabay")
        pixabay_result = _pixabay_fallback(scenes)
        result["scene_assets"] = pixabay_result

    music_path = _generate_music(channel, cfg)
    sfx_path = _generate_sfx(channel, cfg)
    result["music"] = music_path
    result["sfx"] = sfx_path

    meta_path = ASSETS_DIR / "asset_manifest.json"
    json.dump(result, open(meta_path, "w"), indent=2, default=str)

    return result


def _run_kaggle_kernel(channel, scenes, cfg):
    kernel_slug = KAGGLE_KERNEL
    prompts = [s.get("image_prompt", "") for s in scenes]

    payload = json.dumps({
        "channel": channel,
        "scenes": len(scenes),
        "prompts": prompts,
        "style": cfg["style"],
        "resolution": "1920x1080",
    })

    payload_path = ASSETS_DIR / "kaggle_payload.json"
    json.dump({"payload": payload}, open(payload_path, "w"))

    try:
        result = subprocess.run(
            ["kaggle", "kernels", "push", "--kernel", kernel_slug,
             "--kernel-path", str(payload_path)],
            capture_output=True, text=True, timeout=60,
        )
        print(f"Kaggle push: {result.stdout}")
    except Exception as e:
        print(f"Kaggle push failed: {e}")
        raise

    kernel_id = f"{KAGGLE_USERNAME}/openmontage-sana-ltx-runner"
    output_dir = ASSETS_DIR / "kaggle_output"
    output_dir.mkdir(exist_ok=True)

    for attempt in range(90):
        time.sleep(20)
        try:
            result = subprocess.run(
                ["kaggle", "kernels", "status", kernel_id],
                capture_output=True, text=True, timeout=30,
            )
            status = result.stdout.strip().lower()
            print(f"Kaggle status [{attempt+1}/90]: {status}")

            if "complete" in status:
                subprocess.run(
                    ["kaggle", "kernels", "output", kernel_id,
                     "--path", str(output_dir)],
                    capture_output=True, timeout=60,
                )
                break
            elif "error" in status or "failed" in status:
                raise RuntimeError(f"Kaggle kernel failed: {status}")
        except Exception as e:
            if attempt > 10:
                raise

    scene_assets = _extract_kaggle_output(output_dir, scenes)
    return scene_assets


def _extract_kaggle_output(output_dir, scenes):
    asset_pattern = re.compile(r's(\d+)_(photo[123]|video)\.')

    for z in output_dir.glob("*.zip"):
        with zipfile.ZipFile(z) as zf:
            zf.extractall(output_dir)

    scene_assets = {}
    for f in sorted(output_dir.iterdir()):
        m = asset_pattern.match(f.name.lower())
        if not m:
            continue
        idx = int(m.group(1))
        kind = m.group(2)
        if idx not in scene_assets:
            scene_assets[idx] = {"photos": [], "video": None}
        if kind == "video":
            scene_assets[idx]["video"] = str(f)
        elif kind.startswith("photo"):
            scene_assets[idx]["photos"].append(str(f))

    return scene_assets


def _pixabay_fallback(scenes):
    if not PIXABAY_API_KEY:
        print("No PIXABAY_API_KEY, using placeholder images")
        return _generate_placeholders(scenes)

    scene_assets = {}
    for scene in scenes:
        si = scene.get("scene", 0)
        keywords = scene.get("keywords", [])
        query = "+".join(keywords[:3]) if keywords else "background"
        url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}&image_type=photo&per_page=5"

        photos = []
        try:
            resp = requests.get(url, timeout=15)
            data = resp.json()
            hits = data.get("hits", [])
            for pi in range(PHOTO_COUNT):
                if pi < len(hits):
                    img_url = hits[pi]["largeImageURL"]
                    ext = img_url.rsplit(".", 1)[-1][:4]
                    out_path = IMAGES_DIR / f"scene_{si:03d}_photo{pi+1}.{ext}"
                    img_data = requests.get(img_url, timeout=30).content
                    out_path.write_bytes(img_data)
                    photos.append(str(out_path))
                else:
                    photos.append(_placeholder_image(si, pi))
        except Exception as e:
            print(f"Pixabay error for scene {si}: {e}")
            for pi in range(PHOTO_COUNT):
                photos.append(_placeholder_image(si, pi))
        scene_assets[si] = {"photos": photos, "video": None}

    return scene_assets


def _generate_placeholders(scenes):
    scene_assets = {}
    for scene in scenes:
        si = scene.get("scene", 0)
        photos = [_placeholder_image(si, pi) for pi in range(PHOTO_COUNT)]
        scene_assets[si] = {"photos": photos, "video": None}
    return scene_assets


def _placeholder_image(scene_num, photo_idx=0):
    label = f"Scene {scene_num}" if photo_idx == 0 else f"Scene {scene_num} - {photo_idx+1}"
    out_path = IMAGES_DIR / f"scene_{scene_num:03d}_photo{photo_idx+1}.png"
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (1920, 1080), (20, 20, 30))
        draw = ImageDraw.Draw(img)
        draw.text((960, 540), label, fill=(200, 200, 200))
        img.save(out_path)
    except ImportError:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"color=c=#14141e:s=1920x1080:d=5",
             "-vf", f"drawtext=text='{label}':x=(w-text_w)/2:y=(h-text_h)/2:fontsize=48:fontcolor=white",
             str(out_path)],
            capture_output=True,
        )
    return str(out_path)


def _generate_test_assets(channel, scenes):
    scene_assets = {}
    for scene in scenes:
        si = scene.get("scene", 0)
        photos = [_placeholder_image(si, pi) for pi in range(PHOTO_COUNT)]
        scene_assets[si] = {"photos": photos, "video": None}

    music_path = MUSIC_DIR / "bg_music.mp3"
    sfx_path = SFX_DIR / "sfx.mp3"

    if not music_path.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             "anoisesrc=d=300:c=pink:a=48000",
             "-ar", "44100", str(music_path)],
            capture_output=True,
        )

    if not sfx_path.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             "anoisesrc=d=5:c=brown:a=48000",
             "-ar", "44100", str(sfx_path)],
            capture_output=True,
        )

    return {
        "scene_assets": scene_assets,
        "music": str(music_path),
        "sfx": str(sfx_path),
    }


def _generate_music(channel, cfg):
    music_path = MUSIC_DIR / "bg_music.mp3"
    bpm = cfg.get("music_bpm", 70)
    duration = 300
    sample_rate = 44100

    import math, struct
    import numpy as np

    try:
        import soundfile as sf
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        beat_interval = 60.0 / bpm
        beat_signal = np.sin(2 * np.pi * t / beat_interval)
        ambience = np.random.randn(len(t)) * 0.02
        low_drone = 0.15 * np.sin(2 * np.pi * 55 * t)
        signal = (beat_signal * 0.08 + ambience + low_drone)
        signal = np.clip(signal, -1, 1).astype(np.float32)
        sf.write(str(music_path), signal, sample_rate)
    except ImportError:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"anoisesrc=d={duration}:c=pink:a=44100",
             "-af", f"volume=0.1", str(music_path)],
            capture_output=True,
        )

    return str(music_path)


def _generate_sfx(channel, cfg):
    sfx_path = SFX_DIR / "sfx.mp3"
    sfx_type = cfg.get("sfx", "boom")
    duration_map = {"boom": 3, "thud": 2, "static": 4}
    dur = duration_map.get(sfx_type, 2)

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"anoisesrc=d={dur}:c=brown:a=44100",
         "-af", "volume=0.3", str(sfx_path)],
        capture_output=True,
    )

    return str(sfx_path)
