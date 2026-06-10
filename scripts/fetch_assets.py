import json, os, re, subprocess, sys, time, requests
from pathlib import Path
from urllib import parse, request, error

ROOT = Path(__file__).resolve().parent.parent
CHANNEL = os.getenv("CHANNEL")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

STOCK_SEARCH_TERMS = {
    "weirdhistory": [
        "historical archive antique",
        "vintage photograph 19th century",
        "medieval castle dark",
        "ancient ruins gothic",
        "old manuscript parchment",
        "Victorian era portrait",
        "Renaissance painting dark",
        "world war documentary",
        "archaeological excavation",
        "ancient artifact museum",
    ],
    "crimeledger": [
        "rain police lights night",
        "handcuffs slow motion",
        "dark corridor interrogation",
        "night highway rain",
        "police evidence crime scene",
        "anonymous city street night",
        "surveillance camera feed",
        "detective office dark",
        "courtroom dramatic",
        "prison cell corridor",
    ],
    "mindtactics": [
        "chess pieces strategic",
        "broken mirror reflection",
        "silhouette fog mist",
        "ink water abstract",
        "labyrinth maze dark",
        "pendulum swinging",
        "hypnotic spiral pattern",
        "psychiatric evaluation room",
        "brain neurology abstract",
        "pupil dilation eye closeup",
    ],
}

AI_IMAGE_PROMPTS = {
    "weirdhistory": "historical archive photo, 35mm film grain, Rembrandt lighting, chiaroscuro, moody shadows, dark academia aesthetic",
    "crimeledger": "crime scene documentary still, cold steel grey, dark green tint, fluorescent lighting, forensic photography",
    "mindtactics": "dark psychological portrait, high contrast, one color accent, psychiatric file aesthetic, clinical lighting",
}

def load_script(channel):
    p = ROOT / "projects" / channel / "script.json"
    if not p.exists():
        sys.exit(f"ERROR: {p}")
    return json.loads(p.read_text(encoding="utf-8"))

def download_file(url, dest_path):
    if dest_path.exists():
        return True
    for attempt in range(1, 4):
        try:
            r = requests.get(url, stream=True, timeout=60)
            r.raise_for_status()
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return True
        except Exception as e:
            print(f"  Attempt {attempt} failed: {e}")
            time.sleep(2)
    return False

def search_pixabay_video(query):
    if not PIXABAY_API_KEY:
        return None
    params = parse.urlencode({
        "key": PIXABAY_API_KEY, "q": query,
        "per_page": 50, "orientation": "horizontal",
        "safesearch": "true", "min_width": 1280
    })
    url = f"https://pixabay.com/api/videos/?{params}"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        hits = data.get("hits", [])
        if not hits:
            return None
        for hit in hits:
            videos = hit.get("videos", {})
            for quality in ("large", "medium", "small"):
                if quality in videos:
                    return videos[quality].get("url")
    except Exception as e:
        print(f"  Pixabay error: {e}")
    return None

def search_pexels_video(query):
    if not PEXELS_API_KEY:
        return None
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={parse.quote(query)}&per_page=5&orientation=landscape&size=large"
    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        videos = data.get("videos", [])
        if not videos:
            return None
        for video in videos:
            files = video.get("video_files", [])
            hd = next((f for f in files if f.get("quality") in ("hd", "uhd")), files[0] if files else None)
            if hd:
                return hd["link"]
    except Exception as e:
        print(f"  Pexels error: {e}")
    return None

def create_placeholder_clip(dest_path, scene_id, text):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=black:s=1280x720:d=10",
        "-vf", f"drawtext=text='{text[:80]}':fontcolor=white:fontsize=28:x=(w-text_w)/2:y=(h-text_h)/2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
        str(dest_path)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except Exception as e:
        print(f"  Placeholder failed: {e}")
        return False

def get_visual_text(scene):
    raw = str(scene.get("visual") or scene.get("title") or "")
    clean = re.sub(r'\[.*?\]', '', raw)
    words = [w for w in clean.split() if len(w) > 3]
    return ' '.join(words[:4]) if words else 'documentary footage'

def main():
    if not CHANNEL:
        sys.exit("ERROR: CHANNEL not set")
    script = load_script(CHANNEL)
    footage_dir = ROOT / "projects" / CHANNEL / "footage"
    footage_dir.mkdir(parents=True, exist_ok=True)
    scenes = script.get("scenes", [])
    search_terms = STOCK_SEARCH_TERMS.get(CHANNEL, ["documentary footage"])
    print(f"Fetching assets for {CHANNEL}: {len(scenes)} scenes")

    for i, scene in enumerate(scenes):
        scene_id = scene.get("id")
        if not scene_id:
            continue
        dest = footage_dir / f"{scene_id}_1.mp4"
        if dest.exists():
            print(f"  SKIP {scene_id} (exists)")
            continue
        query = get_visual_text(scene)
        print(f"  [{i+1}/{len(scenes)}] {scene_id}: searching \"{query}\"")
        video_url = search_pexels_video(query)
        if not video_url:
            video_url = search_pixabay_video(query)
        if video_url:
            print(f"    Downloading...")
            if download_file(video_url, dest):
                kb = dest.stat().st_size // 1024
                print(f"    OK ({kb}KB)")
                time.sleep(0.3)
                continue
        print(f"    Creating placeholder")
        create_placeholder_clip(dest, scene_id, f"{CHANNEL}: {query}")
    print("Fetch complete.")

if __name__ == "__main__":
    main()
