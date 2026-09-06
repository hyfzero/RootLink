#!/bin/sh
# 只检查 ELF，不在主机执行 ARM 程序，也不使用可能执行目标文件的 ldd。
set -eu
binary=${1:?Usage: sh verify-arm.sh ARM_BINARY BUILDROOT_SYSROOT}
sysroot=${2:?BUILDROOT_SYSROOT is required}
reader=${READELF:-readelf}
command -v "$reader" >/dev/null
command -v file >/dev/null
check_arm() {
  header=$(LC_ALL=C "$reader" -h "$1")
  printf '%s\n' "$header" | grep -Eq 'Class:[[:space:]]+ELF32' || return 1
  printf '%s\n' "$header" | grep -Eq 'Machine:[[:space:]]+ARM$' || return 1
}
check_arm "$binary" || { echo 'Expected 32-bit ARM ELF' >&2; exit 1; }
file "$binary"
LC_ALL=C "$reader" -l "$binary" | grep 'interpreter' || :
dynamic=$(LC_ALL=C "$reader" -d "$binary")
printf '%s\n' "$dynamic" | grep NEEDED
for name in asound curl json-c; do
  printf '%s\n' "$dynamic" | grep -q "lib$name.so" || {
    echo "Missing dynamic dependency: lib$name" >&2; exit 1;
  }
done
for name in asound curl json-c ssl crypto; do
  found=
  for directory in "$sysroot/usr/lib" "$sysroot/lib"; do
    for library in "$directory/lib$name.so"*; do
      [ -f "$library" ] || continue
      check_arm "$library" || { echo "Not ARM ELF: $library" >&2; exit 1; }
      found=$library
      break
    done
    [ -z "$found" ] || break
  done
  [ -n "$found" ] || { echo "Missing sysroot library: lib$name" >&2; exit 1; }
  echo "target_library=$found"
  if [ "$name" = curl ]; then
    tls=$(LC_ALL=C "$reader" -d "$found")
    printf '%s\n' "$tls" | grep -Eq 'lib(ssl|crypto)\.so' || {
      echo 'libcurl must use target OpenSSL (enable TLS in Buildroot)' >&2; exit 1;
    }
  fi
done
echo 'arm_verification=ok (runtime/physical audio still require board testing)'
