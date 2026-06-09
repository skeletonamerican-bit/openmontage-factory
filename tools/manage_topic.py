import json
import os
from pathlib import Path

STATE_FILE = Path('topic_state.json')

def get_next_topic():
    with open('topics.json', 'r') as f:
        topics = json.load(f)
    
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
    else:
        state = {'last_channel_index': 0, 'topic_indices': {ch: 0 for ch in topics.keys()}}
        
    channels = list(topics.keys())
    
    # Simple round-robin for channel
    channel_index = state['last_channel_index']
    channel = channels[channel_index]
    
    # Get next topic for this channel
    topic_index = state['topic_indices'][channel]
    topic = topics[channel][topic_index]
    
    # Update state
    state['topic_indices'][channel] = (topic_index + 1) % len(topics[channel])
    state['last_channel_index'] = (channel_index + 1) % len(channels)
    
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)
        
    return channel, topic

if __name__ == "__main__":
    channel, topic = get_next_topic()
    print(f"CHANNEL={channel}")
    print(f"TOPIC={topic}")
