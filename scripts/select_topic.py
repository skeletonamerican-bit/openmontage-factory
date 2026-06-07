import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOPICS_FILE = ROOT / "topics.json"
STATE_FILE = ROOT / "topic_state.json"


def load_json(path, default=None):
    if path.exists():
        return json.loads(path.read_text())
    return default


def save_json(path, content):
    path.write_text(json.dumps(content, indent=2))


def pick_channel_and_topic(topics, state):
    channels = sorted(topics.keys())
    if not channels:
        raise ValueError("No channels found in topics.json")

    if state.get("channels") != channels:
        state = {
            "channels": channels,
            "last_channel": None,
            "next_topic_index": {channel: 0 for channel in channels},
        }

    last_channel = state.get("last_channel")
    if last_channel in channels:
        current_index = channels.index(last_channel)
        next_channel = channels[(current_index + 1) % len(channels)]
    else:
        next_channel = channels[0]

    topic_list = topics[next_channel]
    if not topic_list:
        raise ValueError(f"No topics available for channel {next_channel}")

    topic_index = state["next_topic_index"].get(next_channel, 0)
    selected_topic = topic_list[topic_index % len(topic_list)]

    state["next_topic_index"][next_channel] = (topic_index + 1) % len(topic_list)
    state["last_channel"] = next_channel
    return next_channel, selected_topic, state


def write_github_env(channel, topic):
    env_path = os.getenv("GITHUB_ENV")
    lines = [f"CHANNEL={channel}", f"TOPIC={topic}"]
    if env_path:
        with open(env_path, "a") as f:
            for line in lines:
                f.write(line + "\n")

    for line in lines:
        print(line)


def main():
    topics = load_json(TOPICS_FILE, {})
    if not topics:
        raise SystemExit("topics.json is missing or empty")

    state = load_json(STATE_FILE, {}) or {}
    channel, topic, new_state = pick_channel_and_topic(topics, state)
    save_json(STATE_FILE, new_state)
    write_github_env(channel, topic)


if __name__ == "__main__":
    main()
