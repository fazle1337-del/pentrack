#!/usr/bin/env bash
#
# Pen Test Tracker deploy helper.
#
# The build half runs on your DEV machine (buildx multi-arch -> Docker Hub).
# The recreate/verify half runs on the PI (pull the new image, force-recreate,
# then confirm the live container is actually running the new build).
#
# Usage:
#   ./deploy.sh build      # dev machine: build + push multi-arch images
#   ./deploy.sh recreate   # pi: pull new images and force-recreate containers
#   ./deploy.sh verify     # pi: print the live CACHE_NAME from the web container
#   ./deploy.sh help

set -euo pipefail

# ============================================================================
# CONFIG  — confirm these against your actual setup before first run
# ============================================================================
DOCKER_USER="tonybooom"
TAG="latest"
PLATFORMS="linux/amd64,linux/arm64"

# Images you build (name : dockerfile : build-context). Postgres is not built.
API_IMAGE="${DOCKER_USER}/pen-test-tracker-api"
API_DOCKERFILE="./api/Dockerfile"
API_CONTEXT="./api"

WEB_IMAGE="${DOCKER_USER}/pen-test-tracker-web"
WEB_DOCKERFILE="./web/Dockerfile"
WEB_CONTEXT="./web"

# Pi-side: how Umbrel runs this app, and where to find the service worker.
APP_ID="tony-pen-test-tracker"
COMPOSE_FILE="${HOME}/umbrel/app-data/${APP_ID}/docker-compose.yml"
API_CONTAINER="${APP_ID}_api_1"
WEB_CONTAINER="${APP_ID}_web_1"

BUILDER="pentest-builder"   # buildx builder name
# ============================================================================

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\n\033[1;33m!! %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mxx %s\033[0m\n' "$*" >&2; exit 1; }

digest_of() {
  # Current remote manifest digest for an image, or empty if it doesn't exist.
  docker buildx imagetools inspect "$1:${TAG}" 2>/dev/null \
    | awk '/^Digest:/ {print $2; exit}' || true
}

ensure_builder() {
  if ! docker buildx inspect "${BUILDER}" >/dev/null 2>&1; then
    log "Creating buildx builder '${BUILDER}'"
    docker buildx create --name "${BUILDER}" --use >/dev/null
  else
    docker buildx use "${BUILDER}"
  fi
  docker buildx inspect --bootstrap >/dev/null
}

build_push() {
  local image="$1" dockerfile="$2" context="$3"
  local before after
  before="$(digest_of "${image}")"

  log "Building + pushing ${image}:${TAG} (${PLATFORMS})"
  docker buildx build \
    --platform "${PLATFORMS}" \
    -f "${dockerfile}" \
    -t "${image}:${TAG}" \
    --push \
    "${context}"

  after="$(digest_of "${image}")"
  log "${image}:${TAG} digest: ${after:-<none>}"
  if [[ -n "${before}" && "${before}" == "${after}" ]]; then
    warn "${image} digest did NOT change — nothing new was pushed. The build was a no-op (all layers cached). This is NOT deployed."
  fi
}

cmd_build() {
  command -v docker >/dev/null || die "docker not found on this machine"
  ensure_builder
  build_push "${API_IMAGE}" "${API_DOCKERFILE}" "${API_CONTEXT}"
  build_push "${WEB_IMAGE}" "${WEB_DOCKERFILE}" "${WEB_CONTEXT}"
  log "Build complete. Now run './deploy.sh recreate' on the Pi, then './deploy.sh verify'."
}

cmd_recreate() {
  [[ -f "${COMPOSE_FILE}" ]] || die "Compose file not found: ${COMPOSE_FILE}"
  # :latest won't re-pull on its own, so pull explicitly before recreating.
  log "Pulling new images"
  sudo docker compose -f "${COMPOSE_FILE}" pull
  log "Recreating containers"
  sudo docker compose -f "${COMPOSE_FILE}" up -d --force-recreate
  log "Recreate complete. Confirm with './deploy.sh verify'."
}

verify_image() {
  local image="$1" container="$2"
  local remote img_id running

  remote="$(digest_of "${image}")"
  [[ -n "${remote}" ]] || { warn "${image}: no manifest found on Docker Hub"; return 1; }

  img_id="$(sudo docker inspect "${container}" --format '{{.Image}}' 2>/dev/null || true)"
  [[ -n "${img_id}" ]] || { warn "${container}: not found / not running"; return 1; }

  running="$(sudo docker image inspect "${img_id}" \
    --format '{{range .RepoDigests}}{{println .}}{{end}}' \
    | sed -n "s|^${image}@||p" | head -n1)"
  [[ -n "${running}" ]] || { warn "${container}: image has no Hub digest (built locally?)"; return 1; }

  if [[ "${running}" == "${remote}" ]]; then
    log "${container} OK — ${remote} (matches Docker Hub :${TAG})"
  else
    warn "${container} STALE — has ${running}, Hub has ${remote}. NOT deployed."
    return 1
  fi
}

cmd_verify() {
  local rc=0
  verify_image "${API_IMAGE}" "${API_CONTAINER}" || rc=1
  verify_image "${WEB_IMAGE}" "${WEB_CONTAINER}" || rc=1
  [[ ${rc} -eq 0 ]] \
    && log "All containers are running the current Docker Hub images." \
    || die "One or more containers are not on the current image — not deployed."
}

case "${1:-help}" in
  build)    cmd_build ;;
  recreate) cmd_recreate ;;
  verify)   cmd_verify ;;
  *)
    cat <<EOF
Pen Test Tracker deploy helper

  ./deploy.sh build      Dev machine: buildx multi-arch build + push to Docker Hub
  ./deploy.sh recreate   Pi: pull new images and force-recreate containers
  ./deploy.sh verify     Pi: print the live CACHE_NAME from the web container

A change is only deployed once 'verify' confirms the live containers
match the current Docker Hub images.
EOF
    ;;
esac
