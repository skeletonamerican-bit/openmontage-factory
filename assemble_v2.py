import json,os,subprocess,sys,shutil
from pathlib import Path

CHANNEL=os.getenv("CHANNEL","twistedtruths")
PROJECT_DIR=Path("projects")/CHANNEL
AUDIO_DIR=PROJECT_DIR/"audio"
FOOTAGE_DIR=PROJECT_DIR/"footage"
MUSIC_FILE=PROJECT_DIR/"music/background.mp3"
SCRIPT_FILE=PROJECT_DIR/"script.json"
OUTPUT_DIR=PROJECT_DIR/"render"
OUTPUT_V2=OUTPUT_DIR/"FINAL_v3.mp4"
FONT="DejaVuSans-Bold"
FONT_SIZE=72
SUB_Y_PCT=0.82
YELLOW_WORDS={"money","million","billion","contract","company","deal","profit","loss","fund","salary","bonus","equity"}
RED_WORDS={"fired","stolen","betrayed","fraud","bankrupt","dead","murder","arrested","convicted","forgery","trap","secret"}
KB_NORMAL=("1.00","1.05")
KB_PEAK=("1.12","1.00")
PEAK_SCENES={4,8,12}
W,H,FPS=1920,1080,30

def run(cmd):
    print(f"▶ {' '.join(str(x) for x in cmd[:5])}...")
    r=subprocess.run([str(x) for x in cmd],capture_output=True,text=True)
    if r.returncode!=0:
        print("ERR:",r.stderr[-600:])
        sys.exit(1)
    return r

def get_dur(p):
    r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(p)],capture_output=True,text=True)
    return float(r.stdout.strip())

def fix_audio(src,dst):
    run(["ffmpeg","-y","-i",src,
         "-af","atrim=start=0.1,loudnorm=I=-14:TP=-1:LRA=11",
         "-ar","44100",dst])

def ken_burns(src,dst,dur,idx):
    zs,ze=KB_PEAK if idx in PEAK_SCENES else KB_NORMAL
    frames=int(dur*FPS)
    zexpr=f"'if(eq(on,1),{zs},zoom+({ze}-{zs})/{frames})'"
    # LUT: S-curve + небольшой буст насыщенности
    color_grade="curves=all='0/0 0.5/0.47 1/0.95',eq=saturation=1.15:contrast=1.08:brightness=-0.02"
    run(["ffmpeg","-y","-i",src,
         "-vf",f"scale={W*2}:{H*2},zoompan=z={zexpr}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},scale={W}:{H},{color_grade}",
         "-t",str(dur),"-an","-preset","fast","-crf","18",dst])

def make_ass(text,dur):
    words=text.split()
    if not words: return None
    tpw=dur/max(len(words),1)
    def ft(t):
        h=int(t//3600);m=int((t%3600)//60);s=t%60
        return f"{h}:{m:02d}:{s:05.2f}"
    def wc(w):
        wl=w.lower().strip(".,!?;:")
        if wl in RED_WORDS: return "&H3333FF&"
        if wl in YELLOW_WORDS: return "&H00CCFF&"
        return "&H00FFFFFF&"
    ass="/tmp/subs.ass"
    mv=int(H*(1-SUB_Y_PCT))
    # ASS формат: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,
    #             Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,
    #             BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
    style=f"Style: Default,{FONT},{FONT_SIZE},&H00FFFFFF&,&H000000FF&,&H00000000&,&H80000000&,-1,0,0,0,100,100,0,0,1,3,2,2,10,10,{mv},1"
    lines=[
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {W}",
        f"PlayResY: {H}",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        style,
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    t=0.0
    for w in words:
        c=wc(w)
        txt=f"{{\\c{c}}}{{\\be1}}{w}{{\\r}}"
        lines.append(f"Dialogue: 0,{ft(t)},{ft(t+tpw)},Default,,0,0,0,,{txt}")
        t+=tpw
    Path(ass).write_text("\n".join(lines),encoding="utf-8")
    return ass

def burn_subs(src,dst,text,dur):
    ass=make_ass(text,dur)
    if not ass: shutil.copy(src,dst); return
    run(["ffmpeg","-y","-i",src,
         "-vf",f"ass={ass}",
         "-c:v","libx264","-preset","fast","-crf","18","-an",dst])

def mix_music(voice,music,out,dur):
    run(["ffmpeg","-y",
         "-i",str(voice),
         "-stream_loop","-1","-i",str(music),
         "-filter_complex",
         f"[1:a]volume=-24dB,atrim=0:{dur}[m];[0:a][m]amix=inputs=2:duration=first[a]",
         "-map","[a]","-ar","44100","-ac","2",str(out)])

def process_scene(idx,scene,wav,mp4,tmp):
    text=scene.get("narration",scene.get("text",""))
    p=tmp/f"s{idx:02d}"
    wav_fix=Path(str(p)+"_fix.wav")
    fix_audio(wav,wav_fix)
    dur=get_dur(wav_fix)
    kb=Path(str(p)+"_kb.mp4")
    ken_burns(mp4,kb,dur,idx)
    sub=Path(str(p)+"_sub.mp4")
    burn_subs(kb,sub,text,dur)
    if MUSIC_FILE.exists():
        mix_a=Path(str(p)+"_mix.aac")
        mix_music(wav_fix,MUSIC_FILE,mix_a,dur)
        a_src=mix_a
    else:
        a_src=wav_fix
    out=Path(str(p)+"_wa.mp4")
    run(["ffmpeg","-y","-i",str(sub),"-i",str(a_src),
         "-c:v","copy","-c:a","aac","-shortest",str(out)])
    return out

def main():
    print("="*50)
    if not SCRIPT_FILE.exists(): print("❌ Нет script.json"); sys.exit(1)
    with open(SCRIPT_FILE,encoding="utf-8") as f: data=json.load(f)
    scenes=data if isinstance(data,list) else data.get("scenes",data.get("script",[]))
    wavs=sorted(AUDIO_DIR.glob("*.wav"))
    footages=sorted(FOOTAGE_DIR.glob("*.mp4"))
    n=min(len(scenes),len(wavs),len(footages))
    print(f"Сцен: {n} | WAV: {len(wavs)} | MP4: {len(footages)}")
    if n==0: print("❌ Нет файлов"); sys.exit(1)
    OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
    tmp=Path("/tmp/omv3"); tmp.mkdir(exist_ok=True)
    done=[]
    for i in range(n):
        print(f"\n── Сцена {i+1}/{n}")
        done.append(process_scene(i+1,scenes[i],wavs[i],footages[i],tmp))
    cl=Path("/tmp/cl.txt")
    cl.write_text("\n".join(f"file '{f.resolve()}'" for f in done))
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(cl),
         "-c:v","libx264","-preset","fast","-crf","18","-c:a","aac",str(OUTPUT_V2)])
    dur=get_dur(OUTPUT_V2)
    mb=OUTPUT_V2.stat().st_size/1048576
    print(f"\n✅ {OUTPUT_V2}\n⏱ {dur:.0f}s ({dur/60:.1f}мин) | 💾 {mb:.1f}MB")

if __name__=="__main__": main()
