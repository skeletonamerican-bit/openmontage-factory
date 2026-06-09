import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parent.parent
CHANNEL = os.getenv("CHANNEL")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
RATE_LIMIT_SECONDS = 0.3


def load_script(channel):
    script_path = ROOT / "projects" / channel / "script.json"
    if not script_path.exists():
        sys.exit(f"ERROR: Script file not found: {script_path}")
    return json.loads(script_path.read_text(encoding="utf-8"))


def download_file(url, dest_path):
    if dest_path.exists():
        print(f"Skipping existing file: {dest_path}")
        return True

    for attempt in range(1, 4):
        try:
            req = request.Request(url, headers={"User-Agent": "python-fetch-assets/1.0"})
            with request.urlopen(req, timeout=60) as response:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with open(dest_path, "wb") as out_file:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        out_file.write(chunk)
            return True
        except error.HTTPError as exc:
            print(f"Attempt {attempt} failed for {url}: {exc.code} {exc.reason}")
        except Exception as exc:
            print(f"Attempt {attempt} failed for {url}: {exc}")
        time.sleep(2)
    return False


def pixabay_video_url(query):
    if not PIXABAY_API_KEY:
        return None
    params = parse.urlencode({"key": PIXABAY_API_KEY, "q": query, "per_page": 3, "orientation": "horizontal"})
    url = f"https://pixabay.com/api/videos/?{params}"
    req = request.Request(url, method="GET")
    with request.urlopen(req, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    hits = payload.get("hits", [])
    if not hits:
        return None
    for hit in hits:
        videos = hit.get("videos", {})
        for quality in ("large", "medium", "small"):
            if quality in videos:
                return videos[quality].get("url")
    return None


def create_placeholder_clip(dest_path, scene_id, query):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    duration = 12
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s=1280x720:d={duration}",
        "-vf",
        "drawtext=text='Placeholder clip':fontcolor=white:fontsize=36:x=(w-text_w)/2:y=(h-text_h)/2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(dest_path),
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as exc:
        print(f"WARNING: could not create placeholder clip: {exc}")
        return False


def main():
    if not CHANNEL:
        sys.exit("ERROR: Missing CHANNEL environment variable")

    script = load_script(CHANNEL)
    footage_dir = ROOT / "projects" / CHANNEL / "footage"
    footage_dir.mkdir(parents=True, exist_ok=True)

    scenes = script.get("scenes", [])
    print(f"Fetching assets for {len(scenes)} scenes...")

    for scene in scenes:
        scene_id = scene.get("id")
        visual = scene.get("visual") or scene.get("title") or "stock footage"
        if not scene_id:
            print("WARNING: skipping scene with missing id")
            continue

        destination = footage_dir / f"{scene_id}_1.mp4"
        if destination.exists():
            print(f"Skipping existing footage for scene {scene_id}")
            continue

        query = str(visual).strip()
        video_url = None
        if PIXABAY_API_KEY:
            print(f"Searching Pixabay for scene {scene_id}: {query}")
            for attempt in range(1, 4):
                try:
                    video_url = pixabay_video_url(query)
                    if video_url:
                        break
                except error.HTTPError as exc:
                    print(f"Pixabay API error (attempt {attempt}): {exc.code} {exc.reason}")
                except Exception as exc:
                    print(f"Pixabay request failed (attempt {attempt}): {exc}")
                time.sleep(2)

        if video_url:
            print(f"Downloading scene {scene_id} from {video_url}")
            if download_file(video_url, destination):
                time.sleep(RATE_LIMIT_SECONDS)
                continue
            print(f"WARNING: failed to download video for scene {scene_id}, using placeholder")

        print(f"Creating placeholder clip for scene {scene_id}")
        if not create_placeholder_clip(destination, scene_id, query):
            sys.exit(f"ERROR: could not create fallback clip for scene {scene_id}")

    print("Fetch complete.")


if __name__ == "__main__":
    main()
