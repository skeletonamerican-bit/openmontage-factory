import json, os, subprocess, sys, shutil, math
from pathlib import Path

CHANNEL = os.getenv("CHANNEL", "weirdhistory").strip().lower()
PROJECT_DIR = Path("projects") / CHANNEL
AUDIO_DIR = PROJECT_DIR / "audio"
FOOTAGE_DIR = PROJECT_DIR / "footage"
MUSIC_FILE = PROJECT_DIR / "music" / "background.mp3"
SCRIPT_FILE = PROJECT_DIR / "script.json"
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FINAL = OUTPUT_DIR / f"{CHANNEL}_final.mp4"

W, H, FPS = 1920, 1080, 30
FONT = "Arial-Bold"
FONT_SIZE = 58
SUB_Y = 880
SCENE_DUR = 15
PHOTO_DUR = 5.2
VIDEO_DUR = 5.2
XFADE_DUR = 0.3

CHANNEL_CONFIGS = {
    "weirdhistory": {
        "color_grade": (
            "eq=brightness=-0.05:contrast=1.35:saturation=0.55"
        ),
        "sfx_cut": "cinematic_boom",
        "description": "Archive Noir — deep black, amber gold, ink blue",
    },
    "crimeledger": {
        "color_grade": (
            "eq=brightness=-0.02:contrast=1.25:saturation=0.35"
        ),
        "sfx_cut": "thud_dry",
        "description": "Fincher Cold — cold blue teal, desaturated, forensic",
    },
    "mindtactics": {
        "color_grade": (
            "eq=contrast=1.45:brightness=-0.03,"
            "hue=s=0.15"
        ),
        "sfx_cut": "static_glitch",
        "description": "Analog Horror — monochrome, red accent, VHS static",
    },
}

SFX_CHANNEL = {
    "cinematic_boom": (
        "sine=frequency=60:duration=0.5,volume=0.3,"
        "afade=t=out:st=0.2:d=0.3,"
        "adelay=100|100[a]"
    ),
    "thud_dry": (
        "sine=frequency=80:duration=0.3,volume=0.5,"
        "afade=t=out:st=0.01:d=0.29,"
        "adelay=50|50[a]"
    ),
    "static_glitch": (
        "anoisesrc=d=0.3:c=white:r=44100:a=0.05,"
        "highpass=f=2000,volume=0.4,"
        "adelay=150|150[a]"
    ),
}

COLOR_WORDS = {
    "weirdhistory": {
        "emphasis": {"king", "queen", "emperor", "empire", "died", "death", "killed", "war", "battle", "secret", "lost", "curse", "legend", "myth"},
        "highlight": {"&H0000FFFF&"},
        "danger": {"&H00FF4444&"},
        "neutral": {"&H00FFFFFF&"},
    },
    "crimeledger": {
        "emphasis": {"money", "million", "billion", "dollars", "stolen", "fraud", "crime", "bank", "court", "guilty", "arrested", "prison"},
        "highlight": {"&H0000FFFF&"},
        "danger": {"&H00FF4444&"},
        "neutral": {"&H00FFFFFF&"},
    },
    "mindtactics": {
        "emphasis": {"mind", "control", "manipulate", "fear", "gaslight", "narcissist", "trauma", "abuse", "power", "secret", "hidden", "dark"},
        "highlight": {"&H0000FFFF&"},
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


def ken_burns_photo(src, dst, dur, ken_mode, cfg):
    frames = int(dur * FPS)
    color_grade = cfg["color_grade"]

    if ken_mode == "zoom_in":
        zexpr = "'min(zoom+0.0003,1.05)'"
        xexpr = "'iw/2-(iw/zoom/2)'"
        yexpr = "'ih/2-(ih/zoom/2)'"
    elif ken_mode == "pan_left":
        zexpr = "1.3"
        xexpr = f"'iw*0.15+iw*0.15*(1-on/{frames})'"
        yexpr = "'ih/2-(ih/zoom/2)'"
    elif ken_mode == "zoom_out":
        zexpr = "'if(eq(on,1),1.05,max(zoom-0.0003,1.0))'"
        xexpr = "'iw/2-(iw/zoom/2)'"
        yexpr = "'ih/2-(ih/zoom/2)'"
    elif ken_mode == "pan_right":
        zexpr = "1.3"
        xexpr = f"'iw*0.15*(on/{frames})'"
        yexpr = "'ih/2-(ih/zoom/2)'"
    else:
        zexpr = "'min(zoom+0.0003,1.05)'"
        xexpr = "'iw/2-(iw/zoom/2)'"
        yexpr = "'ih/2-(ih/zoom/2)'"

    run([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", (
            f"zoompan=z={zexpr}:x={xexpr}:y={yexpr}:"
            f"d={frames}:s={W}x{H}:fps={FPS},"
            f"{color_grade}"
        ),
        "-t", str(dur), "-pix_fmt", "yuv420p", "-an",
        "-preset", "fast", "-crf", "23", str(dst)
    ])


def prep_video_clip(src, dst, dur, cfg):
    if not src.exists():
        create_placeholder(dst, "missing video clip")
        return
    color_grade = cfg["color_grade"]
    src_dur = get_dur(src)
    loop = ""
    trim = ""
    if src_dur < dur and src_dur > 0:
        loop = f"-stream_loop -1"
        trim = f"-t {dur}"
    elif src_dur >= dur:
        trim = f"-t {dur}"
    cmd = ["ffmpeg", "-y"]
    if loop:
        cmd.extend(loop.split())
    cmd.extend(["-i", str(src)])
    vf = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps={FPS},{color_grade}"
    filter_parts = ["-vf", vf]
    if trim:
        filter_parts.extend(trim.split())
    cmd.extend(filter_parts)
    cmd.extend(["-pix_fmt", "yuv420p", "-an", "-preset", "fast", "-crf", "23", str(dst)])
    run(cmd)


def create_placeholder(dst, text):
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:d={VIDEO_DUR}",
        "-vf", f"drawtext=text='{text[:80]}':fontcolor=white:fontsize=28:x=(w-text_w)/2:y=(h-text_h)/2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
        str(dst)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except Exception as e:
        print(f"  Placeholder failed: {e}")


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

    ass = f"/tmp/subs_{CHANNEL}.ass"
    mv = H - SUB_Y
    style = (
        f"Style: Default,{FONT},{FONT_SIZE},&H00FFFFFF&,&H000000FF&,"
        f"&H00000000&,&H80000000&,-1,0,0,0,100,100,0,0,1,3,6,2,10,10,{mv},1"
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
        txt = f"{{\\c{c}}}{w}{{\\r}}"
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


def synthesize_sfx(sfx_name):
    sfx_dir = Path("/tmp/omfactory/sfx")
    sfx_dir.mkdir(parents=True, exist_ok=True)
    sfx_file = sfx_dir / f"{sfx_name}.wav"
    if sfx_file.exists():
        return sfx_file

    specs = {
        "cinematic_boom": (
            "-f", "lavfi", "-i", "sine=frequency=60:duration=0.5",
            "-af", "afade=t=out:st=0.2:d=0.3,volume=0.3"
        ),
        "thud_dry": (
            "-f", "lavfi", "-i", "sine=frequency=80:duration=0.3",
            "-af", "afade=t=out:st=0.01:d=0.29,volume=0.5"
        ),
        "static_glitch": (
            "-f", "lavfi", "-i", "anoisesrc=d=0.3:c=white:r=44100:a=0.05",
            "-af", "highpass=f=2000,volume=0.4"
        ),
    }
    spec = specs.get(sfx_name)
    if not spec:
        return None
    cmd = ["ffmpeg", "-y"] + list(spec) + ["-ar", "44100", "-ac", "2", str(sfx_file)]
    run(cmd)
    return sfx_file


def mix_scene_audio(voice, music, out, dur, scene_idx):
    cfg = CHANNEL_CONFIGS.get(CHANNEL, CHANNEL_CONFIGS["weirdhistory"])
    sfx_key = cfg["sfx_cut"]

    sfx_cut = synthesize_sfx(sfx_key)

    voice_norm = Path(str(out) + "_voice_norm.wav")
    run([
        "ffmpeg", "-y", "-i", str(voice),
        "-af", f"loudnorm=I=-16:TP=-1:LRA=7,atrim=0:{dur},apad=whole_dur={dur}",
        "-ar", "44100", "-ac", "2", str(voice_norm)
    ])

    if music and music.exists():
        music_trim = Path(str(out) + "_music_trim.wav")
        run([
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(music),
            "-af", f"volume=-28dB,atrim=0:{dur}",
            "-ar", "44100", "-ac", "2", str(music_trim)
        ])
        music_src = music_trim
    else:
        music_src = None

    sfx_start = Path(str(out) + "_sfx_start.wav")
    if sfx_cut and sfx_cut.exists():
        run([
            "ffmpeg", "-y", "-i", str(sfx_cut),
            "-af", "volume=-24dB",
            "-ar", "44100", str(sfx_start)
        ])
    else:
        sfx_start = None

    if music_src and sfx_start:
        run([
            "ffmpeg", "-y",
            "-i", str(voice_norm),
            "-i", str(music_src),
            "-i", str(sfx_start),
            "-filter_complex",
            f"[1:a]volume=0.15[music_d];"
            f"[0:a][music_d]amix=inputs=2:duration=first:weights=1 1[voice_mix];"
            f"[voice_mix][2:a]amix=inputs=2:duration=first:weights=1 0.3[a]",
            "-map", "[a]", "-ar", "44100", "-ac", "2",
            str(out)
        ])
    elif music_src:
        run([
            "ffmpeg", "-y",
            "-i", str(voice_norm),
            "-i", str(music_src),
            "-filter_complex",
            f"[1:a]volume=0.15[music_d];"
            f"[0:a][music_d]amix=inputs=2:duration=first:weights=1 1[a]",
            "-map", "[a]", "-ar", "44100", "-ac", "2",
            str(out)
        ])
    else:
        shutil.copy(voice_norm, out)

    for f in [voice_norm, music_src] if music_src else [voice_norm]:
        if f and f.exists():
            try:
                f.unlink()
            except:
                pass


def fix_audio(src, dst, target_dur):
    run([
        "ffmpeg", "-y", "-i", str(src),
        "-af", f"atrim=start=0.08:duration={target_dur},loudnorm=I=-16:TP=-1:LRA=7,apad=whole_dur={target_dur}",
        "-ar", "44100", str(dst)
    ])


def get_ken_burns_modes(scene_idx):
    modes = ["zoom_in", "pan_left", "zoom_out", "pan_right"]
    a = modes[scene_idx % 4]
    b = modes[(scene_idx + 1) % 4]
    return a, b


def process_scene(idx, scene, wav, tmp):
    text = scene.get("narration", scene.get("text", ""))
    p = tmp / f"s{idx:02d}"
    cfg = CHANNEL_CONFIGS.get(CHANNEL, CHANNEL_CONFIGS["weirdhistory"])

    # Ken Burns modes cycle by scene index
    kb_a, kb_b = get_ken_burns_modes(idx)

    photo1 = FOOTAGE_DIR / f"s{idx:03d}_photo1.jpg"
    photo2 = FOOTAGE_DIR / f"s{idx:03d}_photo2.jpg"
    video = FOOTAGE_DIR / f"s{idx:03d}_video.mp4"

    # Clip 1: LTX-Video (5.2s)
    vclip = Path(str(p) + "_vclip.mp4")
    if video.exists():
        prep_video_clip(video, vclip, VIDEO_DUR, cfg)
    else:
        create_placeholder(vclip, f"[{CHANNEL}] Video scene {idx}")

    # Clip 2: SANA photo 1 + Ken Burns A (5.2s)
    kb1 = Path(str(p) + "_kb1.mp4")
    if photo1.exists():
        ken_burns_photo(photo1, kb1, PHOTO_DUR, kb_a, cfg)
    else:
        create_placeholder(kb1, f"[{CHANNEL}] Photo1 scene {idx}")

    # Clip 3: SANA photo 2 + Ken Burns B (5.2s)
    kb2 = Path(str(p) + "_kb2.mp4")
    if photo2.exists():
        ken_burns_photo(photo2, kb2, PHOTO_DUR, kb_b, cfg)
    else:
        create_placeholder(kb2, f"[{CHANNEL}] Photo2 scene {idx}")

    # Crossfade concat: video → xfade → photo1 → xfade → photo2
    # offset1 = VIDEO_DUR - XFADE_DUR
    # After first xfade: total = 2*clip_dur - XFADE_DUR
    # offset2 = total - XFADE_DUR = 2*clip_dur - 2*XFADE_DUR
    offset1 = VIDEO_DUR - XFADE_DUR
    offset2 = 2 * VIDEO_DUR - 2 * XFADE_DUR

    concat_raw = Path(str(p) + "_concat.mp4")
    run([
        "ffmpeg", "-y",
        "-i", str(vclip),
        "-i", str(kb1),
        "-i", str(kb2),
        "-filter_complex",
        f"[0:v]xfade=transition=fade:duration={XFADE_DUR}:offset={offset1}[t0];"
        f"[t0][2:v]xfade=transition=fade:duration={XFADE_DUR}:offset={offset2}[video]",
        "-map", "[video]",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-an", str(concat_raw)
    ])

    # Subtitles
    sub = Path(str(p) + "_sub.mp4")
    burn_subs(concat_raw, sub, text, SCENE_DUR)

    # Audio mix: TTS -16 LUFS, music -28 LUFS ducked, SFX at joints
    mix_a = Path(str(p) + "_mix.aac")
    music = MUSIC_FILE if MUSIC_FILE.exists() else None
    mix_scene_audio(wav, music, mix_a, SCENE_DUR, idx)

    out = Path(str(p) + "_wa.mp4")
    run([
        "ffmpeg", "-y", "-i", str(sub), "-i", str(mix_a),
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(out)
    ])

    for f in [kb1, kb2, vclip, concat_raw, sub, mix_a]:
        if f and f.exists():
            try:
                f.unlink()
            except:
                pass
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
    n = min(len(scenes), len(wavs))
    print(f"Scenes: {n} | WAV: {len(wavs)} | Each scene: {SCENE_DUR}s")
    if n == 0:
        print("ERROR: no files to process")
        sys.exit(1)
    tmp = Path(f"/tmp/omfactory/{CHANNEL}")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    done = []
    for i in range(n):
        sid = scenes[i].get("title", str(scenes[i].get("id", "")))[:40]
        print(f"\n  == Scene {i+1}/{n}: {sid}")
        done.append(process_scene(i, scenes[i], wavs[i], tmp))

    cl = Path(f"/tmp/concat_factory_{CHANNEL}.txt")
    cl.write_text("\n".join(f"file '{f.resolve()}'" for f in done))
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(cl),
        "-c:v", "libx264", "-preset", "slow",
        "-crf", "18", "-b:v", "35M", "-maxrate", "42M", "-bufsize", "70M",
        "-c:a", "aac", "-b:a", "192k",
        "-r", "30", "-s", "1920x1080",
        "-movflags", "+faststart",
        str(OUTPUT_FINAL)
    ])
    if OUTPUT_FINAL.exists():
        dur = get_dur(OUTPUT_FINAL)
        mb = OUTPUT_FINAL.stat().st_size / 1048576
        print(f"\n  OK: {OUTPUT_FINAL}")
        print(f"  Duration: {dur:.0f}s ({dur/60:.1f}min) | Size: {mb:.1f}MB | Bitrate: 35Mbps | Profile: slow, CRF 18")
    else:
        print("\n  ERROR: output file not created")


if __name__ == "__main__":
    main()
