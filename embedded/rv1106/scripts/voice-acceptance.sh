#!/bin/sh
# 板端/仿真共用验收入口；仅 --allow-cloud 明确允许真实服务计费。
# 不 source 配置、不修改混音器、不打印密钥。日志含对话文本，权限设为仅当前用户可读。
set -eu
umask 077
binary=${1:?Usage: sh voice-acceptance.sh BINARY CONFIG [SECONDS] [--allow-cloud]}
config=${2:?CONFIG is required}
duration=${3:-600}
allow_cloud=${4:-}
case "$duration" in ''|*[!0-9]*|0) echo 'SECONDS must be a positive integer' >&2; exit 2;; esac
[ "$duration" -le 86400 ] || exit 2
[ -x "$binary" ] && [ -f "$config" ] || { echo 'Binary/config not found' >&2; exit 2; }
# 报告含私人对话，使用新建的权限受限子目录；可指定持久目录，避免 /tmp 随重启丢失。
# 父目录必须由部署者提前准备，脚本不覆盖或删除已有报告。
report_root=${ROOTLINK_REPORT_DIR:-${TMPDIR:-/tmp}}
[ -d "$report_root" ] || { echo 'ROOTLINK_REPORT_DIR must be an existing directory' >&2; exit 2; }
report=$(mktemp -d "$report_root/rootlink-voice-acceptance.XXXXXX")
echo "report_dir=$report"
echo "utc=$(date -u)"
if [ -r /proc/asound/cards ]; then cat /proc/asound/cards; else echo 'No /proc/asound/cards (expected in simulation)'; fi
"$binary" doctor --config "$config" > "$report/doctor.log" 2>&1 || {
  cat "$report/doctor.log"; exit 1;
}
cat "$report/doctor.log"
if grep -q '^service_mode=cloud$' "$report/doctor.log" && [ "$allow_cloud" != --allow-cloud ]; then
  echo 'Cloud voice incurs API charges. Re-run with --allow-cloud after reviewing config.' >&2
  exit 2
fi
echo 'Speak normally, pause within sentences, and verify playback never retriggers listening.'
echo 'Do not place microphone next to speaker. This script never changes mixer volumes.'
child=
monitor=
interrupted=0
stop_child() {
  interrupted=1
  if [ -n "$child" ]; then kill -TERM "$child" 2>/dev/null || :; fi
}
trap stop_child INT TERM
"$binary" voice --config "$config" --duration "$duration" > "$report/voice.log" 2>&1 &
child=$!
(
  printf 'seconds,rss_kib,peak_rss_kib\n'
  start=$(date +%s)
  while [ -r "/proc/$child/status" ]; do
    now=$(date +%s)
    awk -v elapsed="$((now-start))" '
      /^VmRSS:/ {rss=$2} /^VmHWM:/ {peak=$2}
      END {if (rss != "") print elapsed "," rss "," peak}
    ' "/proc/$child/status" 2>/dev/null || :
    sleep 5
  done
) > "$report/memory.csv" &
monitor=$!
result=0
wait "$child" || result=$?
if [ "$interrupted" -eq 1 ]; then wait "$child" 2>/dev/null || :; result=0; fi
child=
kill "$monitor" 2>/dev/null || :
wait "$monitor" 2>/dev/null || :
trap - INT TERM
# 输出最终统计及受控错误；完整对话留在权限受限的日志中。
grep -E '^(utterances|turn_errors|network_|authentication_|provider_|vad_|asr_|llm_|tts_|playback_|buffer_|capture_|http_|rss_|peak_rss_|voice error)' "$report/voice.log" || :
echo "exit_code=$result"
echo "memory_samples=$report/memory.csv"
# 将预热后的摘要直接输出，报告目录丢失时仍能保留基本观测；范围不等于泄漏判定。
awk -F, 'NR>1 && $1>=60 {
  if (n==0) {first=$2; min=$2; max=$2}
  if ($2<min) min=$2; if ($2>max) max=$2; last=$2; n++
} END {
  print "warm_rss_samples=" n+0
  if (n>0) {print "warm_rss_first_kib=" first; print "warm_rss_last_kib=" last;
    print "warm_rss_min_kib=" min; print "warm_rss_max_kib=" max}
}' "$report/memory.csv"
echo 'Review RSS after 60s warm-up. A finite sample is not proof of absence of leaks.'
exit "$result"
