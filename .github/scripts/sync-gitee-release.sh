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

auth="$(printf '%s:%s' "$owner" "$GITEE_TOKEN" | base64 --wrap=0)"
release_tree="$(git rev-parse "${RELEASE_TAG}^{tree}")"
release_date="$(git show --no-patch --format=%aI "$RELEASE_TAG")"
snapshot_commit="$(
  printf 'RootLink %s release snapshot\n' "$RELEASE_TAG" |
    GIT_AUTHOR_NAME="RootLink Release" \
    GIT_AUTHOR_EMAIL="actions@users.noreply.github.com" \
    GIT_AUTHOR_DATE="$release_date" \
    GIT_COMMITTER_NAME="RootLink Release" \
    GIT_COMMITTER_EMAIL="actions@users.noreply.github.com" \
    GIT_COMMITTER_DATE="$release_date" \
    git commit-tree "$release_tree"
)"
test -n "$snapshot_commit"
git remote add gitee "https://gitee.com/${owner}/${GITEE_REPO}.git"
git -c "http.extraHeader=Authorization: Basic ${auth}" push gitee \
  "+${snapshot_commit}:refs/heads/main" \
  "+${snapshot_commit}:refs/tags/${RELEASE_TAG}"

existing="$(
  curl --silent --get \
    --data-urlencode "access_token=${GITEE_TOKEN}" \
    --write-out "%{http_code}" \
    --output existing-release.json \
    "${repo_api}/releases/tags/${RELEASE_TAG}"
)"
if [ "$existing" = "200" ]; then
  release_id="$(jq --raw-output '.id' existing-release.json)"
  curl --fail --silent --show-error --request DELETE --get \
    --data-urlencode "access_token=${GITEE_TOKEN}" \
    "${repo_api}/releases/${release_id}" > /dev/null
elif [ "$existing" != "404" ]; then
  echo "Unable to inspect existing Gitee release: HTTP ${existing}"
  exit 1
fi

release_json="$(
  curl --fail --silent --show-error \
    --data-urlencode "access_token=${GITEE_TOKEN}" \
    --data-urlencode "tag_name=${RELEASE_TAG}" \
    --data-urlencode "name=RootLink ${RELEASE_TAG}" \
    --data-urlencode "body=Primary release: https://github.com/${GITHUB_REPOSITORY}/releases/tag/${RELEASE_TAG}" \
    --data-urlencode "target_commitish=main" \
    "${repo_api}/releases"
)"
release_id="$(jq --raw-output '.id' <<< "$release_json")"
test -n "$release_id" && test "$release_id" != "null"

for artifact in "${artifact_dir}"/*; do
  curl --fail --silent --show-error \
    --form "access_token=${GITEE_TOKEN}" \
    --form "file=@${artifact}" \
    "${repo_api}/releases/${release_id}/attach_files" > /dev/null
done

echo "Gitee release: https://gitee.com/${owner}/${GITEE_REPO}/releases/tag/${RELEASE_TAG}"
