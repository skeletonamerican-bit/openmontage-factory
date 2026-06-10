import json, os, subprocess, sys, shutil
from pathlib import Path

CHANNEL = os.getenv("CHANNEL", "weirdhistory").strip().lower()
PROJECT_DIR = Path("projects") / CHANNEL
AUDIO_DIR = PROJECT_DIR / "audio"
FOOTAGE_DIR = PROJECT_DIR / "footage"
MUSIC_FILE = PROJECT_DIR / "music" / "background.mp3"
SCRIPT_FILE = PROJECT_DIR / "script.json"
OUTPUT_DIR = PROJECT_DIR / "render"
OUTPUT_FINAL = OUTPUT_DIR / "FINAL_v3.mp4"

W, H, FPS = 1920, 1080, 30
FONT = "DejaVuSans-Bold"
FONT_SIZE = 76
SUB_Y_PCT = 0.82
KB_NORMAL = ("1.00", "1.05")
KB_PEAK = ("1.12", "1.00")
PEAK_SCENES = {3, 6, 9, 12, 15, 18, 21, 24}

CHANNEL_CONFIGS = {
    "weirdhistory": {
        "color_grade": (
            "curves=all='0/0 0.5/0.44 1/0.92',"
            "eq=saturation=0.85:contrast=1.15:brightness=-0.04"
        ),
        "extra_vf": (
            "geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
            "a='alpha(X,Y)',"
            "noise=alls=8:allf=t+u,"
            "colorbalance=rs=-0.1:gs=-0.05:bs=0.1:rh=-0.05:gh=0.0:bh=0.05,"
            "vignette=PI/4"
        ),
        "sfx_cut": "cinematic_boom",
        "description": "35mm film grain overlay, vignette, Chiaroscuro lighting — Gothic Dark Academia",
    },
    "crimeledger": {
        "color_grade": (
            "curves=all='0/0.05 0.5/0.42 1/0.88',"
            "eq=saturation=0.70:contrast=1.12:brightness=-0.03:gamma=0.95,"
            "colorbalance=rs=-0.15:gs=0.05:bs=0.15"
        ),
        "extra_vf": (
            "hue=H=0.02:s=0,"
            "noise=alls=4:allf=t,"
            "vignette=PI/3.5"
        ),
        "sfx_cut": "typewriter_click",
        "description": "Cold steel grade: dark green, cold blue, steel grey — Scandinavian Detective noir",
    },
    "mindtactics": {
        "color_grade": (
            "hue=s=0,"
            "curves=all='0/0.02 0.5/0.5 1/0.95',"
            "eq=contrast=1.2:brightness=-0.05"
        ),
        "extra_vf": (
            "geq=r='r(X,Y)+g(X,Y)*0.05*gte(sin(T*20),0.9)*0.3':"
            "g='g(X,Y)+b(X,Y)*0.05*gte(sin(T*20+2),0.9)*0.3':"
            "b='b(X,Y)+r(X,Y)*0.05*gte(sin(T*20+4),0.9)*0.3',"
            "noise=alls=6:allf=t+u,"
            "vignette=PI/3"
        ),
        "sfx_cut": "tape_rewind",
        "description": "VHS glitch overlay, monochrome with red/green accent — Analog Horror",
    },
}

SFX_CHANNEL = {
    "cinematic_boom": (
        "sine=frequency=60:duration=0.3,volume=0.4,"
        "adelay=100|100[a]"
    ),
    "typewriter_click": (
        "sine=frequency=800:duration=0.05,volume=0.15,"
        "adelay=50|50[a]"
    ),
    "tape_rewind": (
        "sine=frequency=300:duration=0.4,volume=0.2,"
        "adelay=200|200[a]"
    ),
}

COLOR_WORDS = {
    "weirdhistory": {
        "emphasis": {"king", "queen", "emperor", "empire", "died", "death", "killed", "war", "battle", "secret", "lost", "curse", "legend", "myth"},
        "highlight": {"&H00FFD700&"},
        "danger": {"&H00FF4444&"},
        "neutral": {"&H00FFFFFF&"},
    },
    "crimeledger": {
        "emphasis": {"money", "million", "billion", "dollars", "stolen", "fraud", "crime", "bank", "court", "guilty", "arrested", "prison"},
        "highlight": {"&H0000FF88&"},
        "danger": {"&H00FF4444&"},
        "neutral": {"&H00FFFFFF&"},
    },
    "mindtactics": {
        "emphasis": {"mind", "control", "manipulate", "fear", "gaslight", "narcissist", "trauma", "abuse", "power", "secret", "hidden", "dark"},
        "highlight": {"&H00FF2020&"},
        "danger": {"&H00FF0000&"},
        "neutral": {"&H00CCCCCC&"},
    },
}


def run(cmd, check=True):
    desc = " ".join(str(x) for x in cmd[:4])
    print(f"  >> {desc}...")
    r = subprocess.run([str(x) for x in cmd], capture_output=True, text=True)
    if check and r.returncode != 0:
        print(f"  ERR: {r.stderr[-400:]}")
        sys.exit(1)
    return r


def get_dur(p):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True
    )
    return float(r.stdout.strip())


def fix_audio(src, dst):
    run([
        "ffmpeg", "-y", "-i", str(src),
        "-af", "atrim=start=0.08,loudnorm=I=-14:TP=-1:LRA=11",
        "-ar", "44100", str(dst)
    ])


def ken_burns(src, dst, dur, idx):
    zs, ze = KB_PEAK if idx in PEAK_SCENES else KB_NORMAL
    frames = int(dur * FPS)
    zexpr = f"'if(eq(on,1),{zs},zoom+({ze}-{zs})/{frames})'"
    cfg = CHANNEL_CONFIGS.get(CHANNEL, CHANNEL_CONFIGS["weirdhistory"])
    color_grade = cfg["color_grade"]
    extra_vf = cfg["extra_vf"]
    run([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", (
            f"scale={W*2}:{H*2},"
            f"zoompan=z={zexpr}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={W}x{H}:fps={FPS},"
            f"scale={W}:{H},{color_grade},{extra_vf}"
        ),
        "-t", str(dur), "-an",
        "-preset", "fast", "-crf", "18", str(dst)
    ])


def make_ass(text, dur):
    words = text.split()
    if not words:
        return None
    tpw = dur / max(len(words), 1)
    color_cfg = COLOR_WORDS.get(CHANNEL, COLOR_WORDS["weirdhistory"])

    def ft(t):
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = t % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    def wc(w):
        wl = w.lower().strip(".,!?;:\"'-")
        if wl in color_cfg["danger"]:
            return color_cfg["danger"]
        if wl in color_cfg["emphasis"]:
            return color_cfg["highlight"]
        return color_cfg["neutral"]

    ass = "/tmp/subs.ass"
    mv = int(H * (1 - SUB_Y_PCT))
    style = (
        f"Style: Default,{FONT},{FONT_SIZE},&H00FFFFFF&,&H000000FF&,"
        f"&H00000000&,&H80000000&,-1,0,0,0,100,100,0,0,1,3,2,2,10,10,{mv},1"
    )
    lines = [
        "[Script Info]", "ScriptType: v4.00+",
        f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
        "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,"
        "ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding",
        style, "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    t = 0.0
    for w in words:
        c = wc(w)
        txt = f"{{\\c{c}}}{{\\be1}}{w}{{\\r}}"
        lines.append(
            f"Dialogue: 0,{ft(t)},{ft(t + tpw)},Default,,0,0,0,,{txt}"
        )
        t += tpw
    Path(ass).write_text("\n".join(lines), encoding="utf-8")
    return ass


def burn_subs(src, dst, text, dur):
    ass = make_ass(text, dur)
    if not ass:
        shutil.copy(src, dst)
        return
    run([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", f"ass={ass}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-an", str(dst)
    ])


def mix_music(voice, music, out, dur):
    sfx_key = CHANNEL_CONFIGS.get(CHANNEL, CHANNEL_CONFIGS["weirdhistory"])["sfx_cut"]
    sfx_filter = SFX_CHANNEL.get(sfx_key, "")
    mix_label = "[mix]"
    if sfx_filter:
        mix_label = "[sfxout]"
        run([
            "ffmpeg", "-y",
            "-i", str(voice),
            "-stream_loop", "-1", "-i", str(music),
            "-filter_complex",
            f"f,aevalsrc=0:duration={dur}:s=44100:c=2[null];"
            f"[1:a]volume=-24dB,atrim=0:{dur}[m];"
            f"[0:a][m]amix=inputs=2:duration=first:normalize=0,"
            f"loudnorm=I=-14:TP=-1:LRA=11{sfx_filter}",
            "-map", "[a]", "-ar", "44100", "-ac", "2",
            str(out)
        ])
    else:
        run([
            "ffmpeg", "-y",
            "-i", str(voice),
            "-stream_loop", "-1", "-i", str(music),
            "-filter_complex",
            f"[1:a]volume=-24dB,atrim=0:{dur}[m];"
            f"[0:a][m]amix=inputs=2:duration=first:normalize=0,"
            f"loudnorm=I=-14:TP=-1:LRA=11[a]",
            "-map", "[a]", "-ar", "44100", "-ac", "2",
            str(out)
        ])


def process_scene(idx, scene, wav, mp4, tmp):
    text = scene.get("narration", scene.get("text", ""))
    p = tmp / f"s{idx:02d}"
    wav_fix = Path(str(p) + "_fix.wav")
    fix_audio(wav, wav_fix)
    dur = get_dur(wav_fix)
    kb = Path(str(p) + "_kb.mp4")
    ken_burns(mp4, kb, dur, idx)
    sub = Path(str(p) + "_sub.mp4")
    burn_subs(kb, sub, text, dur)
    if MUSIC_FILE.exists():
        mix_a = Path(str(p) + "_mix.aac")
        mix_music(wav_fix, MUSIC_FILE, mix_a, dur)
        a_src = mix_a
    else:
        a_src = wav_fix
    out = Path(str(p) + "_wa.mp4")
    run([
        "ffmpeg", "-y", "-i", str(sub), "-i", str(a_src),
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(out)
    ])
    return out


def main():
    cfg = CHANNEL_CONFIGS.get(CHANNEL, CHANNEL_CONFIGS["weirdhistory"])
    print("=" * 56)
    print(f"  {CHANNEL.upper()} — {cfg['description']}")
    print("=" * 56)
    if not SCRIPT_FILE.exists():
        print(f"ERROR: {SCRIPT_FILE}")
        sys.exit(1)
    with open(SCRIPT_FILE, encoding="utf-8") as f:
        data = json.load(f)
    scenes = data if isinstance(data, list) else data.get("scenes", [])
    wavs = sorted(AUDIO_DIR.glob("*.wav"))
    footages = sorted(FOOTAGE_DIR.glob("*.mp4"))
    n = min(len(scenes), len(wavs), len(footages))
    print(f"Scenes: {n} | WAV: {len(wavs)} | MP4: {len(footages)}")
    if n == 0:
        print("ERROR: no files to process")
        sys.exit(1)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = Path("/tmp/omfactory")
    tmp.mkdir(exist_ok=True)
    done = []
    for i in range(n):
        sid = scenes[i].get("title", "")[:40]
        print(f"\n  == Scene {i+1}/{n}: {sid}")
        done.append(process_scene(i + 1, scenes[i], wavs[i], footages[i], tmp))
    cl = Path("/tmp/concat_factory.txt")
    cl.write_text("\n".join(f"file '{f.resolve()}'" for f in done))
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(cl),
        "-c:v", "libx264", "-preset", "medium",
        "-b:v", "35M", "-maxrate", "42M", "-bufsize", "70M",
        "-c:a", "aac", "-b:a", "320k",
        str(OUTPUT_FINAL)
    ])
    if OUTPUT_FINAL.exists():
        dur = get_dur(OUTPUT_FINAL)
        mb = OUTPUT_FINAL.stat().st_size / 1048576
        print(f"\n  OK: {OUTPUT_FINAL}")
        print(f"  Duration: {dur:.0f}s ({dur/60:.1f}min) | Size: {mb:.1f}MB | Bitrate: 35Mbps")
    else:
        print("\n  ERROR: output file not created")


if __name__ == "__main__":
    main()
