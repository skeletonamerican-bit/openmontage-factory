"""
TwistedTruths EP1 — Full Pipeline
Runs: TTS → Footage → Music → Assemble
"""
import os, json, subprocess, requests, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────
BASE    = Path("/workspaces/OpenMontage")
PROJ    = BASE / "projects/weirdhistory"
AUDIO   = PROJ / "audio"
FOOTAGE = PROJ / "footage"
MUSIC   = PROJ / "music"
RENDER  = PROJ / "render"
MODEL   = BASE / "models/piper/en_US-lessac-high.onnx"

for d in [AUDIO, FOOTAGE, MUSIC, RENDER]:
    d.mkdir(parents=True, exist_ok=True)

PEXELS_KEY  = os.getenv("PEXELS_API_KEY", "")
PIXABAY_KEY = os.getenv("PIXABAY_API_KEY", "")

# ── Script ─────────────────────────────────────────────
SCENES = [
    {
        "id": "s01_hook",
        "duration": 30,
        "pexels_query": "woman silhouette office window rain city",
        "narration": (
            "She handed her business to her best friend. "
            "The warning signs were there. She just chose to call them help. "
            "But in the world of high-stakes partnerships, "
            "sometimes the person holding the ladder "
            "is the one preparing to pull it down."
        )
    },
    {
        "id": "s02_golden_cage",
        "duration": 75,
        "pexels_query": "two women business partners laughing notebook startup",
        "narration": (
            "Claire spent five years building Sienna Botanicals "
            "from a tiny kitchen experiment into a boutique organic skincare brand "
            "valued at two million dollars. It was her baby. "
            "By late 2025, the rapid scaling was suffocating her. "
            "Enter Danielle. Danielle was Claire's maid of honor, her confidante, "
            "and a seasoned operational manager. "
            "When Claire's father fell terminally ill, Danielle stepped in, "
            "offering to manage daily operations so Claire could spend "
            "those final precious months at her father's bedside. "
            "It felt like a miracle. Danielle proposed a fifty-fifty partnership. "
            "Claire, blinded by grief and gratitude, signed without a second thought. "
            "She trusted Danielle with her life. Therefore, she trusted her with her life's work."
        )
    },
    {
        "id": "s03_crack",
        "duration": 105,
        "pexels_query": "woman looking at laptop bank statement dark room",
        "narration": (
            "It started small. Three months after Danielle took the operational reins, "
            "Claire returned to the office part-time. The atmosphere had shifted. "
            "The team Claire had hand-picked looked down when she walked by. "
            "Danielle had moved Claire's personal belongings "
            "out of the main corner office into a smaller, windowless space down the hall, "
            "calling it a quiet environment for her recovery. Claire brushed it off. "
            "But then came the financial discrepancy. "
            "While reviewing quarterly accounts, Claire noticed "
            "a series of large wire transfers to an unfamiliar entity "
            "called Vanguard Consulting Group. The total was ninety-five thousand dollars. "
            "All authorized by Danielle. "
            "When Claire asked about it over lunch, Danielle didn't flinch. "
            "She smiled and said it was a tax mitigation strategy. "
            "It was classic gaslighting. "
            "Claire wanted to believe her. "
            "But that night, Claire's intuition kept her awake. "
            "She logged into the corporate banking portal at two in the morning. "
            "What she found made her breath catch in her throat."
        )
    },
    {
        "id": "s04_slow_takeover",
        "duration": 90,
        "pexels_query": "office door frosted glass silhouette corporate",
        "narration": (
            "The wire transfers weren't tax strategies. "
            "They were systematic drains on the company's operating capital. "
            "But when Claire tried to log back in the next morning to print the documents, "
            "her access code failed. She tried again. Locked. "
            "She called the bank, only to be told that her name had been removed "
            "as an authorized administrator on the primary account. "
            "The authorization had been changed via an amendment to the operating agreement, "
            "an amendment that Claire had signed months earlier during her grief, "
            "tucked inside a thick stack of routine operational paperwork. "
            "Danielle had legally stripped Claire of her financial oversight."
        )
    },
    {
        "id": "s05_staff_whisperer",
        "duration": 90,
        "pexels_query": "woman walking through empty office staff looking away",
        "narration": (
            "Danielle hadn't just taken the bank accounts. "
            "She had taken the hearts and minds of the staff. "
            "Over the previous six months, Danielle had quietly painted Claire "
            "as an unstable, absentee founder who was draining the company's resources "
            "for personal family matters. "
            "She had implemented a new bonus structure "
            "that made the design team entirely dependent on Danielle's personal approval. "
            "Claire was now a ghost in her own building. "
            "When Claire tried to schedule an all-hands meeting, "
            "only two people showed up. "
            "The others had been pulled into an urgent client emergency "
            "orchestrated by Danielle. "
            "Claire walked into the breakroom and overheard her lead designer "
            "telling a colleague that Claire was trying to ruin the company "
            "because she couldn't handle her personal life. "
            "She was being cast as the villain in her own story."
        )
    },
    {
        "id": "s06_isolated",
        "duration": 30,
        "pexels_query": "woman walking alone glass building exterior city",
        "narration": (
            "That afternoon, Claire walked to her car, "
            "her hands shaking so hard she dropped her keys. "
            "She sat in the driver's seat, staring at the glass tower. "
            "She took out her phone to call her lawyer. "
            "But before she could dial, an email notification popped up on her screen."
        )
    },
    {
        "id": "s07_secret_entity",
        "duration": 90,
        "pexels_query": "legal documents table highlighter pen late night",
        "narration": (
            "The email was a formal notice. Danielle was invoking a clause "
            "in the amended operating agreement that allowed for the forced buyout "
            "of a partner deemed incapable of performing fiduciary duties "
            "due to prolonged personal absence. "
            "The buyout offer was fifty thousand dollars, "
            "for a business Claire had built to a two-million-dollar valuation. "
            "It was an insult. "
            "But instead of breaking down, Claire got cold. "
            "She hired a forensic accountant who specialized in corporate asset recovery. "
            "For two weeks, they worked out of Claire's dining room, "
            "reconstructing the paper trail Danielle thought she had buried. "
            "They discovered that Vanguard Consulting Group was not a consulting firm at all. "
            "It was a shell company registered in Delaware, "
            "with Danielle listed as the sole beneficial owner. "
            "Danielle had been paying her own shell company to consult on projects "
            "that didn't exist, using Sienna Botanicals' money "
            "to fund her personal lifestyle and build a legal war chest."
        )
    },
    {
        "id": "s08_facing_mirror",
        "duration": 90,
        "pexels_query": "split screen contracts signatures documents comparison",
        "narration": (
            "But the biggest revelation lay in the operating agreement amendment itself. "
            "The forensic team analyzed the digital signature certificate. "
            "The metadata revealed the document had been signed "
            "from an IP address mapped directly to Danielle's home desktop computer "
            "at three fourteen AM on a Tuesday, "
            "a night Claire was documented as being at the hospital with her father. "
            "Claire had never seen that amendment, let alone signed it. "
            "Danielle had forged Claire's digital signature. "
            "She had used Claire's saved digital certificate on the shared company server "
            "to sign the document that stripped Claire of her rights. "
            "It was a federal crime."
        )
    },
    {
        "id": "s09_confrontation",
        "duration": 30,
        "pexels_query": "conference room tense meeting two women glass table",
        "narration": (
            "With the evidence compiled, Claire's lawyer advised her "
            "to file for an emergency injunction. "
            "But Claire didn't want a quiet settlement. "
            "She wanted to look Danielle in the eyes when the trap snapped shut. "
            "She scheduled a meeting at the office "
            "under the pretense of discussing the fifty-thousand-dollar buyout. "
            "Danielle sat at the head of the conference table, "
            "a leather-bound folder open in front of her. "
            "She pushed a pen toward Claire. "
            "She told Claire it was time to let go, to focus on her healing. "
            "But Claire didn't take the pen. "
            "Instead, she slid a manila folder across the glass."
        )
    },
    {
        "id": "s10_phoenix_strategy",
        "duration": 90,
        "pexels_query": "forensic documents IP address tracking legal evidence",
        "narration": (
            "Danielle opened the folder. "
            "The first page was the IP address log proving the forgery. "
            "The second was the Delaware corporate registry "
            "linking her directly to Vanguard Consulting. "
            "Danielle's composure cracked. "
            "The warmth drained from her face, leaving a cold, pale mask. "
            "She didn't deny it. Instead, she leaned back, looked at Claire, and said, "
            "So what? You don't have the money to fight me in court. "
            "This company is mine now. "
            "But Claire had already anticipated that move. "
            "The injunction had been filed two hours prior. "
            "The bank accounts were frozen. "
            "The board of directors, who had been misled by Danielle, "
            "had been sent the forensic report. "
            "While Danielle had been focusing on the internal staff, "
            "Claire had gone directly to the primary suppliers "
            "and the brand's top wholesale accounts. "
            "They refused to ship any inventory "
            "until the ownership dispute was resolved. "
            "Danielle hadn't just been cornered. "
            "She had been completely cut off from the oxygen of the business."
        )
    },
    {
        "id": "s11_legal_reclaim",
        "duration": 90,
        "pexels_query": "woman standing outside office building autumn victory",
        "narration": (
            "It took six months of legal battles, "
            "but the forgery evidence was undeniable. "
            "Faced with potential federal wire fraud and forgery charges, "
            "Danielle agreed to a settlement. "
            "She surrendered her shares, resigned from the board, "
            "and was legally barred from entering the premises of Sienna Botanicals. "
            "The business was Claire's again. "
            "But the victory was bittersweet. "
            "The brand had taken a severe reputational hit, "
            "and Claire had to rebuild the trust of her staff from the ground up. "
            "More than that, she had lost her best friend. "
            "The person who had stood beside her at her wedding, "
            "who had held her hand when her father passed, "
            "had been systematically planning her professional execution. "
            "Claire realized that the most dangerous threats "
            "don't come from your enemies. "
            "They come from the people who know exactly where your armor is weak."
        )
    },
    {
        "id": "s12_outro",
        "duration": 30,
        "pexels_query": "woman entrepreneur desk empowered morning light laptop",
        "narration": (
            "In business, as in life, trust is a beautiful thing. "
            "But blind trust is a weapon you hand to someone else. "
            "Keep your eyes open, watch the paper trail, "
            "and never let friendship silence your instincts. "
            "If this story made you look twice at your own partnerships, "
            "click the video on your screen right now "
            "to see how another founder survived a hostile takeover. "
            "Until next time, stay vigilant."
        )
    }
]

# ── Step 1: Save script.json ────────────────────────────
script_path = PROJ / "script.json"
with open(script_path, "w") as f:
    json.dump({"title": "The Best Friend Betrayal", "scenes": SCENES}, f, indent=2)
print(f"[1/4] script.json saved — {len(SCENES)} scenes")

# ── Step 2: Generate TTS ────────────────────────────────
print("\n[2/4] Generating TTS audio with Piper...")

if not MODEL.exists():
    print("  ERROR: Piper model not found. Run:")
    print(f"  wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/high/en_US-lessac-high.onnx -O {MODEL}")
else:
    for i, scene in enumerate(SCENES):
        out = AUDIO / f"{scene['id']}.wav"
        if out.exists():
            print(f"  SKIP {scene['id']} (exists)")
            continue
        cmd = f'echo "{scene["narration"]}" | piper --model {MODEL} --output_file {out}'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  OK  [{i+1}/{len(SCENES)}] {scene['id']}.wav")
        else:
            print(f"  ERR [{i+1}/{len(SCENES)}] {scene['id']}: {result.stderr[:80]}")

# ── Step 3: Fetch Pexels footage ────────────────────────
print("\n[3/4] Fetching Pexels footage...")

if not PEXELS_KEY:
    print("  ERROR: PEXELS_API_KEY not set")
else:
    headers = {"Authorization": PEXELS_KEY}
    for i, scene in enumerate(SCENES):
        out = FOOTAGE / f"{scene['id']}.mp4"
        if out.exists():
            print(f"  SKIP {scene['id']} (exists)")
            continue
        url = f"https://api.pexels.com/videos/search?query={requests.utils.quote(scene['pexels_query'])}&per_page=3&orientation=landscape"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"  ERR [{i+1}] {scene['id']}: HTTP {r.status_code}")
            continue
        videos = r.json().get("videos", [])
        if not videos:
            print(f"  ERR [{i+1}] {scene['id']}: no results")
            continue
        # Pick best quality
        files = videos[0].get("video_files", [])
        hd = next((f for f in files if f.get("quality") == "hd"), files[0] if files else None)
        if not hd:
            print(f"  ERR [{i+1}] {scene['id']}: no video file")
            continue
        vid_r = requests.get(hd["link"], stream=True, timeout=30)
        with open(out, "wb") as f:
            for chunk in vid_r.iter_content(8192):
                f.write(chunk)
        size = out.stat().st_size // 1024
        print(f"  OK  [{i+1}/{len(SCENES)}] {scene['id']}.mp4 ({size}KB)")
        time.sleep(0.3)

# ── Step 4: Fetch Pixabay music ─────────────────────────
print("\n[4/4] Fetching background music...")

if not PIXABAY_KEY:
    print("  ERROR: PIXABAY_API_KEY not set")
else:
    music_file = MUSIC / "background.mp3"
    if music_file.exists():
        print(f"  SKIP music (exists)")
    else:
        url = f"https://pixabay.com/api/music/?key={PIXABAY_KEY}&q=suspenseful+dark+cinematic&per_page=3"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            tracks = r.json().get("hits", [])
            if tracks:
                mp3_url = tracks[0].get("audio", "")
                if mp3_url:
                    mr = requests.get(mp3_url, stream=True, timeout=30)
                    with open(music_file, "wb") as f:
                        for chunk in mr.iter_content(8192):
                            f.write(chunk)
                    print(f"  OK  background.mp3 ({music_file.stat().st_size//1024}KB)")
                else:
                    print("  ERR: no audio URL in response")
            else:
                print("  ERR: no tracks found")
        else:
            print(f"  ERR: HTTP {r.status_code}")

# ── Summary ─────────────────────────────────────────────
print("\n" + "="*50)
print("PIPELINE SUMMARY")
print("="*50)
wav_files  = list(AUDIO.glob("*.wav"))
mp4_files  = list(FOOTAGE.glob("*.mp4"))
mp3_files  = list(MUSIC.glob("*.mp3"))
print(f"TTS audio:  {len(wav_files)}/{len(SCENES)} files")
print(f"Footage:    {len(mp4_files)}/{len(SCENES)} files")
print(f"Music:      {len(mp3_files)}/1 files")
ready = len(wav_files) == len(SCENES) and len(mp4_files) == len(SCENES) and len(mp3_files) >= 1
print(f"\nStatus: {'READY FOR ASSEMBLY ✓' if ready else 'INCOMPLETE — check errors above'}")
