"""
kaggle_runner.py — Kaggle GPU runner for SANA-Sprint 1.6B + LTX-Video 2B
On T4 (SM >= 7): generates AI images via SANA-Sprint + AI videos via LTX-Video.
On P100 (SM < 7): downloads images from Pixabay API as fallback.
Sequential pipeline loading to fit 16GB VRAM.

Usage:
    python kaggle_runner.py [--scenes-start N] [--scenes-end N]

Reads: /kaggle/input/openmontage-prompts/scene_prompts.json
Writes: /kaggle/working/footage/scene_{i:03d}_photo_1.png, photo_2.png, video.mp4
"""
import argparse
import gc
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import torch
from PIL import Image

CHANNEL_STYLES = {
    "weirdhistory": "historical archive photograph, 35mm film grain, Rembrandt lighting, chiaroscuro, amber candlelight, dark academia",
    "crimeledger": "crime scene documentary, cold blue steel lighting, Fincher aesthetic, teal shadows, forensic atmosphere",
    "mindtactics": "psychological portrait, high contrast monochrome, red accent color, analog horror, VHS distortion",
}

PIXABAY_KEY = "55765604-3d52278fd71142a6824524b58"


def log(msg):
    print(msg, flush=True)


def cuda_stats():
    if not torch.cuda.is_available():
        return "NO GPU"
    gb = torch.cuda.memory_allocated() / 1e9
    reserved = torch.cuda.memory_reserved() / 1e9
    return f"alloc={gb:.1f}GB, reserved={reserved:.1f}GB"


def detect_gpu():
    if not torch.cuda.is_available():
        sys.exit("ERROR: No GPU detected")
    name = torch.cuda.get_device_name(0)
    props = torch.cuda.get_device_properties(0)
    cap = props.major * 10 + props.minor
    vram = props.total_memory / 1e9
    log(f"  GPU: {name} | SM {props.major}.{props.minor} | VRAM: {vram:.1f}GB")
    return props.major >= 7


def load_prompts():
    paths = [
        Path("/kaggle/input/openmontage-prompts/scene_prompts.json"),
        Path("/kaggle/working/scene_prompts.json"),
        Path("/kaggle/working/openmontage-factory/scene_prompts.json"),
    ]
    for p in paths:
        if p.exists():
            with open(p) as f:
                return json.load(f)
    log("WARNING: scene_prompts.json not found — generating default test prompts")
    default_scenes = [
        {"id": 1, "title": "The Lost City of Atlantis", "img1_prompt": "ruined columns underwater, sunbeams filtering through, ancient stone carvings, deep ocean", "img2_prompt": "aerial view of geometric patterns on ocean floor, sonar mapping visualization", "vid_prompt": "slow reveal of underwater ruins, particles drifting in light beams, mysterious atmosphere"},
        {"id": 2, "title": "Medieval Alchemist's Workshop", "img1_prompt": "cluttered stone workshop with glass vials, bubbling liquids, candlelight, aged manuscripts", "img2_prompt": "close-up of alchemist's hands holding glowing potion, dust particles in light beam", "vid_prompt": "candle flames flicker as liquid bubbles in flask, steam rises, magical atmosphere"},
        {"id": 3, "title": "Forgotten Soviet Space Program", "img1_prompt": "abandoned rocket silo overgrown with moss, faded hammer and sickle, industrial decay", "img2_prompt": "retro Soviet space poster peeling on concrete wall, cold war aesthetic", "vid_prompt": "camera pans across abandoned control room, dust motes in dim light, eerie silence"},
        {"id": 4, "title": "The Phantom Clockmaker", "img1_prompt": "dusty clockmaker shop filled with antique timepieces, cobwebs, single lantern glow", "img2_prompt": "close-up of intricate clockwork mechanism, brass gears, precision engineering, vintage", "vid_prompt": "clock pendulums swing in slow motion, shadows flicker, gears turn with creaking sound"},
        {"id": 5, "title": "Library of Babel", "img1_prompt": "infinite hexagonal library, bookshelves stretching to vanishing point, warm amber light", "img2_prompt": "ancient leather-bound book open on reading desk, ornate illustrations, candle beside", "vid_prompt": "slow dolly zoom through endless bookshelves, pages flutter, dust dances in light"},
    ]
    return {"channel": "weirdhistory", "scenes": default_scenes}


def inject_style(raw_prompt, channel):
    style = CHANNEL_STYLES.get(channel, "")
    if style:
        return f"{style}, {raw_prompt}"
    return raw_prompt


def make_image_sana(pipe, prompt, out_path, seed):
    if out_path.exists():
        log(f"    SKIP {out_path.name} (exists)")
        return True
    try:
        result = pipe(
            prompt=prompt,
            num_inference_steps=2,
            generator=torch.Generator(device="cpu").manual_seed(seed),
        )
        img = result.images[0]
        # SANA generates 1024x1024 — center-crop to 16:9, then upscale to 1920x1080
        crop_h = int(img.width * 9 / 16)
        top = (img.height - crop_h) // 2
        img = img.crop((0, top, img.width, top + crop_h))
        img = img.resize((1920, 1080), Image.LANCZOS)
        img.save(str(out_path))
        return True
    except Exception as e:
        log(f"    SANA FAILED: {e}")
        return False


def make_image_pixabay(prompt, out_path, page=1):
    if out_path.exists():
        return True
    try:
        q = urllib.parse.quote(prompt[:100])
        url = f"https://pixabay.com/api/?key={PIXABAY_KEY}&q={q}&per_page=5&page={page}&orientation=horizontal&image_type=photo&safesearch=true&min_width=1280"
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        hits = data.get("hits", [])
        if not hits:
            log(f"    Pixabay: no results for '{prompt[:40]}...'")
            return False
        img_url = hits[0]["largeImageURL"]
        log(f"    Pixabay: {img_url.split('/')[-1][:50]}")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        req = urllib.request.Request(img_url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            img_data = resp.read()
        with open(out_path, "wb") as f:
            f.write(img_data)
        img = Image.open(out_path)
        if img.size != (1920, 1080):
            img = img.resize((1920, 1080), Image.LANCZOS)
            img.save(str(out_path))
        return True
    except Exception as e:
        log(f"    Pixabay FAILED: {e}")
        return False


def generate_all_images_t4(scenes, channel, out_dir, scenes_start, scenes_end):
    log("\n=== PHASE 1: SANA-Sprint 1.6B (T4 GPU) ===")
    log(f"CUDA before model load: {cuda_stats()}")

    from diffusers import SanaPipeline
    pipe = SanaPipeline.from_pretrained(
        "Efficient-Large-Model/Sana_Sprint_1.6B_1024px",
        torch_dtype=torch.float16,
    )
    pipe.enable_model_cpu_offload()
    log(f"CUDA after model load: {cuda_stats()}")

    ok_count = 0
    fail_count = 0
    for idx in range(scenes_start, scenes_end):
        scene = scenes[idx]
        scene_id = scene.get("id", idx + 1)
        prefix = f"s{idx:03d}"
        img1_prompt = scene.get("photo_prompt_1") or scene.get("img1_prompt") or scene.get("title", "")
        img2_prompt = scene.get("photo_prompt_2") or scene.get("img2_prompt") or scene.get("title", "")
        photo1 = out_dir / f"{prefix}_photo1.jpg"
        photo2 = out_dir / f"{prefix}_photo2.jpg"

        log(f"  [{idx + 1 - scenes_start}/{scenes_end - scenes_start}] photo1...")
        ok1 = make_image_sana(pipe, inject_style(img1_prompt, channel), photo1, scene_id)
        log(f"    -> {photo1.name} {'OK' if ok1 else 'FAIL'}")

        log(f"  [{idx + 1 - scenes_start}/{scenes_end - scenes_start}] photo2...")
        ok2 = make_image_sana(pipe, inject_style(img2_prompt, channel), photo2, scene_id + 1000)
        log(f"    -> {photo2.name} {'OK' if ok2 else 'FAIL'}")

        photo3 = out_dir / f"{prefix}_photo3.jpg"
        img3_prompt = scene.get("photo_prompt_3") or scene.get("img1_prompt") or scene.get("title", "")
        log(f"  [{idx + 1 - scenes_start}/{scenes_end - scenes_start}] photo3...")
        ok3 = make_image_sana(pipe, inject_style(img3_prompt, channel), photo3, scene_id + 2000)
        log(f"    -> {photo3.name} {'OK' if ok3 else 'FAIL'}")

        if ok1: ok_count += 1
        else: fail_count += 1
        if ok2: ok_count += 1
        else: fail_count += 1
        if ok3: ok_count += 1
        else: fail_count += 1

    log(f"Images done: {ok_count} OK, {fail_count} FAIL")
    del pipe
    gc.collect()
    torch.cuda.empty_cache()


def generate_all_images_pixabay(scenes, channel, out_dir, scenes_start, scenes_end):
    log("\n=== PHASE 1: Pixabay (P100 fallback) ===")

    ok_count = 0
    fail_count = 0
    for idx in range(scenes_start, scenes_end):
        scene = scenes[idx]
        prefix = f"s{idx:03d}"
        title = scene.get("title", "")
        photo1 = out_dir / f"{prefix}_photo1.jpg"
        photo2 = out_dir / f"{prefix}_photo2.jpg"

        log(f"  [{idx + 1 - scenes_start}/{scenes_end - scenes_start}] photo1...")
        ok1 = make_image_pixabay(title, photo1, page=1)
        log(f"    -> {photo1.name} {'OK' if ok1 else 'FAIL'}")

        log(f"  [{idx + 1 - scenes_start}/{scenes_end - scenes_start}] photo2...")
        ok2 = make_image_pixabay(title, photo2, page=2)
        log(f"    -> {photo2.name} {'OK' if ok2 else 'FAIL'}")

        photo3 = out_dir / f"{prefix}_photo3.jpg"
        log(f"  [{idx + 1 - scenes_start}/{scenes_end - scenes_start}] photo3...")
        ok3 = make_image_pixabay(title, photo3, page=3)
        log(f"    -> {photo3.name} {'OK' if ok3 else 'FAIL'}")

        if ok1: ok_count += 1
        else: fail_count += 1
        if ok2: ok_count += 1
        else: fail_count += 1
        if ok3: ok_count += 1
        else: fail_count += 1

    log(f"Images done: {ok_count} OK, {fail_count} FAIL")


def make_ltx_video(pipe, prompt, out_path):
    if out_path.exists():
        log(f"    SKIP {out_path.name} (exists)")
        return True
    try:
        result = pipe(
            prompt=prompt,
            negative_prompt="blurry, low quality, watermark, text, distorted",
            width=1280, height=704,
            num_frames=97,
            num_inference_steps=8,
            guidance_scale=3.0,
        )
        frames = result.frames[0]
        import imageio
        imageio.mimwrite(
            str(out_path), frames,
            fps=30, quality=8,
            output_params=["-vcodec", "libx264", "-pix_fmt", "yuv420p"],
        )
        return True
    except Exception as e:
        log(f"    FAILED: {e}")
        return False


def generate_all_ltx(scenes, channel, out_dir, scenes_start, scenes_end):
    log("\n=== PHASE 2: LTX-Video 2B ===")
    log(f"CUDA before LTX load: {cuda_stats()}")

    from diffusers import LTXPipeline
    ltx = LTXPipeline.from_pretrained(
        "Lightricks/LTX-Video",
        torch_dtype=torch.float16,
    )
    ltx.enable_model_cpu_offload()
    ltx.vae.enable_tiling()
    ltx.enable_attention_slicing()
    log(f"CUDA after LTX load: {cuda_stats()}")

    ok_count = 0
    fail_count = 0
    skip_count = 0
    for idx in range(scenes_start, scenes_end):
        scene = scenes[idx]
        prefix = f"s{idx:03d}"

        # LTX-Video only for every 3rd scene to save time
        if idx % 3 != 0:
            log(f"  [{idx + 1 - scenes_start}/{scenes_end - scenes_start}] video... SKIP (no LTX for scene {idx})")
            skip_count += 1
            continue

        vid_prompt = scene.get("video_prompt") or scene.get("vid_prompt") or scene.get("title", "")
        video = out_dir / f"{prefix}_video.mp4"

        log(f"  [{idx + 1 - scenes_start}/{scenes_end - scenes_start}] video...")
        ok = make_ltx_video(ltx, inject_style(vid_prompt, channel), video)
        log(f"    -> {video.name} {'OK' if ok else 'FAIL'}")

        if ok: ok_count += 1
        else: fail_count += 1

    log(f"LTX done: {ok_count} OK, {fail_count} FAIL, {skip_count} SKIP (scene%3!=0)")
    del ltx
    gc.collect()
    torch.cuda.empty_cache()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes-start", type=int, default=0)
    parser.add_argument("--scenes-end", type=int, default=None)
    args = parser.parse_args()

    log("=== SANA-Sprint + LTX Runner ===")
    log(f"PyTorch: {torch.__version__}")
    log(f"CUDA available: {torch.cuda.is_available()}")

    is_t4 = detect_gpu()

    data = load_prompts()
    channel = data.get("channel", "weirdhistory")
    scenes = data.get("scenes", [])
    total = len(scenes)
    log(f"Channel: {channel} | Total scenes: {total}")

    scenes_end = args.scenes_end if args.scenes_end is not None else total
    scenes_start = min(args.scenes_start, total)
    scenes_end = min(scenes_end, total)
    log(f"Processing scenes: {scenes_start} to {scenes_end - 1} ({scenes_end - scenes_start} scenes)")

    out_dir = Path("/kaggle/working/footage")
    out_dir.mkdir(parents=True, exist_ok=True)

    if is_t4:
        generate_all_images_t4(scenes, channel, out_dir, scenes_start, scenes_end)
        generate_all_ltx(scenes, channel, out_dir, scenes_start, scenes_end)
    else:
        log("P100 detected — SDXL/LTX GPU kernels not available in this PyTorch build.")
        log("Using Pixabay API for images (free stock photos). Videos skipped.")
        generate_all_images_pixabay(scenes, channel, out_dir, scenes_start, scenes_end)

    log("\n=== Summary ===")
    files = sorted(out_dir.iterdir())
    log(f"Total assets: {len(files)}")
    for f in files:
        kb = f.stat().st_size // 1024 if f.is_file() else 0
        log(f"  {f.name} ({kb}KB)")
    log("=== Done ===")


if __name__ == "__main__":
    main()
