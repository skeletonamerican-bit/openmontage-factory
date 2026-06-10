import json, os, re, subprocess, sys, time, requests, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANNEL = os.getenv("CHANNEL")

CHANNEL_STYLES = {
    "weirdhistory": "historical archive photograph, 35mm film grain, Rembrandt lighting, chiaroscuro, amber candlelight, dark academia",
    "crimeledger": "crime scene documentary, cold blue steel lighting, Fincher aesthetic, dark green shadows, forensic",
    "mindtactics": "psychological portrait, high contrast monochrome, red accent, analog horror, VHS distortion",
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
            r = requests.get(url, stream=True, timeout=120)
            r.raise_for_status()
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return True
        except Exception as e:
            print(f"    Attempt {attempt} failed: {e}")
            time.sleep(2)
    return False

def inject_style(raw_prompt):
    style = CHANNEL_STYLES.get(CHANNEL, "")
    if style:
        return f"{style}, {raw_prompt}"
    return raw_prompt

def generate_ai_image(prompt, dest_path, scene_id):
    if dest_path.exists():
        return True
    styled = inject_style(prompt)
    encoded = urllib.parse.quote(styled)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1920&height=1080&model=flux&nologo=true&seed={scene_id}"
    return download_file(url, dest_path)

def generate_ai_video(prompt, dest_path):
    if dest_path.exists():
        return True
    styled = inject_style(prompt)
    encoded = urllib.parse.quote(styled)

    for model in ("seedance", "wan"):
        print(f"    Pollinations video ({model})...", end=" ")
        sys.stdout.flush()
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&model={model}&duration=5"
        if download_file(url, dest_path):
            return True
        print("FAILED")

    return False

def create_ken_burns_video(photo_path, dest_path):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(photo_path),
        "-vf", "zoompan=z='min(zoom+0.0015,1.5)':d=125:s=1280x720",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
        "-t", "5",
        str(dest_path)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except Exception as e:
        print(f"    Ken Burns failed: {e}")
        return False

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

def main():
    if not CHANNEL:
        sys.exit("ERROR: CHANNEL not set")
    script = load_script(CHANNEL)
    footage_dir = ROOT / "projects" / CHANNEL / "footage"
    footage_dir.mkdir(parents=True, exist_ok=True)
    scenes = script.get("scenes", [])
    total = len(scenes) * 3
    count = 0
    print(f"Generating AI assets for {CHANNEL}: {len(scenes)} scenes ({total} assets)")

    for scene in scenes:
        scene_id = scene.get("id")
        if not scene_id:
            continue
        img1_prompt, img2_prompt, vid_prompt = parse_visual_prompts(scene)
        if not img1_prompt:
            img1_prompt = str(scene.get("title", ""))
        if not img2_prompt:
            img2_prompt = img1_prompt
        if not vid_prompt:
            vid_prompt = img1_prompt

        photo1 = footage_dir / f"s{scene_id}_photo1.jpg"
        photo2 = footage_dir / f"s{scene_id}_photo2.jpg"
        video = footage_dir / f"s{scene_id}_1.mp4"

        count += 1
        if not photo1.exists():
            print(f"  [{count}/{total}] Generating photo1...", end=" ")
            sys.stdout.flush()
            if generate_ai_image(img1_prompt, photo1, scene_id):
                kb = photo1.stat().st_size // 1024
                print(f"OK ({kb}KB)")
            else:
                print("FAILED")
        else:
            print(f"  [{count}/{total}] Photo1 exists (skip)")

        count += 1
        if not photo2.exists():
            print(f"  [{count}/{total}] Generating photo2...", end=" ")
            sys.stdout.flush()
            if generate_ai_image(img2_prompt, photo2, scene_id):
                kb = photo2.stat().st_size // 1024
                print(f"OK ({kb}KB)")
            else:
                print("FAILED")
        else:
            print(f"  [{count}/{total}] Photo2 exists (skip)")

        count += 1
        if not video.exists():
            print(f"  [{count}/{total}] Generating video...")
            if generate_ai_video(vid_prompt, video):
                kb = video.stat().st_size // 1024
                print(f"  [{count}/{total}] Video OK ({kb}KB)")
            elif photo1.exists():
                print(f"  [{count}/{total}] Creating Ken Burns from photo...", end=" ")
                sys.stdout.flush()
                if create_ken_burns_video(photo1, video):
                    kb = video.stat().st_size // 1024
                    print(f"OK ({kb}KB)")
                else:
                    print("FAILED")
            else:
                print(f"  [{count}/{total}] Video FAILED (no fallback)")
        else:
            print(f"  [{count}/{total}] Video exists (skip)")

    print("Asset generation complete.")

if __name__ == "__main__":
    main()
