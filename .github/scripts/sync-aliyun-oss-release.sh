#!/usr/bin/env bash
set -euo pipefail

: "${ALIYUN_OSS_ACCESS_KEY_ID:?Missing ALIYUN_OSS_ACCESS_KEY_ID}"
: "${ALIYUN_OSS_ACCESS_KEY_SECRET:?Missing ALIYUN_OSS_ACCESS_KEY_SECRET}"
: "${ALIYUN_OSS_BUCKET:?Missing ALIYUN_OSS_BUCKET}"
: "${ALIYUN_OSS_ENDPOINT:?Missing ALIYUN_OSS_ENDPOINT}"
: "${ALIYUN_OSS_REGION:?Missing ALIYUN_OSS_REGION}"
: "${ALIYUN_OSS_PUBLIC_BASE_URL:?Missing ALIYUN_OSS_PUBLIC_BASE_URL}"
: "${RELEASE_TAG:?Missing RELEASE_TAG}"

artifact_dir="${RELEASE_ARTIFACTS_DIR:-release-artifacts}"
test -d "$artifact_dir"

apk_name="RootLink-${RELEASE_TAG}-android.apk"
windows_name="RootLink-${RELEASE_TAG}-windows.zip"
apk_path="${artifact_dir}/${apk_name}"
windows_path="${artifact_dir}/${windows_name}"

test -s "$apk_path"
test -s "$windows_path"
command -v ossutil >/dev/null 2>&1 || {
  echo "Missing ossutil. Install Aliyun ossutil 2.0 on the release runner."
  exit 1
}

export OSS_ACCESS_KEY_ID="${ALIYUN_OSS_ACCESS_KEY_ID}"
export OSS_ACCESS_KEY_SECRET="${ALIYUN_OSS_ACCESS_KEY_SECRET}"
export OSS_ENDPOINT="${ALIYUN_OSS_ENDPOINT}"
export OSS_REGION="${ALIYUN_OSS_REGION}"

oss_prefix="${ALIYUN_OSS_PREFIX:-releases}"
oss_prefix="${oss_prefix#/}"
oss_prefix="${oss_prefix%/}"

oss_base="oss://${ALIYUN_OSS_BUCKET}/${oss_prefix}/${RELEASE_TAG}"
public_base="${ALIYUN_OSS_PUBLIC_BASE_URL%/}/${oss_prefix}/${RELEASE_TAG}"
apk_url="${public_base}/${apk_name}"
windows_url="${public_base}/${windows_name}"

ossutil cp "$apk_path" "${oss_base}/${apk_name}" \
  --content-type "application/vnd.android.package-archive" \
  --content-disposition "attachment; filename=\"${apk_name}\"" \
  --cache-control "public, max-age=31536000, immutable" \
  -f

ossutil cp "$windows_path" "${oss_base}/${windows_name}" \
  --content-type "application/zip" \
  --content-disposition "attachment; filename=\"${windows_name}\"" \
  --cache-control "public, max-age=31536000, immutable" \
  -f

curl --fail --silent --show-error --location --head "$apk_url" > apk-headers.txt
if ! grep -qi '^content-type:.*application/vnd.android.package-archive' apk-headers.txt; then
  echo "Unexpected APK Content-Type:"
  cat apk-headers.txt
  exit 1
fi
if ! grep -qi "^content-disposition:.*${apk_name}" apk-headers.txt; then
  echo "Unexpected APK Content-Disposition:"
  cat apk-headers.txt
  exit 1
fi

curl --fail --silent --show-error --location --head "$windows_url" > windows-headers.txt
if ! grep -qi '^content-type:.*application/zip' windows-headers.txt; then
  echo "Unexpected Windows ZIP Content-Type:"
  cat windows-headers.txt
  exit 1
fi

echo "Aliyun OSS Android APK: ${apk_url}"
echo "Aliyun OSS Windows ZIP: ${windows_url}"
