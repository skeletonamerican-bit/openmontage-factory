import json, os, sys, urllib.request, urllib.error
from pathlib import Path

API_URL = "https://models.inference.ai.azure.com/chat/completions"
MODEL   = "gpt-oss-120b"

CONFIGS = {
    "weirdhistory": {
        "style": "Gothic Dark Academia, Archive Noir aesthetic, historical mystery documentary",
        "tone": "dramatic, haunting, reverent with morbid curiosity",
        "scenes": 25,
        "duration_min": 5,
        "visual_style": "Gothic Dark Academia / Archive Noir",
        "color_note": "deep black, amber gold, ink blue palette"
    },
    "crimeledger": {
        "style": "Scandinavian Detective noir, David Fincher aesthetic (Se7en, Zodiac)",
        "tone": "investigative, cold, methodical, shocking",
        "scenes": 18,
        "duration_min": 3.6,
        "visual_style": "Scandinavian Detective / David Fincher",
        "color_note": "dark green, cold blue, steel grey palette"
    },
    "mindtactics": {
        "style": "Psychological Thriller, Analog Horror aesthetic",
        "tone": "unsettling, analytical, clinical, creeping dread",
        "scenes": 15,
        "duration_min": 3,
        "visual_style": "Psychological Thriller / Analog Horror",
        "color_note": "monochrome with red accent palette"
    },
}

VISUAL_SUFFIXES = {
    "weirdhistory": "[SFX: paper rustle, distant clock chime] color_note: deep black, amber gold, ink blue",
    "crimeledger": "[SFX: rain patter, typewriter click] color_note: dark green, cold blue, steel grey",
    "mindtactics": "[SFX: tape rewind, static hiss] color_note: monochrome with red accent",
}

PROMPT = """You are an elite YouTube documentary scriptwriter like MagnatesMedia.
Style: {style}
Topic: {topic}
Tone: {tone}

Write EXACTLY {scenes} scenes for a ~{duration_min} minute documentary.

RULES:
1. Scene 1: SHOCKING hook — reveal the ending first with specific numbers/names/dates
2. Every 3 scenes: micro-twist ("But they didn't know...")
3. ALL narrations must use SPECIFIC details: exact amounts, real names, dates, locations
4. Last scene: moral lesson + "Subscribe to never miss a story like this"
5. Structure: Hook → Origin → Rise → Betrayal → Unravels → Consequences → Resolution → CTA
6. Each scene is EXACTLY 12 seconds — narration must be ~25-30 words

For EACH scene, the "visual" field MUST use this EXACT format with 3 prompts separated by pipes:
IMG1: [describe photo1: the primary photo scene, vivid visual detail, {img_style}]
| IMG2: [describe photo2: the secondary photo scene, complementary shot, {img_style}]
| VID: [describe the 4-second video clip scene, cinematic motion, {vid_style}]

Channel image style keywords - weave these into IMG prompts:
{img_keywords}

Channel video style keywords - weave these into VID prompts:
{vid_keywords}

Then append: {sfx_suffix}

Return ONLY valid JSON, NO markdown:
{{"title":"","description":"","tags":[],"scenes":[{{"id":1,"title":"","narration":"","visual":"","duration_seconds":12,"emotion":""}}]}}"""

def main():
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("ERROR: GITHUB_TOKEN not set")
        sys.exit(1)
    ch = os.environ.get("CHANNEL", "weirdhistory").lower().strip()
    topic = os.environ.get("TOPIC", "The Lost History")
    cfg = CONFIGS.get(ch)
    if not cfg:
        print(f"ERROR: Unknown channel {ch}")
        sys.exit(1)
    sfx = VISUAL_SUFFIXES.get(ch, "")

    img_keywords_map = {
        "weirdhistory": "historical archive photograph, 35mm film grain, Rembrandt lighting, chiaroscuro contrast, amber candlelight, deep black shadows, dark academia aesthetic, moody atmospheric, Caravaggio style lighting, dusty archive",
        "crimeledger": "crime scene photograph, cold blue steel lighting, fluorescent light, dark green shadows, forensic documentary style, high contrast black and white with teal tones, Fincher aesthetic, clinical cold atmosphere",
        "mindtactics": "psychological portrait, high contrast monochrome, single red accent color, psychiatric file aesthetic, dark surreal, analog horror style, glitch distortion, VHS aesthetic",
    }
    vid_keywords_map = {
        "weirdhistory": "cinematic dark historical scene, slow dramatic movement, film grain overlay, amber tones",
        "crimeledger": "crime documentary footage, cold steel blue tones, slow motion, noir atmosphere",
        "mindtactics": "psychological thriller abstract, chess pieces slow motion, broken mirror reflection, ink dissolving in water, silhouette in fog, VHS glitch",
    }

    print(f"Channel:{ch} | Topic:{topic} | Scenes:{cfg['scenes']} | Model:{MODEL}")
    prompt = PROMPT.format(
        topic=topic, sfx_suffix=sfx,
        img_keywords=img_keywords_map.get(ch, ""),
        vid_keywords=vid_keywords_map.get(ch, ""),
        img_style=cfg["visual_style"],
        vid_style=cfg["visual_style"],
        **cfg
    )
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 8192,
        "temperature": 0.85
    }).encode()
    req = urllib.request.Request(API_URL, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            text = json.loads(r.read())["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        print(f"ERROR HTTP {e.code}: {e.read().decode()[:300]}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
    except:
        s = text.find("{")
        e = text.rfind("}") + 1
        data = json.loads(text[s:e])
    out = Path(f"projects/{ch}")
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "script.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    scenes = data.get("scenes", [])
    print(f"OK: {len(scenes)} scenes -> projects/{ch}/script.json")
    print(f"Title: {data.get('title', '')}")

if __name__ == "__main__":
    main()
