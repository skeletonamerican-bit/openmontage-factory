import json, os, re, subprocess, sys, time, requests, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANNEL = os.getenv("CHANNEL")

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

def generate_ai_image(prompt, dest_path):
    if dest_path.exists():
        return True
    encoded = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1920&height=1080&nologo=true"
    print(f"    Pollinations: {prompt[:60]}...")
    return download_file(url, dest_path)

def create_placeholder_clip(dest_path, scene_id, text):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=black:s=1280x720:d=4",
        "-vf", f"drawtext=text='{text[:80]}':fontcolor=white:fontsize=28:x=(w-text_w)/2:y=(h-text_h)/2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
        str(dest_path)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except Exception as e:
        print(f"    Placeholder failed: {e}")
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
    print(f"Generating AI assets for {CHANNEL}: {len(scenes)} scenes")

    for i, scene in enumerate(scenes):
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

        print(f"  [{i+1}/{len(scenes)}] Scene {scene_id}")

        photo1 = footage_dir / f"s{scene_id}_photo1.jpg"
        photo2 = footage_dir / f"s{scene_id}_photo2.jpg"
        video = footage_dir / f"s{scene_id}_1.mp4"

        if not photo1.exists():
            print(f"    Generating photo 1...")
            if generate_ai_image(img1_prompt, photo1):
                kb = photo1.stat().st_size // 1024
                print(f"    Photo1 OK ({kb}KB)")
            else:
                print(f"    Photo1 FAILED")
        else:
            print(f"    Photo1 exists (skip)")

        if not photo2.exists():
            print(f"    Generating photo 2...")
            if generate_ai_image(img2_prompt, photo2):
                kb = photo2.stat().st_size // 1024
                print(f"    Photo2 OK ({kb}KB)")
            else:
                print(f"    Photo2 FAILED")
        else:
            print(f"    Photo2 exists (skip)")

        if not video.exists():
            print(f"    Creating placeholder video...")
            create_placeholder_clip(video, scene_id, f"{CHANNEL}: {vid_prompt[:60]}")
            print(f"    Placeholder video created")
        else:
            print(f"    Video exists (skip)")

    print("Asset generation complete.")

if __name__ == "__main__":
    main()
