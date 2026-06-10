import json, os, sys
from pathlib import Path

TOPICS_FILE = Path("topics.json")
if not TOPICS_FILE.exists():
    sys.exit("ERROR: topics.json not found")

TOPICS = json.loads(TOPICS_FILE.read_text(encoding="utf-8"))

CHANNEL_ROTATION = ["weirdhistory", "crimeledger", "mindtactics"]

def main():
    channel = os.environ.get("CHANNEL", "").lower().strip()
    topic = os.environ.get("TOPIC", "").strip()

    state_file = Path("topic_state.json")
    state = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
        except:
            state = {}

    channels = state.get("channels", CHANNEL_ROTATION)
    last_ch = state.get("last_channel", "mindtactics")
    indices = state.get("next_topic_index", {})

    if not channel or channel not in TOPICS:
        idx = channels.index(last_ch) + 1 if last_ch in channels else 0
        channel = channels[idx % len(channels)]

    if not topic:
        idx = indices.get(channel, 0)
        topics = TOPICS[channel]
        topic = topics[idx % len(topics)]
        indices[channel] = (idx + 1) % len(topics)

    state["last_channel"] = channel
    state["next_topic_index"] = indices
    state["channels"] = channels
    state_file.write_text(json.dumps(state, indent=2))

    print(f"Channel: {channel}")
    print(f"Topic: {topic}")

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"CHANNEL={channel}\n")
            f.write(f"TOPIC={topic}\n")

    github_env = os.environ.get("GITHUB_ENV", "")
    if github_env:
        with open(github_env, "a") as f:
            f.write(f"CHANNEL={channel}\n")
            f.write(f"TOPIC={topic}\n")

if __name__ == "__main__":
    main()
