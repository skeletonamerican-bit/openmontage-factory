import json
import os
import time
from pathlib import Path

import requests

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
CHANNEL = os.getenv("CHANNEL")
RATE_LIMIT_SECONDS = 0.3


def download_file(url, dest_path):
    if dest_path.exists():
        print(f"Skipping existing file: {dest_path}")
        return True

    for attempt in range(1, 4):
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as exc:
            print(f"Attempt {attempt} failed for {url}: {exc}")
            time.sleep(2)
    return False


def search_pexels(query):
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": query, "per_page": 3, "orientation": "landscape"}
    response = requests.get("https://api.pexels.com/videos/search", headers=headers, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    urls = []
    for video in data.get("videos", []):
        files = [item for item in video.get("video_files", []) if item.get("file_type") == "video/mp4"]
        if files:
            files.sort(key=lambda item: item.get("width", 0), reverse=True)
            urls.append(files[0]["link"])
    return urls


def search_pixabay(query):
    params = {"key": PIXABAY_API_KEY, "q": query, "per_page": 3, "orientation": "horizontal"}
    response = requests.get("https://pixabay.com/api/videos/", params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    urls = []
    for hit in data.get("hits", []):
        videos = hit.get("videos", {})
        for quality in ("large", "medium", "small"):
            if quality in videos:
                urls.append(videos[quality]["url"])
                break
    return urls


def fetch_urls(query):
    if not PEXELS_API_KEY:
        raise EnvironmentError("PEXELS_API_KEY is required")
    try:
        urls = search_pexels(query)
        if urls:
            return urls
    except Exception as exc:
        print(f"Pexels lookup failed for '{query}': {exc}")

    if PIXABAY_API_KEY:
        try:
            urls = search_pixabay(query)
            if urls:
                return urls
        except Exception as exc:
            print(f"Pixabay lookup failed for '{query}': {exc}")
    return []


def main():
    if not all([PEXELS_API_KEY, CHANNEL]):
        raise SystemExit("Missing PEXELS_API_KEY or CHANNEL environment variables")

    script_path = Path(f"projects/{CHANNEL}/script.json")
    if not script_path.exists():
        raise SystemExit(f"Script file not found: {script_path}")

    with open(script_path, "r") as f:
        script = json.load(f)

    footage_dir = Path(f"projects/{CHANNEL}/footage")
    footage_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching assets for {len(script['scenes'])} scenes...")

    for scene in script["scenes"]:
        scene_id = scene["id"]
        print(f"Processing scene {scene_id}")
        scene_clip = 1
        for query in scene.get("pexels_queries", [])[:5]:
            if not query:
                continue

            urls = fetch_urls(query)
            if not urls:
                print(f"No clip URLs found for query '{query}'")
                time.sleep(RATE_LIMIT_SECONDS)
                continue

            for clip_url in urls[:2]:
                dest_path = footage_dir / f"{scene_id}_{scene_clip:02d}.mp4"
                if download_file(clip_url, dest_path):
                    print(f"Downloaded {dest_path}")
                else:
                    print(f"Failed to download clip for scene {scene_id} from {clip_url}")
                scene_clip += 1
                time.sleep(RATE_LIMIT_SECONDS)

    print("Fetch complete.")


if __name__ == "__main__":
    main()
