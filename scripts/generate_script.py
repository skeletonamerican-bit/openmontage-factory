import json, os, sys
from pathlib import Path

from scripts.llm_router import get_router

CONFIGS = {
    "weirdhistory": {
        "style": "Archive Noir, Gothic Dark Academia, historical mystery documentary",
        "tone": "dramatic, haunting, reverent with morbid curiosity",
        "scenes": 25,
        "duration_min": 6.25,
        "visual_style": "Archive Noir / Gothic Dark Academia",
    },
    "crimeledger": {
        "style": "David Fincher crime documentary (Se7en, Zodiac, Mindhunter)",
        "tone": "investigative, cold, methodical, shocking",
        "scenes": 18,
        "duration_min": 4.5,
        "visual_style": "Fincher Cold / Crime Documentary",
    },
    "mindtactics": {
        "style": "Psychological Horror, Analog Horror aesthetic",
        "tone": "unsettling, analytical, clinical, creeping dread",
        "scenes": 15,
        "duration_min": 3.75,
        "visual_style": "Analog Horror / Psychological Thriller",
    },
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
6. EACH scene is EXACTLY 15 seconds — narration must be 45-55 words

For EACH scene, provide these fields:
- narration: 45-55 words of voiceover for this 15-second scene
- video_prompt: [cinematic action/dynamic scene description], {video_style_prompt}
- photo_prompt_1: [close-up detail shot description], {photo_style_prompt}
- photo_prompt_2: [wide or medium shot description, different angle], {photo_style_prompt}
- sfx: "{sfx_value}"

{niche_prompt_notes}

Return ONLY valid JSON, NO markdown:
{{"title":"","description":"","tags":[],"scenes":[{{"id":1,"title":"","narration":"","video_prompt":"","photo_prompt_1":"","photo_prompt_2":"","sfx":""}}]}}"""


def main():
    ch = os.environ.get("CHANNEL", "weirdhistory").lower().strip()
    topic = os.environ.get("TOPIC", "The Lost History")
    cfg = CONFIGS.get(ch)
    if not cfg:
        print(f"ERROR: Unknown channel {ch}")
        sys.exit(1)

    niche_notes = {
        "weirdhistory": (
            "NICHE VIDEO PROMPT FORMULA:\n"
            "  video_prompt = \"[action from scene], [historical period], "
            "cinematic slow motion, chiaroscuro lighting, "
            "candlelight flicker, dark stone chamber, "
            "35mm film grain, high contrast amber shadows, "
            "4K cinematic, no modern elements\"\n\n"
            "NICHE PHOTO PROMPT FORMULA:\n"
            "  photo_prompt = \"[subject/character from scene], [historical period], "
            "historical archive photograph style, "
            "chiaroscuro portrait, dramatic side lighting, "
            "35mm film grain, aged sepia tones, "
            "gothic architecture background, "
            "ultra detailed, photorealistic\"\n\n"
            "SFX: \"cinematic_boom\""
        ),
        "crimeledger": (
            "NICHE VIDEO PROMPT FORMULA:\n"
            "  video_prompt = \"[action from scene], crime documentary style, "
            "cold blue teal color grade, Fincher aesthetic, "
            "forensic overhead lighting, slow cinematic push-in, "
            "rain-slicked streets, surveillance camera angle, "
            "high contrast desaturated, 4K\"\n\n"
            "NICHE PHOTO PROMPT FORMULA:\n"
            "  photo_prompt = \"[subject/evidence from scene], "
            "crime scene documentation style, "
            "cold forensic blue lighting, high contrast, "
            "desaturated teal grade, sharp focus, "
            "investigative documentary aesthetic, "
            "photorealistic, ultra detailed\"\n\n"
            "SFX: \"thud_dry\""
        ),
        "mindtactics": (
            "NICHE VIDEO PROMPT FORMULA:\n"
            "  video_prompt = \"[psychological action from scene], "
            "psychological horror aesthetic, "
            "analog VHS camera effect, monochrome with red accent, "
            "slow zoom into eyes, shadows and negative space, "
            "unsettling atmosphere, 16mm grain, "
            "horror film cinematography\"\n\n"
            "NICHE PHOTO PROMPT FORMULA:\n"
            "  photo_prompt = \"[psychological image/metaphor from scene], "
            "analog horror photography style, "
            "monochrome high contrast, single red accent element, "
            "deep shadows, claustrophobic framing, "
            "VHS artifact texture, photorealistic\"\n\n"
            "SFX: \"static_glitch\""
        ),
    }

    video_style_prompts = {
        "weirdhistory": "35mm film grain, chiaroscuro lighting, candlelit, dark stone chamber, amber shadows",
        "crimeledger": "cold blue teal, Fincher aesthetic, forensic lighting, desaturated, high contrast",
        "mindtactics": "analog VHS, monochrome with red accent, unsettling, horror cinematography",
    }

    photo_style_prompts = {
        "weirdhistory": "historical archive photograph, chiaroscuro, sepia tones, gothic, photorealistic",
        "crimeledger": "crime scene documentation, cold forensic blue, desaturated teal, photorealistic",
        "mindtactics": "analog horror photography, monochrome high contrast, red accent, VHS artifact",
    }

    sfx_map = {
        "weirdhistory": "cinematic_boom",
        "crimeledger": "thud_dry",
        "mindtactics": "static_glitch",
    }

    print(f"Channel:{ch} | Topic:{topic} | Scenes:{cfg['scenes']}")
    prompt_text = PROMPT.format(
        topic=topic,
        sfx_value=sfx_map.get(ch, ""),
        niche_prompt_notes=niche_notes.get(ch, ""),
        video_style_prompt=video_style_prompts.get(ch, ""),
        photo_style_prompt=photo_style_prompts.get(ch, ""),
        **cfg
    )

    router = get_router()
    result = router.complete(
        messages=[{"role": "user", "content": prompt_text}],
        max_tokens=8192,
        temperature=0.85,
    )

    if not result.success:
        print(f"ERROR: All models exhausted after {len(result.attempts)} attempts")
        for a in result.attempts[-5:]:
            print(f"  {a['model']}: code {a['code']}")
        sys.exit(1)

    print(f"Model: {result.model} | Attempts: {len(result.attempts)}")
    for a in result.attempts:
        print(f"  [{a['cycle']}] {a['model']} -> {a['code']}")

    text = result.text
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
