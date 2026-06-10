import base64, json, os, urllib.request, sys, time

TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO  = "skeletonamerican-bit/openmontage-factory"

GENERATE_TTS = '''import json,os,subprocess,sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def load_script(channel):
    p = ROOT/"projects"/channel/"script.json"
    if not p.exists(): sys.exit(f"ERROR: {p}")
    return json.loads(p.read_text(encoding="utf-8"))

def try_kokoro(text, out_path):
    try:
        import kokoro, soundfile as sf, numpy as np
        pipeline = kokoro.KPipeline(lang_code="a")
        chunks = []
        for _,_,audio in pipeline(text, voice="af_heart", speed=1.0):
            chunks.append(audio)
        if chunks:
            sf.write(str(out_path), np.concatenate(chunks), 24000)
            return True
    except Exception as e:
        print(f"  Kokoro failed: {e}")
    return False

def try_espeak(text, out_path):
    try:
        subprocess.run(
            ["espeak","-w",str(out_path),"-s","145","-p","45","-a","180",text],
            check=True, capture_output=True, timeout=60)
        return True
    except Exception as e:
        print(f"  espeak failed: {e}")
    return False

def normalize(src, dst):
    subprocess.run([
        "ffmpeg","-y","-i",str(src),
        "-af","atrim=start=0.08,loudnorm=I=-14:TP=-1:LRA=11",
        "-ar","44100",str(dst)
    ], capture_output=True, check=True, timeout=120)

def main():
    channel = os.getenv("CHANNEL","").strip()
    if not channel: sys.exit("ERROR: CHANNEL not set")
    script  = load_script(channel)
    out_dir = ROOT/"projects"/channel/"audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    kokoro_ok = False
    try:
        import kokoro, soundfile, numpy
        kokoro_ok = True
        print("TTS: Kokoro-82M")
    except:
        print("TTS: espeak")
    for scene in script.get("scenes",[]):
        sid  = scene.get("id")
        text = str(scene.get("narration","")).strip()
        if not sid or not text: continue
        final = out_dir/f"{sid}.wav"
        if final.exists(): print(f"  Skip {sid}"); continue
        print(f"  Scene {sid}...")
        tmp = out_dir/f"{sid}_raw.wav"
        ok = (try_kokoro(text,tmp) if kokoro_ok else False) or try_espeak(text,tmp)
        if not ok: continue
        normalize(tmp, final)
        tmp.unlink(missing_ok=True)
        print(f"  OK {final.name}")

if __name__=="__main__": main()
'''

GENERATE_SCRIPT = '''import json,os,sys,urllib.request,urllib.error
from pathlib import Path

API_URL = "https://models.inference.ai.azure.com/chat/completions"
MODEL   = "gpt-oss-120b"

CONFIGS = {
    "weirdhistory":  {"style":"gothic dark academia","tone":"dramatic, suspenseful","scenes":25,"duration_min":25},
    "crimeledger":   {"style":"financial crime documentary","tone":"investigative, shocking","scenes":16,"duration_min":18},
    "mindtactics":   {"style":"dark psychology","tone":"analytical, unsettling","scenes":12,"duration_min":12},
}

PROMPT = """You are elite YouTube documentary scriptwriter like MagnatesMedia.
Style: {style}, Topic: {topic}, Tone: {tone}
Write {scenes} scenes (~{duration_min} min, 65-80 words per narration).
RULES:
1. Scene 1: SHOCKING hook with specific numbers/names/dates
2. Every 3 scenes: micro-twist ("But they didnt know...")
3. Use SPECIFIC details: exact amounts, real names, dates
4. Last scene: moral + "Subscribe to never miss a story like this"
Structure: Hook->Origin->Rise->Betrayal->Unravels->Consequences->CTA
Return ONLY JSON no markdown:
{{"title":"","description":"","tags":[],"scenes":[{{"id":1,"title":"","narration":"","visual":"","duration_seconds":65,"emotion":""}}]}}"""

def main():
    token = os.environ.get("GITHUB_TOKEN","").strip()
    if not token: print("ERROR: GITHUB_TOKEN not set"); sys.exit(1)
    ch    = os.environ.get("CHANNEL","weirdhistory").lower().strip()
    topic = os.environ.get("TOPIC","The Corporate Betrayal")
    cfg   = CONFIGS.get(ch, CONFIGS["weirdhistory"])
    print(f"Channel:{ch} | Scenes:{cfg[chr(39)+'scenes'+chr(39)]} | Model:{MODEL}")
    prompt  = PROMPT.format(topic=topic,**cfg)
    payload = json.dumps({"model":MODEL,"messages":[{"role":"user","content":prompt}],"max_tokens":6000,"temperature":0.88}).encode()
    req = urllib.request.Request(API_URL,data=payload,method="POST")
    req.add_header("Authorization",f"Bearer {token}")
    req.add_header("Content-Type","application/json")
    try:
        with urllib.request.urlopen(req,timeout=180) as r:
            text=json.loads(r.read())["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        print(f"ERROR HTTP {e.code}: {e.read().decode()[:300]}"); sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}"); sys.exit(1)
    if text.startswith("```"):
        text=text.split("\n",1)[-1].rsplit("```",1)[0].strip()
    try: data=json.loads(text)
    except:
        s=text.find("{");e=text.rfind("}")+1
        data=json.loads(text[s:e])
    out=Path(f"projects/{ch}")
    out.mkdir(parents=True,exist_ok=True)
    with open(out/"script.json","w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)
    print(f"OK: {len(data.get(chr(39)+'scenes'+chr(39),[]))} scenes | {data.get(chr(39)+'title'+chr(39),chr(39)+chr(39))[:60]}")

if __name__=="__main__": main()
'''

print("Part 1 loaded OK")

ASSEMBLE_V2 = r'''import json,os,subprocess,sys,shutil,urllib.request
from pathlib import Path

CHANNEL     = os.getenv("CHANNEL","weirdhistory")
PROJECT_DIR = Path("projects")/CHANNEL
AUDIO_DIR   = PROJECT_DIR/"audio"
FOOTAGE_DIR = PROJECT_DIR/"footage"
MUSIC_FILE  = PROJECT_DIR/"music/background.mp3"
SCRIPT_FILE = PROJECT_DIR/"script.json"
OUTPUT_DIR  = PROJECT_DIR/"render"
OUTPUT_V3   = OUTPUT_DIR/"FINAL_v3.mp4"
TMP         = Path("/tmp/omv4")

FONT="DejaVuSans-Bold"; FONT_SIZE=76; SUB_Y_PCT=0.82
YELLOW_WORDS={"money","million","billion","contract","company","deal","profit","loss","fund","salary","bonus","equity","cash","shares","wealth"}
RED_WORDS={"fired","stolen","betrayed","fraud","bankrupt","dead","murder","arrested","convicted","forgery","trap","secret","lied","exposed","scandal","corrupt"}
KB_NORMAL=("1.00","1.05"); KB_PEAK=("1.12","1.00"); PEAK_SCENES={3,6,9,12,15}
W,H,FPS=1920,1080,30

SFX_URLS={
    "riser":"https://freesound.org/data/previews/415/415510_5121236-lq.mp3",
    "impact":"https://freesound.org/data/previews/398/398937_7594403-lq.mp3",
}

def run(cmd,check=True):
    print(f"  ▶ {' '.join(str(x) for x in cmd[:4])}...")
    r=subprocess.run([str(x) for x in cmd],capture_output=True,text=True)
    if check and r.returncode!=0: print("ERR:",r.stderr[-300:]); sys.exit(1)
    return r

def get_dur(p):
    r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(p)],capture_output=True,text=True)
    return float(r.stdout.strip())

def download_sfx():
    d=TMP/"sfx"; d.mkdir(parents=True,exist_ok=True)
    paths={}
    for name,url in SFX_URLS.items():
        dst=d/f"{name}.mp3"
        if not dst.exists():
            try: urllib.request.urlretrieve(url,dst); print(f"  SFX {name} OK")
            except: dst=None
        paths[name]=dst if dst and Path(dst).exists() else None
    return paths

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
    ass="/tmp/subs_v4.ass"; mv=int(H*(1-SUB_Y_PCT))
    style=f"Style: Default,{FONT},{FONT_SIZE},&H00FFFFFF&,&H000000FF&,&H00000000&,&H90000000&,-1,0,0,0,100,100,0,0,1,3,2,2,10,10,{mv},1"
    lines=["[Script Info]","ScriptType: v4.00+",f"PlayResX: {W}",f"PlayResY: {H}","WrapStyle: 0","",
           "[V4+ Styles]","Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
           style,"","[Events]","Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]
    t=0.0
    for w in words:
        c=wc(w); txt=f"{{\\c{c}}}{{\\be1}}{w}{{\\r}}"
        lines.append(f"Dialogue: 0,{ft(t)},{ft(t+tpw)},Default,,0,0,0,,{txt}")
        t+=tpw
    Path(ass).write_text("\n".join(lines),encoding="utf-8")
    return ass

def ken_burns(src,dst,dur,idx):
    zs,ze=KB_PEAK if idx in PEAK_SCENES else KB_NORMAL
    frames=int(dur*FPS)
    zexpr=f"'if(eq(on,1),{zs},zoom+({ze}-{zs})/{frames})'"
    cgrade="curves=all='0/0 0.5/0.47 1/0.95',eq=saturation=1.18:contrast=1.08:brightness=-0.02"
    run(["ffmpeg","-y","-i",src,"-vf",
         f"scale={W*2}:{H*2},zoompan=z={zexpr}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},scale={W}:{H},{cgrade}",
         "-t",str(dur),"-an","-preset","fast","-crf","20",dst])

def mix_audio(voice,music,sfx_paths,out,dur,idx,total):
    inputs=["-i",str(voice)]; n=1; filters=[]
    if music and Path(music).exists():
        inputs+=["-stream_loop","-1","-i",str(music)]
        filters.append(f"[1:a]volume=-22dB,atrim=0:{dur}[m]")
        filters.append(f"[0:a][m]sidechaincompress=threshold=0.02:ratio=8:attack=5:release=200[md]")
        mix="[0:a][md]"; n=2
    else:
        mix="[0:a]"; n=1
    sfx=None
    if idx in PEAK_SCENES and sfx_paths.get("riser"):
        inputs+=["-i",str(sfx_paths["riser"])]
        si=len(inputs)//2-1
        filters.append(f"[{si}:a]volume=-18dB,atrim=0:3[sfx]")
        mix+=("[md]" if n==2 else "[0:a]").replace("[md]","[md][sfx]") if n==2 else "[0:a][sfx]"
        n+=1
    elif idx==total and sfx_paths.get("impact"):
        inputs+=["-i",str(sfx_paths["impact"])]
        si=len(inputs)//2-1
        filters.append(f"[{si}:a]volume=-12dB,atrim=0:2[sfx]")
        n+=1
    mix_inputs="[0:a][md]" if n>=2 and "md" in "".join(filters) else "[0:a]"
    if n>2: mix_inputs+="[sfx]"
    filters.append(f"{mix_inputs}amix=inputs={n}:duration=first:normalize=0[aout]")
    run(["ffmpeg","-y"]+inputs+["-filter_complex",";".join(filters),"-map","[aout]","-ar","44100","-ac","2",str(out)])

def process_scene(idx,scene,wav,mp4,sfx,total,tmp):
    text=scene.get("narration",scene.get("text",""))
    p=tmp/f"s{idx:02d}"
    wf=Path(str(p)+"_fix.wav")
    run(["ffmpeg","-y","-i",str(wav),"-af","atrim=start=0.05,loudnorm=I=-14:TP=-1:LRA=11","-ar","44100",str(wf)])
    dur=get_dur(wf)
    kb=Path(str(p)+"_kb.mp4"); ken_burns(mp4,kb,dur,idx)
    sub=Path(str(p)+"_sub.mp4")
    ass=make_ass(text,dur)
    if ass: run(["ffmpeg","-y","-i",str(kb),"-vf",f"ass={ass}","-c:v","libx264","-preset","fast","-crf","20","-an",str(sub)])
    else: shutil.copy(kb,sub)
    ma=Path(str(p)+"_mix.aac")
    mix_audio(wf,MUSIC_FILE,sfx,ma,dur,idx,total)
    out=Path(str(p)+"_final.mp4")
    run(["ffmpeg","-y","-i",str(sub),"-i",str(ma),"-c:v","copy","-c:a","aac","-shortest",str(out)])
    return out

def main():
    print("="*50+"\n  FORTS DIGITAL v4 — 10/10 mode\n"+"="*50)
    if not SCRIPT_FILE.exists(): print(f"ERROR: {SCRIPT_FILE}"); sys.exit(1)
    with open(SCRIPT_FILE,encoding="utf-8") as f: data=json.load(f)
    scenes=data if isinstance(data,list) else data.get("scenes",[])
    wavs=sorted(AUDIO_DIR.glob("*.wav")); footages=sorted(FOOTAGE_DIR.glob("*.mp4"))
    n=min(len(scenes),len(wavs),len(footages))
    if n==0: print("ERROR: no files"); sys.exit(1)
    print(f"Scenes:{n} WAV:{len(wavs)} MP4:{len(footages)}")
    OUTPUT_DIR.mkdir(parents=True,exist_ok=True); TMP.mkdir(exist_ok=True)
    sfx=download_sfx(); done=[]
    for i in range(n):
        print(f"\n── Scene {i+1}/{n}: {scenes[i].get('title','')[:40]}")
        done.append(process_scene(i+1,scenes[i],wavs[i],footages[i],sfx,n,TMP))
    cl=Path("/tmp/concat_v4.txt")
    cl.write_text("\n".join(f"file '{f.resolve()}'" for f in done))
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(cl),
         "-c:v","libx264","-preset","medium","-b:v","8000k",
         "-maxrate","10000k","-bufsize","20000k",
         "-c:a","aac","-b:a","192k",str(OUTPUT_V3)])
    dur=get_dur(OUTPUT_V3); mb=OUTPUT_V3.stat().st_size/1048576
    print(f"\n✅ FINAL_v3.mp4 | {dur:.0f}s ({dur/60:.1f}min) | {mb:.1f}MB")

if __name__=="__main__": main()
'''

WORKFLOW='''name: Make Video Factory

on:
  workflow_dispatch:
    inputs:
      channel:
        description: "Channel"
        required: true
        default: "weirdhistory"
      topic:
        description: "Topic (empty=auto)"
        required: false
        default: ""
  schedule:
    - cron: "0 3 * * 1,3,5"

jobs:
  build_video:
    runs-on: ubuntu-latest
    timeout-minutes: 180
    permissions:
      contents: write

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh && echo "$HOME/.local/bin" >> $GITHUB_PATH

      - name: Install system deps
        run: |
          sudo apt-get update -q
          sudo apt-get install -y ffmpeg espeak espeak-data libespeak1 libsndfile1

      - name: Install Python deps
        run: uv pip install --system --no-cache requests kokoro soundfile numpy

      - name: Select topic
        id: select_topic
        run: python scripts/select_topic.py
        env:
          CHANNEL: ${{ github.event.inputs.channel || 'weirdhistory' }}
          TOPIC: ${{ github.event.inputs.topic || '' }}

      - name: Generate script
        run: python scripts/generate_script.py
        env:
          GITHUB_TOKEN: ${{ secrets.GH_MODELS_TOKEN }}
          CHANNEL: ${{ steps.select_topic.outputs.CHANNEL }}
          TOPIC: ${{ steps.select_topic.outputs.TOPIC }}

      - name: Generate AI assets
        run: python scripts/generate_assets.py
        env:
          CHANNEL: ${{ steps.select_topic.outputs.CHANNEL }}

      - name: Generate TTS
        run: python scripts/generate_tts.py
        env:
          CHANNEL: ${{ steps.select_topic.outputs.CHANNEL }}

      - name: Assemble video
        run: python assemble_v2.py
        env:
          CHANNEL: ${{ steps.select_topic.outputs.CHANNEL }}

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: video-${{ steps.select_topic.outputs.CHANNEL }}-${{ github.run_id }}
          path: projects/*/render/FINAL_v3.mp4
          retention-days: 7

      - name: Send to Telegram
        if: always()
        run: python scripts/notify_telegram.py
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          CHANNEL: ${{ steps.select_topic.outputs.CHANNEL }}
          TOPIC: ${{ steps.select_topic.outputs.TOPIC }}
          RUN_ID: ${{ github.run_id }}
          STATUS: ${{ job.status }}
        continue-on-error: true
'''

FILES={
    "scripts/generate_tts.py":          GENERATE_TTS,
    "scripts/generate_script.py":       GENERATE_SCRIPT,
    "assemble_v2.py":                   ASSEMBLE_V2,
    ".github/workflows/make_video.yml": WORKFLOW,
}

def get_sha(path):
    req=urllib.request.Request(f"https://api.github.com/repos/{REPO}/contents/{path}")
    req.add_header("Authorization",f"token {TOKEN}")
    try:
        with urllib.request.urlopen(req) as r: return json.loads(r.read()).get("sha")
    except: return None

def upload(path,content):
    sha=get_sha(path)
    body={"message":"feat: 10/10 pipeline upgrade","content":base64.b64encode(content.encode()).decode()}
    if sha: body["sha"]=sha
    req=urllib.request.Request(f"https://api.github.com/repos/{REPO}/contents/{path}",data=json.dumps(body).encode(),method="PUT")
    req.add_header("Authorization",f"token {TOKEN}")
    req.add_header("Content-Type","application/json")
    with urllib.request.urlopen(req) as r: print(f"  ✅ {path}")
    time.sleep(0.4)

print("="*50)
print("  FORTS DIGITAL — Pipeline Upgrade 10/10")
print("="*50)
for path,content in FILES.items():
    upload(path,content)
print(f"\nГотово! github.com/{REPO}/actions")
