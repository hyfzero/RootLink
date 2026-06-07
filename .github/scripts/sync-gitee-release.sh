#!/usr/bin/env bash
set -euo pipefail

: "${GITEE_TOKEN:?Missing GITEE_TOKEN}"
: "${GITEE_REPO:?Missing GITEE_REPO}"
: "${RELEASE_TAG:?Missing RELEASE_TAG}"
: "${GITHUB_REPOSITORY:?Missing GITHUB_REPOSITORY}"

artifact_dir="${RELEASE_ARTIFACTS_DIR:-release-artifacts}"
test -d "$artifact_dir"
compgen -G "${artifact_dir}/*" > /dev/null

user_json="$(
  curl --fail --silent --show-error --get \
    --data-urlencode "access_token=${GITEE_TOKEN}" \
    https://gitee.com/api/v5/user
)"
owner="$(jq --raw-output '.login' <<< "$user_json")"
test -n "$owner" && test "$owner" != "null"

repo_api="https://gitee.com/api/v5/repos/${owner}/${GITEE_REPO}"
status="$(
  curl --silent --output /dev/null --write-out "%{http_code}" --get \
    --data-urlencode "access_token=${GITEE_TOKEN}" \
    "$repo_api"
)"
if [ "$status" = "404" ]; then
  curl --fail --silent --show-error \
    --data-urlencode "access_token=${GITEE_TOKEN}" \
    --data-urlencode "name=${GITEE_REPO}" \
    --data-urlencode "path=${GITEE_REPO}" \
    --data-urlencode "description=RootLink release mirror. The primary repository is hosted on GitHub." \
    --data-urlencode "homepage=https://github.com/${GITHUB_REPOSITORY}" \
    --data-urlencode "public=1" \
    https://gitee.com/api/v5/user/repos > /dev/null
elif [ "$status" != "200" ]; then
  echo "Unable to access Gitee repository: HTTP ${status}"
  exit 1
fi

curl --fail --silent --show-error --request PATCH \
  --data-urlencode "access_token=${GITEE_TOKEN}" \
  --data-urlencode "name=${GITEE_REPO}" \
  --data-urlencode "description=RootLink release mirror. The primary repository is hosted on GitHub." \
  --data-urlencode "homepage=https://github.com/${GITHUB_REPOSITORY}" \
  --data-urlencode "private=false" \
  "$repo_api" > /dev/null

for attempt in {1..12}; do
  repo_json="$(
    curl --fail --silent --show-error --get \
      --data-urlencode "access_token=${GITEE_TOKEN}" \
      "$repo_api"
  )"
  if jq --exit-status '.private == false' <<< "$repo_json" > /dev/null; then
    break
  fi
  if [ "$attempt" = "12" ]; then
    echo "Gitee repository did not become public in time."
    exit 1
  fi
  sleep 5
done

existing="$(
  curl --silent --get \
    --data-urlencode "access_token=${GITEE_TOKEN}" \
    --write-out "%{http_code}" \
    --output existing-release.json \
    "${repo_api}/releases/tags/${RELEASE_TAG}"
)"
if [ "$existing" = "200" ]; then
  release_id="$(jq --raw-output '.id // empty' existing-release.json)"
elif [ "$existing" != "404" ]; then
  echo "Unable to inspect existing Gitee release: HTTP ${existing}"
  exit 1
fi

if [ -z "${release_id:-}" ]; then
  for attempt in {1..6}; do
    create_status="$(
      curl --silent --show-error --request POST \
        --data-urlencode "access_token=${GITEE_TOKEN}" \
        --data-urlencode "tag_name=${RELEASE_TAG}" \
        --data-urlencode "name=RootLink ${RELEASE_TAG}" \
        --data-urlencode "body=Primary release: https://github.com/${GITHUB_REPOSITORY}/releases/tag/${RELEASE_TAG}" \
        --data-urlencode "target_commitish=main" \
        --output created-release.json \
        --write-out "%{http_code}" \
        "${repo_api}/releases"
    )"
    if [ "$create_status" = "200" ] || [ "$create_status" = "201" ]; then
      break
    fi
    if [ "$attempt" = "6" ]; then
      echo "Unable to create Gitee release: HTTP ${create_status}"
      exit 1
    fi
    sleep 5
  done
  release_id="$(jq --raw-output '.id' created-release.json)"
fi
test -n "$release_id" && test "$release_id" != "null"

attachments="$(
  curl --fail --silent --show-error --get \
    --data-urlencode "access_token=${GITEE_TOKEN}" \
    "${repo_api}/releases/${release_id}/attach_files"
)"

pids=()
for artifact in "${artifact_dir}"/*; do
  artifact_name="$(basename "$artifact")"
  if jq --exit-status --arg name "$artifact_name" \
    'any(.[]; .name == $name)' <<< "$attachments" > /dev/null; then
    echo "Already uploaded: ${artifact_name}"
    continue
  fi

  (
    curl --fail --silent --show-error --retry 3 --retry-all-errors \
      --form "access_token=${GITEE_TOKEN}" \
      --form "file=@${artifact}" \
      "${repo_api}/releases/${release_id}/attach_files" > /dev/null
    echo "Uploaded: ${artifact_name}"
  ) &
  pids+=("$!")
done

for pid in "${pids[@]}"; do
  wait "$pid"
done

echo "Gitee release: https://gitee.com/${owner}/${GITEE_REPO}/releases/tag/${RELEASE_TAG}"
