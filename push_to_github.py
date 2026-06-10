import base64, json, os, sys, time
from pathlib import Path
import urllib.request, urllib.error

TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = "skeletonamerican-bit/openmontage-factory"
BASE = f"https://api.github.com/repos/{REPO}/contents"

FILES = {
    "assemble_v2.py":                    "assemble_v2.py",
    "scripts/select_topic.py":           "scripts/select_topic.py",
    "scripts/generate_script.py":        "scripts/generate_script.py",
    "scripts/generate_assets.py":        "scripts/generate_assets.py",
    "scripts/generate_tts.py":           "scripts/generate_tts.py",
    "scripts/assemble_video.py":         "scripts/assemble_video.py",
    "scripts/notify_telegram.py":        "scripts/notify_telegram.py",
    "scripts/run_kaggle_video.py":       "scripts/run_kaggle_video.py",
    "topics.json":                       "topics.json",
    "topic_state.json":                  "topic_state.json",
    "config.yaml":                       "config.yaml",
    "requirements.txt":                  "requirements.txt",
    "run_factory.sh":                    "run_factory.sh",
    ".github/workflows/make_video.yml":  ".github/workflows/make_video.yml",
    ".github/workflows/daily_factory.yml": ".github/workflows/daily_factory.yml",
}

def api(path, data):
    url = f"{BASE}/{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="PUT")
    req.add_header("Authorization", f"token {TOKEN}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/vnd.github.v3+json")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, e.read().decode()

def get_sha(path):
    url = f"{BASE}/{path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"token {TOKEN}")
    req.add_header("Accept", "application/vnd.github.v3+json")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read()).get("sha")
    except:
        return None

def upload(repo_path, local_path):
    lp = Path(local_path)
    if not lp.exists():
        print(f"  SKIP (no local file): {local_path}")
        return False
    content = base64.b64encode(lp.read_bytes()).decode()
    sha = get_sha(repo_path)
    data = {"message": f"feat: update {repo_path}", "content": content}
    if sha:
        data["sha"] = sha
    resp, err = api(repo_path, data)
    if err:
        print(f"  FAIL {repo_path}: {err[:120]}")
        return False
    print(f"  OK  {repo_path}")
    return True

def main():
    print("=" * 50)
    print("  OpenMontage Factory — Push to GitHub")
    print("=" * 50)
    if not TOKEN:
        print("ERROR: GITHUB_TOKEN not set")
        sys.exit(1)
    ok = fail = 0
    for repo_path, local_path in FILES.items():
        if upload(repo_path, local_path):
            ok += 1
        else:
            fail += 1
        time.sleep(0.3)
    print(f"\nOK: {ok} | FAIL: {fail}")
    print(f"https://github.com/{REPO}/actions")

if __name__ == "__main__":
    main()
