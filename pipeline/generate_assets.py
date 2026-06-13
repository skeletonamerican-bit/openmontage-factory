import os, json, time, glob, shutil, requests
from kaggle.api.kaggle_api_extended import KaggleApi


def generate_assets(channel: str, script: list) -> dict:
    api = KaggleApi()
    api.authenticate()

    KERNEL = "forts845/openmontage-sana-ltx-runner"
    KAGGLE_DIR = "kaggle"
    OUTPUT_DIR = f"output/{channel}/assets"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    scenes_data = []
    for i, scene in enumerate(script):
        scenes_data.append({
            "idx": i,
            "photo_prompt_1": scene.get("photo_prompt_1", ""),
            "photo_prompt_2": scene.get("photo_prompt_2", ""),
            "video_prompt": scene.get("video_prompt", ""),
            "generate_video": (i % 3 == 0),
        })

    prompts_path = os.path.join(KAGGLE_DIR, "prompts.json")
    with open(prompts_path, "w") as f:
        json.dump({"channel": channel, "scenes": scenes_data}, f)

    print(f"[{channel}] Kaggle push...")
    os.system(
        f"kaggle kernels push --accelerator NvidiaTeslaT4 "
        f"-p {KAGGLE_DIR} 2>&1"
    )

    print(f"[{channel}] Waiting for kernel...")
    for attempt in range(270):
        time.sleep(20)
        try:
            st = api.kernels_status(KERNEL)
            status = st["status"] if isinstance(st, dict) else str(st)
            print(f"[{channel}] Kaggle [{attempt*20}s]: {status}")
            if status == "complete":
                break
            if status == "error":
                print(f"[{channel}] Kaggle ERROR -- Pixabay fallback")
                return _pixabay_fallback(channel, script, OUTPUT_DIR)
        except Exception as e:
            print(f"[{channel}] Poll error: {e}")
            continue

    print(f"[{channel}] Downloading output...")
    tmp_dir = f"/tmp/kaggle_{channel}"
    os.makedirs(tmp_dir, exist_ok=True)

    for attempt in range(3):
        try:
            api.kernels_output(KERNEL, path=tmp_dir)
            break
        except Exception as e:
            print(f"Download attempt {attempt+1} failed: {e}")
            time.sleep(10)

    photos, videos = [], []
    for f in glob.glob(f"{tmp_dir}/**/*", recursive=True):
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

    print(f"[{channel}] Assets: {len(photos)} photos, {len(videos)} videos")

    if len(photos) == 0:
        print(f"[{channel}] No photos -- Pixabay fallback")
        return _pixabay_fallback(channel, script, OUTPUT_DIR)

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

    print(f"Pixabay fallback: {len(photos)} photos")
    return {"photos": photos, "videos": videos, "dir": output_dir}
