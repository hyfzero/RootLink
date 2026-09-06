#!/bin/sh
set -eu

binary=${1:-./rootlink-audio-smoke}
capture_device=${CAPTURE_DEVICE:-default}
playback_device=${PLAYBACK_DEVICE:-default}
record_seconds=${RECORD_SECONDS:-5}
loopback_seconds=${LOOPBACK_SECONDS:-0}
output_wav=${OUTPUT_WAV:-/tmp/rootlink-phase1.wav}

if [ ! -x "$binary" ]; then
  echo "Audio executable is missing or not executable: $binary" >&2
  exit 2
fi

echo "== ALSA devices =="
if command -v arecord >/dev/null 2>&1; then arecord -l || true; fi
if command -v aplay >/dev/null 2>&1; then aplay -l || true; fi

echo "== Record ${record_seconds}s to $output_wav =="
"$binary" record --output "$output_wav" --duration "$record_seconds" \
  --capture-device "$capture_device"

echo "== WAV header =="
if command -v file >/dev/null 2>&1; then file "$output_wav"; fi

echo "== Playback =="
"$binary" play --input "$output_wav" --playback-device "$playback_device"

if [ "$loopback_seconds" != "0" ]; then
  echo "== Loopback ${loopback_seconds}s =="
  "$binary" loopback --duration "$loopback_seconds" \
    --capture-device "$capture_device" --playback-device "$playback_device"
fi

echo "Acceptance smoke test completed. No mixer settings were changed."
