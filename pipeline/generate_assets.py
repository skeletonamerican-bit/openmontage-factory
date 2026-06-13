import os, json, time, glob, shutil, requests, tempfile
from datetime import datetime
from kaggle.api.kaggle_api_extended import KaggleApi


def generate_assets(channel: str, script: list) -> dict:
    if os.environ.get("USE_PIXABAY_ONLY") or os.environ.get("SKIP_KAGGLE"):
        print(f"[{channel}] SKIP_KAGGLE/USE_PIXABAY_ONLY set — skipping Kaggle, going to Pixabay fallback", flush=True)
        OUTPUT_DIR = f"output/{channel}/assets"
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        return _pixabay_fallback(channel, script, OUTPUT_DIR)

    api = KaggleApi()
    api.authenticate()

    KERNEL = "forts845/openmontage-sana-ltx-runner"
    DATASET = "forts845/openmontage-prompts"
    KAGGLE_DIR = "kaggle"
    OUTPUT_DIR = f"output/{channel}/assets"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    scenes_for_kaggle = [
        {
            "id": s.get("scene", i),
            "title": s.get("narration", "")[:100],
            "photo_prompt_1": s.get("photo_prompt_1") or s.get("image_prompt", "generic scene"),
            "photo_prompt_2": s.get("photo_prompt_2") or s.get("photo_prompt_1", "generic scene"),
            "photo_prompt_3": s.get("photo_prompt_3") or s.get("photo_prompt_1", "generic scene"),
            "video_prompt": s.get("video_prompt", ""),
        }
        for i, s in enumerate(script)
    ]

    payload = {
        "channel": channel,
        "scenes": scenes_for_kaggle,
        "generated_at": datetime.utcnow().isoformat(),
    }

    # Step 1: Upload prompts to Kaggle dataset
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    tmp_dir = f"/tmp/kaggle_prompts_{channel}_{timestamp}"
    os.makedirs(tmp_dir, exist_ok=True)
    prompts_file = os.path.join(tmp_dir, "scene_prompts.json")
    with open(prompts_file, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"[{channel}] Uploading prompts to Kaggle dataset {DATASET}...", flush=True)
    for attempt in range(3):
        try:
            api.dataset_create_version(
                tmp_dir,
                f"update_{channel}_{timestamp}"
            )
            print(f"[{channel}] Dataset upload successful", flush=True)
            break
        except Exception as e:
            print(f"[{channel}] Dataset upload attempt {attempt+1} failed: {e}", flush=True)
            if attempt < 2:
                time.sleep(5)
    else:
        print(f"[{channel}] Dataset upload failed after 3 attempts — Pixabay fallback", flush=True)
        return _pixabay_fallback(channel, script, OUTPUT_DIR)

    # Step 2: Push kernel
    print(f"[{channel}] Pushing Kaggle kernel...", flush=True)
    for attempt in range(3):
        try:
            api.kernels_push(kernel_slug=KERNEL, kernel_path=KAGGLE_DIR)
            print(f"[{channel}] Kernel push successful", flush=True)
            break
        except Exception as e:
            print(f"[{channel}] Kernel push attempt {attempt+1} failed: {e}", flush=True)
            if attempt < 2:
                time.sleep(5)
    else:
        print(f"[{channel}] Kernel push failed — Pixabay fallback", flush=True)
        return _pixabay_fallback(channel, script, OUTPUT_DIR)

    # Step 3: Poll kernel status
    print(f"[{channel}] Waiting for kernel to complete...", flush=True)
    for attempt in range(270):
        time.sleep(20)
        try:
            st = api.kernels_status(KERNEL)
            status = st["status"] if isinstance(st, dict) else str(st)
            print(f"[{channel}] Kaggle [{attempt*20}s]: {status}", flush=True)
            if status == "complete":
                break
            if status == "error":
                print(f"[{channel}] Kaggle ERROR — Pixabay fallback", flush=True)
                return _pixabay_fallback(channel, script, OUTPUT_DIR)
        except Exception as e:
            print(f"[{channel}] Poll error: {e}", flush=True)
            continue

    # Step 4: Download output
    print(f"[{channel}] Downloading kernel output...", flush=True)
    dl_dir = f"/tmp/kaggle_output_{channel}_{timestamp}"
    os.makedirs(dl_dir, exist_ok=True)

    for attempt in range(3):
        try:
            api.kernels_output(KERNEL, path=dl_dir)
            break
        except Exception as e:
            print(f"[{channel}] Download attempt {attempt+1} failed: {e}", flush=True)
            time.sleep(10)

    photos, videos = [], []
    for f in glob.glob(f"{dl_dir}/**/*", recursive=True):
        if not os.path.isfile(f):
            continue
        size = os.path.getsize(f)
        name = os.path.basename(f)
        dst = os.path.join(OUTPUT_DIR, name)
        if size > 10000:
            shutil.copy2(f, dst)
            if "_photo" in name:
                photos.append(dst)
            elif "_video" in name:
                videos.append(dst)

    print(f"[{channel}] Assets: {len(photos)} photos, {len(videos)} videos", flush=True)

    if len(photos) == 0:
        print(f"[{channel}] No photos — Pixabay fallback", flush=True)
        return _pixabay_fallback(channel, script, OUTPUT_DIR)

    # Cleanup temp dirs
    for d in [tmp_dir, dl_dir]:
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)

    return {"photos": photos, "videos": videos, "dir": OUTPUT_DIR}


def _pixabay_fallback(channel, script, output_dir):
    key = os.environ.get("PIXABAY_API_KEY", "")
    style_queries = {
        "weirdhistory": "medieval dark history",
        "crimeledger": "crime investigation noir",
        "mindtactics": "psychology shadow dark",
    }
    base_q = style_queries.get(channel, "dark cinematic")
    photos, videos = [], []

    for i, scene in enumerate(script):
        for photo_num in [1, 2]:
            query = scene.get("narration", base_q)[:25]
            url = (
                f"https://pixabay.com/api/?key={key}"
                f"&q={requests.utils.quote(query)}"
                f"&image_type=photo&per_page=3"
                f"&safesearch=true&page={photo_num}"
            )
            try:
                r = requests.get(url, timeout=10)
                hits = r.json().get("hits", [])
                if hits:
                    img_url = hits[0]["largeImageURL"]
                    img_r = requests.get(img_url, timeout=15)
                    out_path = os.path.join(
                        output_dir, f"s{i:03d}_photo{photo_num}.jpg"
                    )
                    with open(out_path, "wb") as f:
                        f.write(img_r.content)
                    if os.path.getsize(out_path) > 10000:
                        photos.append(out_path)
            except Exception as e:
                print(f"Pixabay error scene {i}: {e}")

    print(f"Pixabay fallback: {len(photos)} photos", flush=True)
    return {"photos": photos, "videos": videos, "dir": output_dir}
