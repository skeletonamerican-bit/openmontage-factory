import json, os
from pathlib import Path

TOPICS_FILE = Path("topics.json")
STATE_FILE = Path("topic_state.json")


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
