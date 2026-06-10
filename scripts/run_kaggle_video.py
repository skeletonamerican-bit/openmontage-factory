"""
run_kaggle_video.py — запускает LTX-Video на Kaggle T4
1. Читает script.json → создаёт scene_prompts.json
2. Загружает на Kaggle как dataset
3. Запускает ноутбук ltx-video-runner
4. Ждёт завершения (polling)
5. Скачивает footage/*.mp4
"""
import json, os, sys, time, subprocess, urllib.request
from pathlib import Path

KAGGLE_USER = os.environ.get("KAGGLE_USERNAME", "forts845")
KAGGLE_KEY  = os.environ.get("KAGGLE_KEY", "")
CHANNEL     = os.environ.get("CHANNEL", "weirdhistory")
KERNEL_ID   = f"{KAGGLE_USER}/ltx-video-runner"

def kaggle_api(endpoint, method="GET", data=None):
    url = f"https://www.kaggle.com/api/v1/{endpoint}"
    import base64
    creds = base64.b64encode(f"{KAGGLE_USER}:{KAGGLE_KEY}".encode()).decode()
    req = urllib.request.Request(url, data=data)
    req.add_header("Authorization", f"Basic {creds}")
    req.add_header("Content-Type", "application/json")
    if method == "POST":
        req.method = "POST"
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def push_kernel():
    """Пушим ноутбук через kaggle CLI."""
    env = os.environ.copy()
    env["KAGGLE_USERNAME"] = KAGGLE_USER
    env["KAGGLE_KEY"] = KAGGLE_KEY
    result = subprocess.run(
        ["kaggle", "kernels", "push", "-p", "kaggle/"],
        capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        print("Push error:", result.stderr)
        sys.exit(1)
    print("Kernel pushed OK")

def wait_for_kernel(max_wait=3600):
    """Ждём завершения ноутбука."""
    env = os.environ.copy()
    env["KAGGLE_USERNAME"] = KAGGLE_USER
    env["KAGGLE_KEY"] = KAGGLE_KEY
    slug = KERNEL_ID.replace("/", "-").lower()
    start = time.time()
    while time.time() - start < max_wait:
        r = subprocess.run(
            ["kaggle", "kernels", "status", KERNEL_ID],
            capture_output=True, text=True, env=env
        )
        status = r.stdout.strip()
        print(f"  Status: {status}")
        if "complete" in status.lower():
            return True
        if "error" in status.lower() or "cancel" in status.lower():
            print("Kernel failed!")
            return False
        time.sleep(30)
    return False

def download_output():
    """Скачиваем output файлы."""
    env = os.environ.copy()
    env["KAGGLE_USERNAME"] = KAGGLE_USER
    env["KAGGLE_KEY"] = KAGGLE_KEY
    out_dir = Path(f"projects/{CHANNEL}/footage")
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["kaggle", "kernels", "output", KERNEL_ID, "-p", str(out_dir)],
        env=env, check=True
    )
    mp4s = list(out_dir.glob("*.mp4"))
    print(f"Downloaded {len(mp4s)} MP4 files")
    return mp4s

def main():
    if not KAGGLE_KEY:
        print("ERROR: KAGGLE_KEY not set"); sys.exit(1)

    script_file = Path(f"projects/{CHANNEL}/script.json")
    if not script_file.exists():
        print(f"ERROR: {script_file} not found"); sys.exit(1)

    with open(script_file) as f:
        data = json.load(f)
    scenes = data.get("scenes", [])

    # Сохраняем промпты для Kaggle
    prompts = {"channel": CHANNEL, "scenes": scenes}
    Path("kaggle/scene_prompts.json").write_text(
        json.dumps(prompts, ensure_ascii=False, indent=2)
    )
    print(f"Prepared {len(scenes)} scene prompts")

    # Запускаем на Kaggle
    push_kernel()
    print("Waiting for Kaggle T4 GPU (can take 10-20 min)...")
    ok = wait_for_kernel()

    if ok:
        mp4s = download_output()
        print(f"OK: {len(mp4s)} video clips ready")
    else:
        print("Kaggle failed — using Pixabay stock footage as fallback")
        sys.exit(0)  # не падаем, fallback на сток

if __name__ == "__main__":
    main()
