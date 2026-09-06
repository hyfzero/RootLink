#!/bin/sh
# 仅供 simulated/mock 二进制的离线验收。强制隔离私有配置，绝不会调用云端。
# 独立临时目录保留日志/音频便于检查；不删除用户路径，也不读取真实密钥文件。
set -eu
umask 077
binary=${1:?Usage: sh test-voice-cli.sh BINARY CONFIG}
config=${2:?CONFIG required}
report=$(mktemp -d "${TMPDIR:-/tmp}/rootlink-voice-cli.XXXXXX")
export TARGET=simulator AUDIO_API=simulated SERVICE_MODE=mock
export MODELS_FILE="$report/absent-models.json" SECRETS_FILE="$report/absent-secrets.env"
export SESSION_DIR="$report/sessions"
echo "report_dir=$report"
# Phase 2 实时采集分段独立于角色和会话；重新读取产物检查 WAV 格式有效。
ROLE_DIR="$report/absent-role" "$binary" vad --config "$config" --duration 4 \
  --output-dir "$report/live-segments" > "$report/live-vad.log"
grep -q '^segments=[1-9]' "$report/live-vad.log"
[ ! -e "$SESSION_DIR" ]
"$binary" vad --config "$config" --input "$report/live-segments/segment-1.wav" \
  --output-dir "$report/rechecked-segments" > "$report/rechecked-vad.log"
grep -q '^segments=1$' "$report/rechecked-vad.log"
"$binary" doctor --config "$config" > "$report/doctor.log"
"$binary" chat --config "$config" --text '离线角色测试' > "$report/chat.log"
"$binary" synthesize --config "$config" --text '离线语音测试' --output "$report/tts.wav"
"$binary" transcribe --config "$config" --input "$report/tts.wav" > "$report/asr.log"
"$binary" vad --config "$config" --input "$report/tts.wav" --output-dir "$report/segments" > "$report/vad.log"
"$binary" voice --config "$config" --duration 7 > "$report/voice.log"
grep -q '^utterances=[1-9]' "$report/voice.log"
grep -q '^state=PLAYING$' "$report/voice.log"
child=
trap 'if [ -n "$child" ]; then kill -TERM "$child" 2>/dev/null || :; fi' EXIT INT TERM
"$binary" voice --config "$config" --duration 30 > "$report/signal.log" &
child=$!
sleep 1
kill -INT "$child"
# watchdog 确保真实信号测试不会因为退出回归无限挂起。
(sleep 5; touch "$report/signal-timeout"; kill -TERM "$child" 2>/dev/null || :) &
watchdog=$!
result=0
wait "$child" || result=$?
child=
kill "$watchdog" 2>/dev/null || :
wait "$watchdog" 2>/dev/null || :
trap - EXIT INT TERM
[ "$result" -eq 0 ]
[ ! -e "$report/signal-timeout" ]
grep -q '^utterances=' "$report/signal.log"
if "$binary" voice --config "$config" --duration nan > "$report/invalid.log" 2>&1; then
  echo 'Invalid duration was accepted' >&2; exit 1
fi
if "$binary" doctor --config "$config" --buffer-frames 4294967297 > "$report/overflow.log" 2>&1; then
  echo 'Overflowing buffer capacity was accepted' >&2; exit 1
fi
echo 'Mock CLI commands, full conversation, SIGINT and invalid arguments passed.'
