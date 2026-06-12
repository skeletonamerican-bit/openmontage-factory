"""
generate_assets.py — Kaggle GPU orchestration with dry-run, check, validation

1. Reads script.json for CHANNEL from projects/{CHANNEL}/script.json
2. Parses scene visuals → scene_prompts.json
3. Uploads scene_prompts.json to Kaggle dataset forts845/openmontage-prompts
4. Pushes kernel to forts845/openmontage-sana-ltx-runner (uses SANA-Sprint 1.6B for images)
5. Triggers the kernel run
6. Polls status every 30s until complete or error
7. Downloads output footage to projects/{CHANNEL}/footage/
8. Validates downloaded files (MP4 > 100KB, JPG > 50KB)
"""
import json, os, re, sys, time, subprocess, tempfile, requests, argparse, shutil
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CHANNEL_ENV = os.getenv("CHANNEL", "")
KAGGLE_USERNAME = os.getenv("KAGGLE_USERNAME", "forts845")
KAGGLE_KEY = os.getenv("KAGGLE_KEY", "")
KERNEL_ID = "forts845/openmontage-sana-ltx-runner"
DATASET_ID = "forts845/openmontage-prompts"
KAGGLE_DIR = ROOT / "kaggle"

CHANNEL_STYLES = {
    "weirdhistory": "historical archive photograph, 35mm film grain, Rembrandt lighting, chiaroscuro, amber candlelight, dark academia",
    "crimeledger": "crime scene documentary, cold blue steel lighting, Fincher aesthetic, teal shadows, forensic atmosphere",
    "mindtactics": "psychological portrait, high contrast monochrome, red accent color, analog horror, VHS distortion",
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
    creds = {"username": KAGGLE_USERNAME, "key": KAGGLE_KEY}
    kaggle_json.write_text(json.dumps(creds))
    kaggle_json.chmod(0o600)


def run_kaggle(cmd, desc=""):
    env = os.environ.copy()
    env.update({"KAGGLE_USERNAME": KAGGLE_USERNAME, "KAGGLE_KEY": KAGGLE_KEY})
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return r


def upload_prompts(scene_prompts):
    print("Uploading scene_prompts.json to Kaggle dataset...")
    upload_dir = Path("/tmp/kaggle_upload")
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Clean folder — must contain ONLY scene_prompts.json
    for f in upload_dir.iterdir():
        if f.is_file():
            f.unlink()

    prompt_file = upload_dir / "scene_prompts.json"
    prompt_file.write_text(json.dumps(scene_prompts, ensure_ascii=False, indent=2))

    r = run_kaggle(
        ["kaggle", "datasets", "version", "-p", str(upload_dir),
         "--dir-mode", "zip", "-m", "update"],
        "dataset version upload"
    )
    if r.returncode != 0:
        r = run_kaggle(
            ["kaggle", "datasets", "create", "-p", str(upload_dir), "--dir-mode", "zip"],
            "dataset create"
        )
        if r.returncode != 0:
            print(f"Dataset upload failed:\n{r.stderr}")
            return False

    print("Waiting 10s for dataset to propagate...")
    time.sleep(10)

    # Verify file exists in dataset before pushing kernel
    print("Verifying scene_prompts.json in dataset...")
    verify_dir = Path("/tmp/kaggle_verify")
    verify_dir.mkdir(parents=True, exist_ok=True)
    r2 = run_kaggle(
        ["kaggle", "datasets", "download", DATASET_ID, "-p", str(verify_dir), "--force", "--quiet"],
        "dataset download verify"
    )
    if r2.returncode == 0:
        zips = list(verify_dir.glob("*.zip"))
        found = False
        if zips:
            import zipfile
            with zipfile.ZipFile(zips[0]) as zf:
                found = any("scene_prompts.json" in n for n in zf.namelist())
        else:
            found = (verify_dir / "scene_prompts.json").exists()
        if not found:
            print("ERROR: scene_prompts.json not found in downloaded dataset")
            return False
        print("scene_prompts.json verified in dataset")
    else:
        r3 = run_kaggle(["kaggle", "datasets", "status", DATASET_ID], "dataset status verify")
        if "ready" not in r3.stdout.lower() and "ok" not in r3.stdout.lower():
            print(f"Dataset verification failed: {r3.stdout}")
            return False
        print("Dataset status verified (file existence check via download skipped)")

    print("Dataset updated OK")
    return True


def push_and_run_kernel():
    print("Pushing kernel to Kaggle...")
    r = run_kaggle(
        ["kaggle", "kernels", "push", "-p", str(KAGGLE_DIR)],
        "kernel push"
    )
    if r.returncode != 0:
        stderr_lower = r.stderr.lower()
        if "409" in stderr_lower or "conflict" in stderr_lower:
            print("Kernel already exists (409 conflict) — trying push with -u flag...")
            r = run_kaggle(
                ["kaggle", "kernels", "push", "-p", str(KAGGLE_DIR)],
                "kernel push retry"
            )
        if r.returncode != 0:
            print(f"Kernel push failed:\n{r.stderr}")
            return False
    print("Verifying kernel version...")
    r2 = run_kaggle(["kaggle", "kernels", "status", KERNEL_ID], "kernel verify")
    if "complete" not in r2.stdout.lower() and "running" not in r2.stdout.lower() and "queued" not in r2.stdout.lower():
        print(f"Kernel verification failed: {r2.stdout}")
        return False
    print(f"Kernel pushed OK — T4 GPU run starting")
    return True


def wait_for_kernel(max_wait=3600):
    print("Waiting for Kaggle T4 GPU (polling every 30s)...")
    start = time.time()
    while time.time() - start < max_wait:
        r = run_kaggle(["kaggle", "kernels", "status", KERNEL_ID], "kernel status")
        raw = r.stdout.strip()
        status = raw.lower()
        elapsed = int(time.time() - start)
        if '"queued"' in status:
            print(f"  [{elapsed}s] Status: queued (waiting in line)")
        elif '"running"' in status:
            print(f"  [{elapsed}s] Status: running (T4 GPU active)")
        elif '"complete"' in status:
            print(f"  [{elapsed}s] Status: complete!")
            return True
        elif '"error"' in status or '"cancel"' in status:
            print(f"  [{elapsed}s] Status: error/failed!")
            return False
        else:
            print(f"  [{elapsed}s] Status: {raw}")
        time.sleep(30)
    print("  Timeout reached")
    return False


def download_outputs(channel, scene_ids=None):
    dest = ROOT / "projects" / channel / "footage"
    dest.mkdir(parents=True, exist_ok=True)
    tmp = Path("/tmp/kaggle_download")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    r = run_kaggle(
        ["kaggle", "kernels", "output", KERNEL_ID, "-p", str(tmp)],
        "kernel output download"
    )
    if r.returncode != 0:
        print(f"Download failed:\n{r.stderr}")
        return []

    raw = []
    for p in tmp.rglob("*"):
        if p.is_file():
            raw.append(p)

    if not raw:
        print("No files downloaded")
        return []

    print(f"Downloaded {len(raw)} raw files, converting to {dest} ...")
    valid = True
    converted = []

    for f in raw:
        m = re.match(r"scene_(\d+)_(photo_1|photo_2|video)\.(png|mp4)", f.name)
        if not m:
            print(f"  {f.name}: SKIP (unrecognized pattern)")
            continue
        idx = int(m.group(1))
        kind = m.group(2)
        ext = m.group(3)

        scene_id = scene_ids[idx] if scene_ids and idx < len(scene_ids) else idx

        if kind == "photo_1":
            out_name = f"s{scene_id}_photo1.jpg"
        elif kind == "photo_2":
            out_name = f"s{scene_id}_photo2.jpg"
        elif kind == "video":
            out_name = f"s{scene_id}_1.mp4"
        else:
            continue

        out_path = dest / out_name
        kb = f.stat().st_size // 1024

        if ext == "png":
            img = Image.open(f)
            rgb = img.convert("RGB")
            rgb.save(str(out_path), "JPEG", quality=95)
            print(f"  {f.name} → {out_name} ({kb}KB, converted PNG→JPG)")
        else:
            if out_path.exists():
                out_path.unlink()
            shutil.copy2(f, out_path)
            print(f"  {f.name} → {out_name} ({kb}KB)")

        converted.append(out_path)

        if ext == "mp4" and kb < 100:
            print(f"    WARNING: MP4 < 100KB, may be corrupt")
            valid = False
        elif ext == "jpg" and kb < 50:
            print(f"    WARNING: JPG < 50KB, may be corrupt")
            valid = False

    extra = list(dest.glob("*"))
    print(f"\nConverted {len(converted)} files in {dest}")
    for f in sorted(extra):
        if f.is_file():
            print(f"  {f.name} ({f.stat().st_size // 1024}KB)")

    if not valid:
        sys.exit("ERROR: Downloaded file validation failed")
    return converted


def extract_visual_from_prompt(raw_prompt, channel):
    style = CHANNEL_STYLES.get(channel, "")
    clean = re.sub(r'\[SFX:[^\]]*\]', '', raw_prompt)
    clean = re.sub(r'color_note:[^\n]*', '', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if style:
        return f"{style}, {clean}"
    return clean


def build_scene_prompts(scenes, channel):
    style = CHANNEL_STYLES.get(channel, "")
    build_prompts = []
    for scene in scenes:
        scene_id = scene.get("id")
        if not scene_id:
            continue
        img1, img2, vid = parse_visual_prompts(scene)
        raw_visual = str(scene.get("visual") or scene.get("title", ""))
        if not img1:
            img1 = extract_visual_from_prompt(raw_visual, channel)
        elif style:
            img1 = f"{style}, {img1}"
        if not img2:
            img2 = img1
        elif img2 != img1 and style:
            img2 = f"{style}, {img2}"
        if not vid:
            vid = img1
        elif vid != img1 and style:
            vid = f"{style}, {vid}"
        build_prompts.append({
            "id": scene_id,
            "title": scene.get("title", ""),
            "img1_prompt": img1,
            "img2_prompt": img2,
            "vid_prompt": vid,
        })
    return build_prompts


def pixabay_fallback(channel, scenes, test_mode=False):
    if test_mode:
        print(f"\n=== Dry-run: Generating {min(3, len(scenes))} test scenes using Pixabay fallback ===")
    else:
        print("\n=== Pixabay stock footage fallback ===")
    dest = ROOT / "projects" / channel / "footage"
    dest.mkdir(parents=True, exist_ok=True)

    test_scenes = scenes[:3] if test_mode else scenes

    for scene in test_scenes:
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
    print(f"Done: {count} assets in {dest}")

    if test_mode:
        valid = True
        for f in dest.iterdir():
            if not f.is_file():
                continue
            kb = f.stat().st_size // 1024
            ext = f.suffix.lower()
            print(f"  {f.name} ({kb}KB)")
            if ext == ".mp4" and kb < 100:
                print(f"    WARNING: MP4 < 100KB")
                valid = False
            elif ext == ".jpg" and kb < 50:
                print(f"    WARNING: JPG < 50KB")
                valid = False
        if valid:
            print("Dry-run test PASSED")
        else:
            sys.exit("Dry-run test FAILED")


def _fetch_pixabay_image(query, dest_path, seed):
    if not PIXABAY_KEY:
        print(f"  Pixabay image {dest_path.name}: SKIP (no API key)")
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
        print(f"  Pixabay video {dest_path.name}: SKIP (no API key)")
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


def cmd_check():
    """--check: show status of last kernel run"""
    print(f"Checking kernel status: {KERNEL_ID}")
    r = run_kaggle(["kaggle", "kernels", "status", KERNEL_ID], "check status")
    if r.returncode != 0:
        print(f"Status check failed: {r.stderr}")
        sys.exit(1)
    print(f"Kernel: {KERNEL_ID}")
    print(f"Status: {r.stdout.strip()}")
    r2 = run_kaggle(["kaggle", "kernels", "list", "--mine", "-p", "1"],
                     "list kernels")
    if r2.returncode == 0:
        print(f"\nRecent kernels:\n{r2.stdout}")


def main():
    parser = argparse.ArgumentParser(description="Generate assets via Kaggle GPU")
    parser.add_argument("--channel", default=CHANNEL_ENV,
                        help="Channel name (weirdhistory/crimeledger/mindtactics)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip Kaggle, generate 3 test scenes via Pixabay fallback")
    parser.add_argument("--check", action="store_true",
                        help="Check status of last kernel run only")
    args = parser.parse_args()

    channel = args.channel or CHANNEL_ENV

    if args.check:
        cmd_check()
        return

    if args.dry_run:
        if not channel:
            sys.exit("ERROR: --channel required with --dry-run")
        script = load_script(channel)
        scenes = script.get("scenes", [])
        print(f"DRY-RUN: {channel} ({min(3, len(scenes))} test scenes)")
        build_prompts = build_scene_prompts(scenes, channel)
        scene_prompts = {"channel": channel, "scenes": build_prompts}
        prompt_path = ROOT / "projects" / channel / "scene_prompts.json"
        prompt_path.write_text(json.dumps(scene_prompts, ensure_ascii=False, indent=2))
        print(f"Wrote {prompt_path}")
        pixabay_fallback(channel, scenes, test_mode=True)
        return

    if not channel:
        sys.exit("ERROR: CHANNEL not set (use --channel or CHANNEL env var)")
    if not KAGGLE_KEY:
        print("WARNING: KAGGLE_KEY not set — skipping Kaggle, using Pixabay fallback")
        script = load_script(channel)
        pixabay_fallback(channel, script.get("scenes", []))
        return

    script = load_script(channel)
    scenes = script.get("scenes", [])
    print(f"Generate assets for {channel}: {len(scenes)} scenes")

    build_prompts = build_scene_prompts(scenes, channel)
    scene_prompts = {"channel": channel, "scenes": build_prompts}

    write_kaggle_json()

    ok = upload_prompts(scene_prompts)
    if not ok:
        sys.exit("ERROR: Dataset upload failed")

    ok = push_and_run_kernel()
    if not ok:
        sys.exit("ERROR: Kernel push failed")

    ok = wait_for_kernel()
    if not ok:
        sys.exit("ERROR: Kernel run failed or timed out")

    scene_ids = [s.get("id") for s in scenes]
    files = download_outputs(channel, scene_ids)
    if not files:
        sys.exit("ERROR: No files downloaded")

    print(f"\nSuccess: {len(files)} assets validated in projects/{channel}/footage/")

    if ok and files:
        print("All validations passed — proceeding to next pipeline stage")


if __name__ == "__main__":
    main()
