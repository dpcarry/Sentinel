#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

DEVICE="${SENTINAL_MIC_DEVICE:-hw:2,0}"
DURATION="${SENTINAL_RECORD_SECONDS:-5}"
OUT="${1:-data/audio/query.wav}"

./scripts/record_usb_query.sh --device "$DEVICE" --duration "$DURATION" "$OUT"
