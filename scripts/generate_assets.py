"""
generate_assets.py — Kaggle GPU orchestration

1. Reads script.json for CHANNEL
2. Parses IMG1/IMG2/VID prompts from each scene
3. Uploads scene_prompts.json to Kaggle dataset forts845/openmontage-prompts
4. Triggers Kaggle kernel forts845/ltx-flux-runner
5. Waits for completion (polls every 30s)
6. Downloads footage/* to projects/{CHANNEL}/footage/
7. Falls back to Pixabay stock footage if Kaggle fails
"""
import json, os, re, sys, time, subprocess, tempfile, requests
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANNEL = os.getenv("CHANNEL")
KAGGLE_USERNAME = os.getenv("KAGGLE_USERNAME", "forts845")
KAGGLE_KEY = os.getenv("KAGGLE_KEY", "")
KERNEL_ID = "forts845/ltx-flux-runner"
DATASET_ID = "forts845/openmontage-prompts"

CHANNEL_STYLES = {
    "weirdhistory": "historical archive photograph, 35mm film grain, Rembrandt lighting, chiaroscuro, amber candlelight, dark academia aesthetic",
    "crimeledger": "crime scene documentary photo, cold blue steel lighting, Fincher aesthetic, dark green teal shadows, forensic",
    "mindtactics": "psychological portrait, high contrast monochrome, single red accent, analog horror, VHS distortion aesthetic",
}

PIXABAY_KEY = os.getenv("PIXABAY_API_KEY", "")


def load_script(channel):
    p = ROOT / "projects" / channel / "script.json"
    if not p.exists():
        sys.exit(f"ERROR: {p} not found")
    return json.loads(p.read_text(encoding="utf-8"))


def parse_visual_prompts(scene):
    raw = str(scene.get("visual") or scene.get("title") or "")
    img1 = ""
    img2 = ""
    vid = ""
    m1 = re.search(r'IMG1:\s*(.+?)(?:\s*\|\s*IMG2:|$)', raw)
    m2 = re.search(r'IMG2:\s*(.+?)(?:\s*\|\s*VID:|$)', raw)
    m3 = re.search(r'VID:\s*(.+?)(?:\s*$|$)', raw)
    if m1:
        img1 = m1.group(1).strip()
    if m2:
        img2 = m2.group(1).strip()
    else:
        m2b = re.search(r'IMG2:\s*(.+)', raw)
        if m2b:
            img2 = m2b.group(1).strip()
    if m3:
        vid = m3.group(1).strip()
    else:
        m1_all = re.search(r'IMG1:\s*(.+?)(?:\s*\||$)', raw)
        if m1_all:
            remainder = raw[m1_all.end():].strip()
            m2_from_remainder = re.search(r'IMG2:\s*(.+)', remainder)
            if m2_from_remainder:
                img2 = m2_from_remainder.group(1).strip()
            m3_from_remainder = re.search(r'VID:\s*(.+)', remainder)
            if m3_from_remainder:
                vid = m3_from_remainder.group(1).strip()
    return img1, img2, vid


def write_kaggle_json():
    kaggle_dir = Path.home() / ".kaggle"
    kaggle_dir.mkdir(parents=True, exist_ok=True)
    kaggle_json = kaggle_dir / "kaggle.json"
    kaggle_json.write_text(json.dumps({"username": KAGGLE_USERNAME, "key": KAGGLE_KEY}))
    kaggle_json.chmod(0o600)


def upload_prompts(scene_prompts):
    print("Uploading scene_prompts.json to Kaggle dataset...")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        prompt_file = tmp / "scene_prompts.json"
        prompt_file.write_text(json.dumps(scene_prompts, ensure_ascii=False, indent=2))

        metadata = tmp / "dataset-metadata.json"
        metadata.write_text(json.dumps({
            "id": DATASET_ID,
            "title": "OpenMontage Prompts",
            "licenses": [{"name": "Apache 2.0"}],
        }, indent=2))

        env = os.environ.copy()
        env.update({"KAGGLE_USERNAME": KAGGLE_USERNAME, "KAGGLE_KEY": KAGGLE_KEY})
        r = subprocess.run(
            ["kaggle", "datasets", "version", "-p", str(tmp), "-m", f"update {CHANNEL} prompts"],
            capture_output=True, text=True, env=env,
        )
        if r.returncode != 0:
            # maybe dataset doesn't exist yet — try create
            r = subprocess.run(
                ["kaggle", "datasets", "create", "-p", str(tmp), "-u"],
                capture_output=True, text=True, env=env,
            )
            if r.returncode != 0:
                print(f"Dataset upload failed:\n{r.stderr}")
                return False
        print("Dataset updated OK")
        return True


def push_and_run_kernel():
    print("Pushing kernel to Kaggle...")
    env = os.environ.copy()
    env.update({"KAGGLE_USERNAME": KAGGLE_USERNAME, "KAGGLE_KEY": KAGGLE_KEY})
    r = subprocess.run(
        ["kaggle", "kernels", "push", "-p", str(ROOT / "kaggle")],
        capture_output=True, text=True, env=env,
    )
    if r.returncode != 0:
        print(f"Kernel push failed:\n{r.stderr}")
        return False
    print("Kernel pushed OK — T4 GPU run starting")
    return True


def wait_for_kernel(max_wait=3600):
    print("Waiting for Kaggle T4 GPU (polling every 30s)...")
    env = os.environ.copy()
    env.update({"KAGGLE_USERNAME": KAGGLE_USERNAME, "KAGGLE_KEY": KAGGLE_KEY})
    start = time.time()
    while time.time() - start < max_wait:
        r = subprocess.run(
            ["kaggle", "kernels", "status", KERNEL_ID],
            capture_output=True, text=True, env=env,
        )
        status = r.stdout.strip()
        elapsed = int(time.time() - start)
        print(f"  [{elapsed}s] Status: {status}")
        if "complete" in status.lower():
            return True
        if "error" in status.lower() or "cancel" in status.lower():
            print("  Kernel failed!")
            return False
        time.sleep(30)
    print("  Timeout reached")
    return False


def download_outputs(channel):
    dest = ROOT / "projects" / channel / "footage"
    dest.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({"KAGGLE_USERNAME": KAGGLE_USERNAME, "KAGGLE_KEY": KAGGLE_KEY})
    r = subprocess.run(
        ["kaggle", "kernels", "output", KERNEL_ID, "-p", str(dest)],
        capture_output=True, text=True, env=env,
    )
    if r.returncode != 0:
        print(f"Download failed:\n{r.stderr}")
        return []
    files = list(dest.iterdir())
    print(f"Downloaded {len(files)} files")
    for f in sorted(files):
        kb = f.stat().st_size // 1024 if f.is_file() else 0
        print(f"  {f.name} ({kb}KB)")
    return files


def pixabay_fallback(channel, scenes):
    print("\n=== Pixabay stock footage fallback ===")
    dest = ROOT / "projects" / channel / "footage"
    dest.mkdir(parents=True, exist_ok=True)

    for scene in scenes:
        scene_id = scene.get("id")
        if not scene_id:
            continue
        prompt = str(scene.get("visual") or scene.get("title", ""))

        photo1 = dest / f"s{scene_id}_photo1.jpg"
        photo2 = dest / f"s{scene_id}_photo2.jpg"
        video = dest / f"s{scene_id}_1.mp4"

        if not photo1.exists():
            _fetch_pixabay_image(prompt, photo1, scene_id)
        if not photo2.exists():
            _fetch_pixabay_image(prompt, photo2, scene_id + 1000)
        if not video.exists():
            _fetch_pixabay_video(prompt, video)

    count = len(list(dest.glob("*")))
    print(f"Fallback complete: {count} assets in {dest}")


def _fetch_pixabay_image(query, dest_path, seed):
    if not PIXABAY_KEY:
        return
    if dest_path.exists():
        return
    print(f"  Pixabay image: {dest_path.name}")
    try:
        r = requests.get("https://pixabay.com/api/", params={
            "key": PIXABAY_KEY, "q": query, "per_page": 3,
            "image_type": "photo", "orientation": "horizontal",
            "min_width": 1920, "min_height": 1080,
        }, timeout=30)
        r.raise_for_status()
        hits = r.json().get("hits", [])
        if hits:
            url = hits[seed % len(hits)]["largeImageURL"]
            ir = requests.get(url, timeout=60)
            ir.raise_for_status()
            dest_path.write_bytes(ir.content)
            print(f"    OK ({dest_path.stat().st_size // 1024}KB)")
    except Exception as e:
        print(f"    FAILED: {e}")


def _fetch_pixabay_video(query, dest_path):
    if not PIXABAY_KEY:
        return
    if dest_path.exists():
        return
    print(f"  Pixabay video: {dest_path.name}")
    try:
        r = requests.get("https://pixabay.com/api/videos/", params={
            "key": PIXABAY_KEY, "q": query, "per_page": 3,
            "video_type": "film", "orientation": "horizontal",
            "min_width": 1280, "min_height": 720,
        }, timeout=30)
        r.raise_for_status()
        hits = r.json().get("hits", [])
        for hit in hits:
            videos = hit.get("videos", {})
            for quality in ("large", "medium", "small"):
                src = videos.get(quality, {})
                url = src.get("url")
                if url:
                    vr = requests.get(url, timeout=120)
                    vr.raise_for_status()
                    dest_path.write_bytes(vr.content)
                    print(f"    OK ({dest_path.stat().st_size // 1024}KB)")
                    return
        print("    No suitable video found")
    except Exception as e:
        print(f"    FAILED: {e}")


def main():
    if not CHANNEL:
        sys.exit("ERROR: CHANNEL not set")
    if not KAGGLE_KEY:
        print("WARNING: KAGGLE_KEY not set — skipping Kaggle, using Pixabay fallback")
        script = load_script(CHANNEL)
        pixabay_fallback(CHANNEL, script.get("scenes", []))
        return

    script = load_script(CHANNEL)
    scenes = script.get("scenes", [])
    print(f"Generate assets for {CHANNEL}: {len(scenes)} scenes")

    build_prompts = []
    for scene in scenes:
        scene_id = scene.get("id")
        if not scene_id:
            continue
        img1, img2, vid = parse_visual_prompts(scene)
        if not img1:
            img1 = str(scene.get("title", ""))
        if not img2:
            img2 = img1
        if not vid:
            vid = img1
        build_prompts.append({
            "id": scene_id,
            "title": scene.get("title", ""),
            "img1_prompt": img1,
            "img2_prompt": img2,
            "vid_prompt": vid,
        })

    scene_prompts = {
        "channel": CHANNEL,
        "scenes": build_prompts,
    }

    write_kaggle_json()
    ok = upload_prompts(scene_prompts)

    if ok:
        ok = push_and_run_kernel()

    if ok:
        ok = wait_for_kernel()

    if ok:
        files = download_outputs(CHANNEL)
        if files:
            print(f"\nSuccess: {len(files)} assets downloaded")
            return

    print("\nKaggle pipeline failed — falling back to Pixabay stock footage")
    pixabay_fallback(CHANNEL, scenes)


if __name__ == "__main__":
    main()
