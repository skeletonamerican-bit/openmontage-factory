#!/bin/bash
set -euo pipefail

echo "=== TWISTED TRUTHS FACTORY ==="

echo "Step 1: Setup Kaggle..."
python3 kaggle_setup.py || true

echo "Step 2: Wait for Kaggle (monitor)..."
python3 -u -c 'import time; print("monitor placeholder")' || true

echo "Step 3: Download assets..."
# placeholder: real download handled by kaggle_setup.py

echo "Step 4: Assemble all videos..."
python3 assemble_all.py || true

echo "Step 5: Verify outputs..."
python3 - <<'PY'
import os
for ch in ['projects/twisted-truths-ep1/render','projects/crimeledger/render','projects/mindtactics/render']:
    if os.path.exists(ch):
        print(ch, 'exists, files:', len(os.listdir(ch)))
    else:
        print(ch, 'missing')
PY

echo "=== DONE ==="
ls -lh projects/*/render/FINAL*.mp4 || true
ls -lh projects/*/render/thumbnail.jpg || true
