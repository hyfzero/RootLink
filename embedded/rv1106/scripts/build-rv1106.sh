#!/bin/sh
set -eu

if [ -z "${RV1106_SDK_ROOT:-}" ]; then
  echo "RV1106_SDK_ROOT is not set. Point it at the Echo-Mate rv1106-sdk directory." >&2
  exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
build_dir=${1:-"$source_dir/build/rv1106-arm"}

cmake -S "$source_dir" -B "$build_dir" \
  -DCMAKE_TOOLCHAIN_FILE="$source_dir/cmake/rv1106-toolchain.cmake" \
  -DRV1106_SDK_ROOT="$RV1106_SDK_ROOT" \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=OFF \
  -DROOTLINK_AUDIO_API=alsa \
  -DROOTLINK_SERVICE_API=curl \
  -DROOTLINK_AUDIO_BUILD_CLI=ON \
  -DROOTLINK_VOICE_BUILD_CLI=ON
cmake --build "$build_dir" --parallel

echo "Built: $build_dir/rootlink-audio-smoke"
echo "Built: $build_dir/rootlink-voice"
