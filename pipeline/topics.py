import json, os, base64, requests
from pathlib import Path

TOPICS_FILE = Path("topics.json")
STATE_FILE = Path("topic_state.json")
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "")
GH_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")


def load_topics():
    if not TOPICS_FILE.exists():
        return {}
    return json.loads(TOPICS_FILE.read_text(encoding="utf-8"))


def load_state():
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    _commit_state_to_github(state)


def _commit_state_to_github(state):
    if not GH_TOKEN or not GITHUB_REPO:
        print("[topics] No GITHUB_TOKEN or GITHUB_REPOSITORY set, skipping GitHub commit", flush=True)
        return

    content = json.dumps(state, indent=2)
    encoded = base64.b64encode(content.encode()).decode()

    # First, get the SHA of the existing file
    sha = None
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/topic_state.json"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except Exception as e:
        print(f"[topics] Failed to get current file SHA: {e}", flush=True)

    # Commit the updated file
    data = {
        "message": "Update topic_state.json [skip ci]",
        "content": encoded,
        "branch": os.environ.get("GITHUB_REF_NAME", "main"),
    }
    if sha:
        data["sha"] = sha

    try:
        r = requests.put(url, headers=headers, json=data, timeout=10)
        if r.status_code in (200, 201):
            print(f"[topics] topic_state.json committed to GitHub", flush=True)
        else:
            print(f"[topics] GitHub commit failed: {r.status_code} {r.text[:200]}", flush=True)
    except Exception as e:
        print(f"[topics] GitHub commit error: {e}", flush=True)


def get_next_topic(channel):
    topics = load_topics()
    state = load_state()
    channel_topics = topics.get(channel, [])
    if not channel_topics:
        raise ValueError(f"No topics found for channel '{channel}'")

    idx = state.get("next_topic_index", {}).get(channel, 0)
    if idx >= len(channel_topics):
        idx = 0
    topic = channel_topics[idx]

    if "next_topic_index" not in state:
        state["next_topic_index"] = {}
    state["next_topic_index"][channel] = idx + 1
    state["last_channel"] = channel
    save_state(state)

    return topic


def get_remaining_count(channel):
    topics = load_topics()
    state = load_state()
    channel_topics = topics.get(channel, [])
    idx = state.get("next_topic_index", {}).get(channel, 0)
    return max(0, len(channel_topics) - idx)


def list_remaining(channel):
    topics = load_topics()
    state = load_state()
    channel_topics = topics.get(channel, [])
    idx = state.get("next_topic_index", {}).get(channel, 0)
    return channel_topics[idx:] if idx < len(channel_topics) else []
