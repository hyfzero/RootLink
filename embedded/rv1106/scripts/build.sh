#!/bin/sh
set -eu

# Echo-Mate 的构建入口会先选择板级配置，再调用实际构建系统。这里保留同样的
# 单入口体验，但只解析白名单键，不直接 source 配置文件，避免配置内容被当成命令执行。
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
config_file=${1:-"$source_dir/config/rootlink.conf"}

if [ ! -f "$config_file" ]; then
  echo "RootLink audio config does not exist: $config_file" >&2
  exit 2
fi

cfg_target=simulator
cfg_audio_api=simulated
cfg_service_mode=mock
cfg_build_type=Release
cfg_build_tests=ON
cfg_build_dir=
cfg_sdk_root=
cfg_capture_device=default
cfg_playback_device=default
cfg_buffer_frames=100
cfg_ui_backend=none
cfg_lvgl_source=

line_number=0
while IFS= read -r raw_line || [ -n "$raw_line" ]; do
  line_number=$((line_number + 1))
  # 去掉 Windows 文本文件结尾的 CR；空行和整行注释不参与解析。
  line=$(printf '%s' "$raw_line" | tr -d '\r')
  case "$line" in
    ''|'#'*) continue ;;
  esac
  case "$line" in
    *=*) ;;
    *)
      echo "Invalid config line $line_number (expected KEY=VALUE): $line" >&2
      exit 2
      ;;
  esac

  key=${line%%=*}
  value=${line#*=}
  case "$key" in
    TARGET) cfg_target=$value ;;
    AUDIO_API) cfg_audio_api=$value ;;
    SERVICE_MODE) cfg_service_mode=$value ;;
    UI_BACKEND) cfg_ui_backend=$value ;;
    LVGL_SOURCE_DIR) cfg_lvgl_source=$value ;;
    UI_DEVICE|UI_WIDTH|UI_HEIGHT) : ;;
    BUILD_TYPE) cfg_build_type=$value ;;
    BUILD_TESTS) cfg_build_tests=$value ;;
    BUILD_DIR) cfg_build_dir=$value ;;
    RV1106_SDK_ROOT) cfg_sdk_root=$value ;;
    CAPTURE_DEVICE) cfg_capture_device=$value ;;
    PLAYBACK_DEVICE) cfg_playback_device=$value ;;
    BUFFER_FRAMES) cfg_buffer_frames=$value ;;
    # 以下键由 rootlink-voice 在运行时读取，构建入口只验证它们属于白名单，
    # 不解释内容，更不会读取或打印密钥。
    ASR_PROVIDER|ASR_MODEL|ASR_BASE_URL|LLM_PROVIDER|LLM_MODEL|LLM_BASE_URL|\
    TTS_PROVIDER|TTS_MODEL|TTS_BASE_URL|TTS_VOICE|TTS_SAMPLE_RATE|TTS_TRANSLATE_TO|TTS_TRANSLATION_TIMEOUT_MS|MODELS_FILE|\
    PERSONA_BACKEND|PYTHON_EXECUTABLE|PYTHON_CORE_ENTRY|PYTHON_DATA_DIR|PERSONA_START_TIMEOUT_MS|PERSONA_TURN_TIMEOUT_MS|SECRETS_FILE|ROLE_DIR|SESSION_DIR|HISTORY_TURNS|HISTORY_TOKEN_BUDGET|\
    VAD_START_FRAMES|VAD_PRE_ROLL_MS|VAD_END_SILENCE_MS|VAD_MIN_UTTERANCE_MS|\
    VAD_MAX_UTTERANCE_MS|VAD_MIN_RMS|VAD_NOISE_MULTIPLIER|VAD_NOISE_ALPHA|\
    CONNECT_TIMEOUT_MS|ASR_TIMEOUT_MS|LLM_TIMEOUT_MS|TTS_TIMEOUT_MS|RETRY_COUNT|UI_PAGE_HOLD_MS) : ;;
    *)
      echo "Unknown config key '$key' on line $line_number" >&2
      exit 2
      ;;
  esac
done < "$config_file"

# 构建和运行使用同一优先级：环境变量高于配置；不执行配置或密钥文件内容。
cfg_target=${TARGET:-$cfg_target}
cfg_audio_api=${AUDIO_API:-$cfg_audio_api}
cfg_service_mode=${SERVICE_MODE:-$cfg_service_mode}
cfg_sdk_root=${RV1106_SDK_ROOT:-$cfg_sdk_root}
cfg_build_dir=${BUILD_DIR:-$cfg_build_dir}
cfg_ui_backend=${UI_BACKEND:-$cfg_ui_backend}
cfg_lvgl_source=${LVGL_SOURCE_DIR:-$cfg_lvgl_source}
case "$cfg_ui_backend" in
  none|sdl|fbdev) ;;
  *) echo "UI_BACKEND must be none, sdl or fbdev" >&2; exit 2 ;;
esac

case "$cfg_target" in
  simulator|rv1106) ;;
  *) echo "TARGET must be simulator or rv1106 (got '$cfg_target')" >&2; exit 2 ;;
esac
case "$cfg_audio_api" in
  simulated|alsa) ;;
  *) echo "AUDIO_API must be simulated or alsa (got '$cfg_audio_api')" >&2; exit 2 ;;
esac
case "$cfg_service_mode" in
  mock|cloud) ;;
  *) echo "SERVICE_MODE must be mock or cloud (got '$cfg_service_mode')" >&2; exit 2 ;;
esac
case "$cfg_build_type" in
  Release|Debug|RelWithDebInfo|MinSizeRel) ;;
  *) echo "Unsupported BUILD_TYPE: $cfg_build_type" >&2; exit 2 ;;
esac
case "$cfg_build_tests" in
  ON|OFF) ;;
  *) echo "BUILD_TESTS must be ON or OFF (got '$cfg_build_tests')" >&2; exit 2 ;;
esac
case "$cfg_buffer_frames" in
  ''|*[!0-9]*|0) echo "BUFFER_FRAMES must be a positive integer." >&2; exit 2 ;;
esac
if [ -z "$cfg_capture_device" ] || [ -z "$cfg_playback_device" ]; then
  echo "CAPTURE_DEVICE and PLAYBACK_DEVICE cannot be empty." >&2
  exit 2
fi

case "$cfg_target:$cfg_audio_api:$cfg_service_mode" in
  simulator:simulated:mock|simulator:alsa:cloud|rv1106:alsa:cloud) ;;
  *)
    echo "Unsupported TARGET+AUDIO_API+SERVICE_MODE combination: $cfg_target+$cfg_audio_api+$cfg_service_mode" >&2
    echo "Use simulator+simulated+mock, simulator+alsa+cloud, or rv1106+alsa+cloud." >&2
    exit 2
    ;;
esac

if [ -z "$cfg_build_dir" ]; then
  cfg_build_dir="$source_dir/build/$cfg_target-$cfg_audio_api-$cfg_service_mode"
  if [ "$cfg_ui_backend" != none ]; then cfg_build_dir="$cfg_build_dir-$cfg_ui_backend"; fi
fi

if [ "$cfg_service_mode" = cloud ]; then cfg_service_api=curl; else cfg_service_api=mock; fi

echo "RootLink audio build profile"
echo "  target:     $cfg_target"
echo "  audio API:  $cfg_audio_api"
echo "  services:   $cfg_service_mode ($cfg_service_api)"
echo "  build type: $cfg_build_type"
echo "  output:     $cfg_build_dir"
echo "  capture:    $cfg_capture_device"
echo "  playback:   $cfg_playback_device"
echo "  buffer:     $cfg_buffer_frames frames"

if [ "$cfg_target" = simulator ]; then
  cmake -S "$source_dir" -B "$cfg_build_dir" \
    -DROOTLINK_UI_BACKEND="$cfg_ui_backend" \
    -DROOTLINK_LVGL_SOURCE_DIR="$cfg_lvgl_source" \
    -DCMAKE_BUILD_TYPE="$cfg_build_type" \
    -DBUILD_TESTING="$cfg_build_tests" \
    -DROOTLINK_AUDIO_API="$cfg_audio_api" \
    -DROOTLINK_SERVICE_API="$cfg_service_api" \
    -DROOTLINK_DEFAULT_CAPTURE_DEVICE="$cfg_capture_device" \
    -DROOTLINK_DEFAULT_PLAYBACK_DEVICE="$cfg_playback_device" \
    -DROOTLINK_DEFAULT_BUFFER_FRAMES="$cfg_buffer_frames" \
    -DROOTLINK_AUDIO_BUILD_CLI=ON \
    -DROOTLINK_VOICE_BUILD_CLI=ON
else
  sdk_root=$cfg_sdk_root
  if [ -z "$sdk_root" ]; then sdk_root=${RV1106_SDK_ROOT:-}; fi
  if [ -z "$sdk_root" ]; then
    echo "Set RV1106_SDK_ROOT in the config file or environment." >&2
    exit 2
  fi
  cmake -S "$source_dir" -B "$cfg_build_dir" \
    -DROOTLINK_UI_BACKEND="$cfg_ui_backend" \
    -DROOTLINK_LVGL_SOURCE_DIR="$cfg_lvgl_source" \
    -DCMAKE_TOOLCHAIN_FILE="$source_dir/cmake/rv1106-toolchain.cmake" \
    -DRV1106_SDK_ROOT="$sdk_root" \
    -DRV1106_CA_BUNDLE="${RV1106_CA_BUNDLE:-}" \
    -DCMAKE_BUILD_TYPE="$cfg_build_type" \
    -DBUILD_TESTING=OFF \
    -DROOTLINK_AUDIO_API=alsa \
    -DROOTLINK_SERVICE_API=curl \
    -DROOTLINK_DEFAULT_CAPTURE_DEVICE="$cfg_capture_device" \
    -DROOTLINK_DEFAULT_PLAYBACK_DEVICE="$cfg_playback_device" \
    -DROOTLINK_DEFAULT_BUFFER_FRAMES="$cfg_buffer_frames" \
    -DROOTLINK_AUDIO_BUILD_CLI=ON \
    -DROOTLINK_VOICE_BUILD_CLI=ON
fi

cmake --build "$cfg_build_dir" --parallel
if [ "$cfg_target" = simulator ] && [ "$cfg_build_tests" = ON ]; then
  ctest --test-dir "$cfg_build_dir" --output-on-failure
fi

cmake -E copy_if_different "$config_file" "$cfg_build_dir/rootlink.conf"
echo "Built: $cfg_build_dir/rootlink-audio-smoke"
echo "Built: $cfg_build_dir/rootlink-voice"
