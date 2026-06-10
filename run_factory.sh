#!/bin/bash
set -euo pipefail

CHANNEL="${1:-}"
if [ -z "$CHANNEL" ]; then
  echo "Usage: $0 {weirdhistory|crimeledger|mindtactics}"
  echo ""
  echo "Channel rotation:"
  echo "  Mon = weirdhistory  (25 scenes, 25 min)"
  echo "  Wed = crimeledger   (18 scenes, 18 min)"
  echo "  Fri = mindtactics   (15 scenes, 15 min)"
  exit 1
fi

echo "=== OPENMONTAGE FACTORY: $CHANNEL ==="
echo ""
echo "Step 1: Select topic..."
python3 scripts/select_topic.py
export CHANNEL
export TOPIC="${TOPIC:-}"

echo ""
echo "Step 2: Generate script ($CHANNEL)..."
python3 scripts/generate_script.py

echo ""
echo "Step 3: Fetch assets..."
python3 scripts/fetch_assets.py

echo ""
echo "Step 4: Generate TTS audio..."
python3 scripts/generate_tts.py

echo ""
echo "Step 5: Assemble video..."
python3 assemble_v2.py

echo ""
echo "Step 6: Verify output..."
ls -lh "projects/$CHANNEL/render/FINAL_v3.mp4" 2>/dev/null || echo "  WARNING: no output found"

echo ""
echo "=== DONE ==="
