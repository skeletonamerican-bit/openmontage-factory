#!/usr/bin/env python3
"""
kaggle_setup.py

Best-effort Kaggle orchestration script.
- Reads KAGGLE_USERNAME / KAGGLE_KEY from .env
- Authenticates via Kaggle API (python package and CLI fallback)
- Creates a dataset containing all `projects/*/script.json`
- Uploads `kaggle_factory.ipynb` to the dataset (and attempts to push a kernel)
- Attempts to configure accelerator (best-effort) and start a run
- Polls status every 5 minutes and downloads outputs when available

Note: Kaggle remote execution and resource allocation are limited via Kaggle API; this script uses the kaggle CLI where needed and falls back to API calls.
"""

import os
import sys
import time
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
KAGGLE_USERNAME = os.getenv('KAGGLE_USERNAME')
KAGGLE_KEY = os.getenv('KAGGLE_KEY')

WORKDIR = Path.cwd()
DATASET_SLUG = f"openmontage/factory_assets_{int(time.time())}"
NOTEBOOK_PATH = WORKDIR / 'kaggle_factory.ipynb'
PROJECTS_DIR = WORKDIR / 'projects'


def check_prereqs():
    print("Checking environment prerequisites...")
    try:
        import kaggle
    except Exception:
        print("Kaggle python package not found. Will try CLI if available.")

    cli = shutil.which('kaggle')
    if not cli:
        print("Warning: 'kaggle' CLI not found. Some operations will be limited.")
    else:
        print(f"Found kaggle CLI at: {cli}")

    if not KAGGLE_USERNAME or not KAGGLE_KEY:
        print("KAGGLE_USERNAME or KAGGLE_KEY not found in environment. Please set them in .env or environment variables.")
        return False
    print("Kaggle credentials appear present in environment.")
    return True


def write_kaggle_json():
    # Write ~/.kaggle/kaggle.json
    kaggle_dir = Path.home() / '.kaggle'
    kaggle_dir.mkdir(parents=True, exist_ok=True)
    kaggle_json = kaggle_dir / 'kaggle.json'
    content = {"username": KAGGLE_USERNAME, "key": KAGGLE_KEY}
    kaggle_json.write_text(json.dumps(content))
    os.chmod(kaggle_json, 0o600)
    print(f"Wrote {kaggle_json}")


def collect_assets(tmpdir: Path):
    print("Collecting script.json files into dataset folder...")
    data_dir = tmpdir / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    found = []
    for proj in (PROJECTS_DIR).iterdir():
        if not proj.is_dir():
            continue
        s = proj / 'script.json'
        if s.exists():
            dest = data_dir / f"{proj.name}_script.json"
            shutil.copy(s, dest)
            found.append(dest)
    if not found:
        print("No script.json files found in projects/. Aborting dataset creation.")
        return None
    # also copy the notebook
    if NOTEBOOK_PATH.exists():
        shutil.copy(NOTEBOOK_PATH, tmpdir / NOTEBOOK_PATH.name)
    return tmpdir


def create_dataset(tmpdir: Path):
    print("Creating Kaggle dataset (best-effort)...")
    # Use kaggle CLI if available
    cli = shutil.which('kaggle')
    if cli:
        try:
            cmd = f"kaggle datasets create -p {str(tmpdir)} -u --title 'OpenMontage Factory Assets' --subtitle 'Auto-upload'"
            print(cmd)
            subprocess.run(cmd, shell=True, check=True)
            print("Dataset created via CLI.")
            return True
        except subprocess.CalledProcessError as e:
            print("kaggle datasets create failed:", e)
    # Fallback: attempt using kaggle API package
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()
        print("Authenticated with Kaggle API.")
        # API dataset creation requires a folder; use the CLI path instead if above failed.
        print("Kaggle API dataset create is not implemented in this script path. Please run 'kaggle datasets create -p <path>'.")
    except Exception as e:
        print("Kaggle API authentication failed:", e)
        return False
    return False


def push_notebook_as_kernel():
    cli = shutil.which('kaggle')
    if not cli:
        print("kaggle CLI not available; skipping kernel push.")
        return False
    if not NOTEBOOK_PATH.exists():
        print("kaggle_factory.ipynb not found; skipping kernel push.")
        return False
    try:
        cmd = f"kaggle kernels push -p {str(WORKDIR)}"
        print(f"Pushing kernel: {cmd}")
        subprocess.run(cmd, shell=True, check=True)
        print("Kernel pushed (check Kaggle website to run it with T4).")
        return True
    except subprocess.CalledProcessError as e:
        print("Kernel push failed:", e)
        return False


def monitor_and_download():
    print("Monitoring for output (best-effort placeholder)...")
    # In many Kaggle flows you run a Kernel/Notebook and then download outputs using 'kaggle kernels output <slug>'
    # Here we just poll for existence of potential output zips in /kaggle/working if run on Kaggle.
    elapsed = 0
    timeout = 60 * 60 * 6  # 6 hours
    while elapsed < timeout:
        # Look for artifact zips created by the notebook in working dir
        out_files = list((WORKDIR / 'output').glob('*.zip')) if (WORKDIR / 'output').exists() else []
        if out_files:
            print("Found output zips:")
            for f in out_files:
                print(f" - {f}")
            # Extract to projects
            for f in out_files:
                print(f"Extracting {f} to projects/")
                shutil.unpack_archive(str(f), str(WORKDIR / 'projects' / f.stem))
            return True
        print("No outputs yet. Sleeping 5 minutes...")
        time.sleep(300)
        elapsed += 300
    print("Monitor timeout reached.")
    return False


def main():
    if not check_prereqs():
        sys.exit(1)
    write_kaggle_json()
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        collected = collect_assets(tmpdir)
        if not collected:
            print("No assets to upload. Exiting.")
            return
        created = create_dataset(tmpdir)
        if not created:
            print("Dataset creation didn't complete automatically. You can run 'kaggle datasets create -p', then push the kernel manually.")
        pushed = push_notebook_as_kernel()
        if not pushed:
            print("Kernel push not completed. Please push the notebook via 'kaggle kernels push'.")
        # Start monitor (non-blocking best-effort)
        print("Starting monitor for outputs (this will block until outputs are found or timeout)...")
        monitor_and_download()

if __name__ == '__main__':
    main()
