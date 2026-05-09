#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

DURATION=3
DEVICE=""
OUT="data/audio/query.wav"

usage() {
  printf 'Usage: %s [--duration seconds] [--device hw:X,Y] [output.wav]\n' "$0"
  printf '\n'
  printf 'Examples:\n'
  printf '  %s\n' "$0"
  printf '  %s data/audio/test_query.wav\n' "$0"
  printf '  %s --duration 5 --device hw:1,0 data/audio/test_query.wav\n' "$0"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --duration)
      DURATION="${2:?missing value for --duration}"
      shift 2
      ;;
    --device)
      DEVICE="${2:?missing value for --device}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      OUT="$1"
      shift
      ;;
  esac
done

if ! command -v arecord >/dev/null 2>&1; then
  printf 'arecord not found. Run ./scripts/setup_pi.sh first.\n' >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"

ARGS=(-f S16_LE -r 16000 -c 1 -t wav -d "$DURATION")
if [ -n "$DEVICE" ]; then
  ARGS=(-D "$DEVICE" "${ARGS[@]}")
fi

printf 'Recording %s seconds to %s\n' "$DURATION" "$OUT"
arecord "${ARGS[@]}" "$OUT"
printf 'recorded %s\n' "$OUT"
