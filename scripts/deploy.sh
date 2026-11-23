#!/usr/bin/env bash
# Deploy to a Docker host over SSH. Images are built by GitHub Actions (.github/workflows/images.yml)
# and published to GHCR; the host only pulls them.
#
#   scripts/deploy.sh user@host [--bot]
#
# Copies compose.yaml, Caddyfile, .env and geo/, logs the host into ghcr.io with GHCR_TOKEN from .env
# (a PAT with read:packages; needed once), pulls and starts the stack, and on an empty database loads
# the CSVs and computes product embeddings. Safe to re-run. DEPLOY_DIR sets the remote directory
# (default: uzexify).
set -euo pipefail

host=${1:?usage: scripts/deploy.sh user@host [--bot]}
shift
profiles=(--profile app)
for arg in "$@"; do
  case $arg in
    --bot) profiles+=(--profile bot) ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done
dir=${DEPLOY_DIR:-uzexify}

cd "$(dirname "$0")/.."
[[ -f .env ]] || { echo ".env is missing" >&2; exit 1; }
grep -q '^PUBLIC_HOST=.' .env || { echo "set PUBLIC_HOST in .env" >&2; exit 1; }

remote() { ssh -o BatchMode=yes "$host" "mkdir -p '$dir' && cd '$dir' && $*"; }
send() { COPYFILE_DISABLE=1 tar czf - --no-xattrs "$@" | remote "tar xzf -"; }

if ! remote "sudo test -f /root/.docker/config.json && sudo grep -q ghcr.io /root/.docker/config.json"; then
  token=$(grep '^GHCR_TOKEN=' .env | cut -d= -f2-)
  [[ -n $token ]] || { echo "set GHCR_TOKEN (PAT with read:packages) in .env" >&2; exit 1; }
  owner=$(sed -nE 's#^ +image: ghcr.io/([^/]+)/.*#\1#p' compose.yaml | head -1)
  printf '%s' "$token" | remote "sudo docker login ghcr.io -u '$owner' --password-stdin >/dev/null"
fi

send compose.yaml Caddyfile .env geo
remote "chmod 600 .env && sudo docker compose ${profiles[*]} pull -q && \
  sudo docker compose ${profiles[*]} up -d --no-build --remove-orphans"

if [[ "$(remote "sudo docker compose exec -T db psql -U uzex -d uzex -tAc \"SELECT to_regclass('deals') IS NOT NULL\"")" != "t" ]]; then
  echo "empty database: loading CSVs and embeddings"
  send data/uzex_spot_data
  remote "sudo docker compose run --rm api uzexify ingest --data-dir /data"
  remote "sudo docker compose run --rm api uzexify embed"
  remote "sudo docker compose restart api"
fi

remote "sudo docker image prune -f >/dev/null; sudo docker compose ps --format '{{.Name}} {{.Status}}'"
