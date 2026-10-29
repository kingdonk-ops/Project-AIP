#!/usr/bin/env bash
# Build and Trivy-scan the demo image set — ONE recipe shared by the `security` workflow (the PR /
# merge-queue gate) and `deploy-coolify` (post-merge), so the two gates build and scan the same
# images with the same flags and can no longer drift apart. SECURITY-08 / OPS-11.
#
# The drift this guards against: `security` used to build and scan only aip-api and aip-web, while
# `deploy-coolify` scans five images. A CVE in one of the other three (migrator, postgres-demo,
# keycloak-demo) passed every PR and only failed after merge, in the deploy. Both gates now call
# this script, so they always cover the same five images.
#
# Subcommands:
#   build   Build the five demo images and record their names in $IMAGE_LIST.
#   scan    Trivy-scan every recorded image (fixable HIGH/CRITICAL fail unless excepted), writing
#           table + JSON evidence to $EVIDENCE_DIR; exits non-zero if any image fails.
#
# Environment (build):
#   TAG        the tag put on every built image (required)
#   SHA        commit sha -> GIT_SHA build-arg and the image revision label (default "unknown")
#   REGISTRY   image-name prefix, e.g. ghcr.io/<owner> (deploy) or empty for local tags (security)
#   EXTRA_TAG  an optional second tag (deploy also tags ":main")
#   BUILD_ID   optional build-id label/arg (deploy passes the run id)
#   LABELS     "1" adds the OCI source/revision labels (needs $GITHUB_REPOSITORY); otherwise omitted
# Environment (scan):
#   TRIVY_IMAGE  the pinned Trivy image (required)
#   TAG          must match the build so the same refs are scanned
#   REGISTRY     must match the build
# Environment (both):
#   IMAGE_LIST    state file of built image names (default $RUNNER_TEMP/images.txt, else ./images.txt)
#   EVIDENCE_DIR  scan-evidence directory, relative to the repo root (default evidence)
#
# Run from the repository root.
set -euo pipefail

cmd="${1:?usage: scan_images.sh <build|scan>}"

IMAGE_LIST="${IMAGE_LIST:-${RUNNER_TEMP:-.}/images.txt}"
EVIDENCE_DIR="${EVIDENCE_DIR:-evidence}"
REGISTRY="${REGISTRY:-}"

# name [tag] -> the full image reference (defaults to $TAG).
ref() {
  local name="$1" tag="${2:-$TAG}"
  if [ -n "$REGISTRY" ]; then echo "${REGISTRY}/${name}:${tag}"; else echo "${name}:${tag}"; fi
}

build_one() {
  local name="$1" dockerfile="$2"
  shift 2
  local tags=(-t "$(ref "$name")")
  [ -n "${EXTRA_TAG:-}" ] && tags+=(-t "$(ref "$name" "$EXTRA_TAG")")
  local labels=()
  if [ "${LABELS:-}" = "1" ]; then
    labels=(--label "org.opencontainers.image.source=https://github.com/${GITHUB_REPOSITORY}"
            --label "org.opencontainers.image.revision=${SHA:-unknown}")
  fi
  docker build -f "$dockerfile" "$@" "${labels[@]}" "${tags[@]}" .
  echo "$name" >>"$IMAGE_LIST"
}

# The five images deploy-coolify ships to the demo. aip-web-demo is the web image built the Coolify
# way (VITE_AIP_DEMO=1 and the demo nginx conf), i.e. the same way the live demo serves it.
build_all() {
  : >"$IMAGE_LIST"
  build_one aip-api apps/api/Dockerfile \
    --build-arg "GIT_SHA=${SHA:-unknown}" --build-arg "BUILD_ID=${BUILD_ID:-dev}"
  build_one aip-migrator infra/docker/migrator.Dockerfile
  build_one aip-web-demo apps/web/Dockerfile \
    --build-arg VITE_AIP_DEMO=1 --build-arg NGINX_CONF=infra/coolify/nginx.conf
  build_one aip-postgres-demo infra/coolify/images/postgres.Dockerfile
  build_one aip-keycloak-demo infra/coolify/images/keycloak.Dockerfile
}

# These are exactly the flags deploy-coolify and security must keep identical: fixable HIGH/CRITICAL
# fail (--exit-code 1), unfixed ones are ignored, and the committed exception file is honoured.
scan_all() {
  mkdir -p "$EVIDENCE_DIR"
  local cache="${TRIVY_CACHE:-${RUNNER_TEMP:-/tmp}/trivy-cache}"
  mkdir -p "$cache"
  local fail=0 name format
  while read -r name; do
    [ -n "$name" ] || continue
    for format in table json; do
      docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
        -v "$cache:/root/.cache" -v "$PWD/config:/cfg:ro" -v "$PWD/$EVIDENCE_DIR:/out" \
        "$TRIVY_IMAGE" image --quiet --scanners vuln --severity HIGH,CRITICAL \
        --ignore-unfixed --ignorefile /cfg/vuln-exceptions.txt --exit-code 1 \
        --format "$format" --output "/out/trivy-$name.$format" "$(ref "$name")" || fail=1
    done
    cat "$EVIDENCE_DIR/trivy-$name.table"
  done <"$IMAGE_LIST"
  if [ "$fail" -ne 0 ]; then
    echo "::error::a demo image failed the Trivy scan: nothing was pushed or deployed"
  fi
  return "$fail"
}

case "$cmd" in
  build)
    [ -n "${TAG:-}" ] || {
      echo "scan_images.sh build: TAG is required" >&2
      exit 2
    }
    build_all
    ;;
  scan)
    [ -n "${TRIVY_IMAGE:-}" ] || {
      echo "scan_images.sh scan: TRIVY_IMAGE is required" >&2
      exit 2
    }
    [ -n "${TAG:-}" ] || {
      echo "scan_images.sh scan: TAG is required" >&2
      exit 2
    }
    scan_all
    ;;
  *)
    echo "scan_images.sh: unknown subcommand '$cmd' (expected build or scan)" >&2
    exit 2
    ;;
esac
