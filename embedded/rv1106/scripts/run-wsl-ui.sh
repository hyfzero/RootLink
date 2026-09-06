#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$script_dir/.."
config=${1:-build/windows-cloud/python-ui.conf}
binary=build/ubuntu/rootlink-voice
if [ ! -x "$binary" ]; then
  binary=build/simulator-alsa-cloud-sdl/rootlink-voice
fi
if [ ! -f "$config" ] || [ ! -x "$binary" ]; then
  echo "Missing WSL UI config or binary. See PYTHON_CORE.md." >&2
  exit 1
fi
export UI_BACKEND=sdl
exec "$binary" voice --config "$config"
