"""
Загружает все файлы проекта в skeletonamerican-bit/openmontage-factory
через GitHub API (обход блокировки Codespaces push).
"""
import base64, json, os, sys, time
from pathlib import Path
import urllib.request, urllib.error

TOKEN = os.environ.get("GITHUB_TOKEN", "ghp_placeholder")
REPO  = "skeletonamerican-bit/openmontage-factory"
BASE  = f"https://api.github.com/repos/{REPO}/contents"

# Файлы для загрузки (путь в репо : локальный путь)
FILES = {
    "assemble_v2.py":                    "assemble_v2.py",
    "scripts/select_topic.py":           "scripts/select_topic.py",
    "scripts/generate_script.py":        "scripts/generate_script.py",
    "scripts/fetch_assets.py":           "scripts/fetch_assets.py",
    "scripts/generate_tts.py":           "scripts/generate_tts.py",
    "scripts/assemble_video.py":         "scripts/assemble_video.py",
    "scripts/notify_telegram.py":        "scripts/notify_telegram.py",
    "topics.json":                       "topics.json",
    "topic_state.json":                  "topic_state.json",
    ".github/workflows/make_video.yml":  ".github/workflows/make_video.yml",
    ".github/workflows/daily_factory.yml": ".github/workflows/daily_factory.yml",
    "requirements.txt":                  "requirements.txt",
    "README.md":                         "README.md",
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
        print(f"  ⚠️  ПРОПУСК (нет файла): {local_path}")
        return False
    content = base64.b64encode(lp.read_bytes()).decode()
    sha = get_sha(repo_path)
    data = {
        "message": f"add {repo_path}",
        "content": content,
    }
    if sha:
        data["sha"] = sha
    resp, err = api(repo_path, data)
    if err:
        print(f"  ❌ {repo_path}: {err[:120]}")
        return False
    print(f"  ✅ {repo_path}")
    return True

def make_workflow():
    """Создаёт .github/workflows/make_video.yml если нет локально."""
    wf = Path(".github/workflows/make_video.yml")
    wf.parent.mkdir(parents=True, exist_ok=True)
    if wf.exists():
        return
    wf.write_text('''name: Make Video Factory

on:
  workflow_dispatch:
    inputs:
      channel:
        description: "Channel (twistedtruths/crimeledger/mindtactics)"
        required: true
        default: "twistedtruths"
  schedule:
    - cron: "0 3 * * 1,3,5"  # Mon/Wed/Fri 09:00 Almaty (UTC+6)

jobs:
  make-video:
    runs-on: ubuntu-latest
    timeout-minutes: 180

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install system deps
        run: |
          sudo apt-get update -q
          sudo apt-get install -y ffmpeg espeak-ng libsndfile1

      - name: Install Python deps
        run: |
          pip install -q requests python-dotenv google-generativeai kokoro soundfile

      - name: Select topic
        run: python scripts/select_topic.py
        env:
          CHANNEL: ${{ github.event.inputs.channel || \'twistedtruths\' }}

      - name: Generate script
        run: python scripts/generate_script.py
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}

      - name: Fetch assets
        run: python scripts/fetch_assets.py
        env:
          PEXELS_API_KEY: ${{ secrets.PEXELS_API_KEY }}
          PIXABAY_API_KEY: ${{ secrets.PIXABAY_API_KEY }}

      - name: Generate TTS
        run: python scripts/generate_tts.py

      - name: Assemble video
        run: python assemble_v2.py

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: video-${{ github.run_id }}
          path: projects/*/render/FINAL_v3.mp4
          retention-days: 7

      - name: Notify Telegram
        run: python scripts/notify_telegram.py
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          RUN_ID: ${{ github.run_id }}
        continue-on-error: true
''')
    print("  📝 Создан make_video.yml")

def make_readme():
    p = Path("README.md")
    if p.exists(): return
    p.write_text("""# FORTS DIGITAL — OpenMontage Factory

Automated YouTube documentary pipeline.

## Channels
- **TwistedTruths** — Betrayal/Revenge ($12.82 RPM)
- **CrimeLedger** — Financial Crime ($12-18 RPM)
- **MindTactics** — Dark Psychology ($8-14 RPM)

## Stack
- Script: Gemini 2.0 Flash
- TTS: Kokoro-82M (CPU)
- Footage: Pexels + Pixabay
- Assembly: FFmpeg (Ken Burns + subtitles + color grade)
- CI: GitHub Actions (Mon/Wed/Fri)

## Run manually
Actions → Make Video Factory → Run workflow → select channel
""")

def main():
    print("="*50)
    print("FORTS DIGITAL — GitHub Upload")
    print("="*50)

    make_workflow()
    make_readme()

    ok = 0
    fail = 0
    for repo_path, local_path in FILES.items():
        result = upload(repo_path, local_path)
        if result: ok += 1
        else: fail += 1
        time.sleep(0.3)  # rate limit

    print(f"\n{'='*50}")
    print(f"✅ Загружено: {ok}")
    print(f"❌ Пропущено: {fail}")
    print(f"\n🔗 Репо: https://github.com/{REPO}")
    print(f"⚙️  Actions: https://github.com/{REPO}/actions")
    print(f"\n📌 Добавь секреты:")
    print(f"https://github.com/{REPO}/settings/secrets/actions")
    print("  - GEMINI_API_KEY")
    print("  - PEXELS_API_KEY")
    print("  - PIXABAY_API_KEY")
    print("  - TELEGRAM_BOT_TOKEN (опционально)")
    print("  - TELEGRAM_CHAT_ID (опционально)")

if __name__ == "__main__":
    main()
