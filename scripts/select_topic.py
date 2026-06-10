import json, os, sys
from pathlib import Path

TOPICS = {
    "weirdhistory": [
        "The Nazi Officer Who Saved 300 Jews and Was Executed",
        "The Roman Emperor Who Was Actually a Mad Scientist",
        "The Forgotten Pyramid Built by a Lost Civilization",
        "The Witches of Scotland: The Last Witch Execution",
        "The Alchemist Who Almost Found Immortality",
        "The Ghost Ship That Vanished Without a Trace",
        "The Cursed Pharaoh's Tomb That Killed Archaeologists",
        "The Medieval Knight Who Fought a Hundred Duels",
        "The Secret Society That Controlled Kings",
        "The Plague Doctor Who Cured the Incurable",
        "The Assassination Plot That Changed World History",
        "The Library That Burned with All the World's Knowledge",
        "The Emperor Who Tried to Stop Time",
        "The Prisoner in the Iron Mask: The True Story",
        "The Artist Who Faked Her Death and Started a Cult",
        "The Cannibal Kingdom of the Amazon",
        "The Doomsday Clock That Was Minutes from Midnight",
        "The Underground City Built by Slaves",
        "The Spy Who Stole the Atom Bomb Secrets",
        "The Queen Who Ruled from Beyond the Grave",
        "The Shipwreck Full of Gold That Was Never Found",
        "The Mad King Who Built a Mechanical World",
        "The Cult That Worshipped a False Prophet",
        "The Genocide the World Refused to Believe",
        "The Final Stand of the Last Samurai",
    ],
    "crimeledger": [
        "The Ponzi Scheme That Robbed 40,000 Pensioners",
        "The Hedge Fund Manager Who Faked His Own Death",
        "The Banker Who Laundered for the Cartels",
        "The CEO Who Ran a Billion Dollar Crypto Scam",
        "The Art Forger Who Fooled the Louvre",
        "The Diamond Heist That Bankrupted a Government",
        "The Inside Trader Who Made Millions on Death",
        "The Money Launderer Who Hid Cash in Paradise",
        "The Identity Thief Who Stole a Senator's Life",
        "The Jewel Thief Who Was Never Caught",
        "The Whistleblower Who Took Down a Bank",
        "The Tax Evader Who Built an Offshore Empire",
        "The Fraud That Bankrupted an Entire Country",
        "The Cybercriminal Who Stole from Central Banks",
        "The Real Estate Scam That Left Thousands Homeless",
        "The Insurance Fraud That Killed 40 People",
        "The Forger Who Printed His Own Currency",
        "The Smuggler Who Moved Gold Across Continents",
    ],
    "mindtactics": [
        "The Psychology of the Puppet Master",
        "Engineering Emotional Response",
        "The Cognitive Bias Trap",
        "Persuasion in the Digital Age",
        "The Memory Manipulation Study",
        "Influencing the Collective Mind",
        "Decoding Subtle Body Language",
        "Tactical Social Engineering",
        "The Psychology of False Consensus",
        "Mastering Digital Influence",
        "The Dark Art of Gaslighting",
        "How Narcissists Rewrite Reality",
        "The Science of Brainwashing",
        "The Cults That Controlled Their Members",
        "The Power of Subliminal Messaging",
    ],
}

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
