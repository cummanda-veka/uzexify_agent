#!/usr/bin/env bash
# Deploy to a Docker host over SSH. Images are built by GitHub Actions (.github/workflows/images.yml)
# and published to GHCR as public packages; the host only pulls them.
#
#   scripts/deploy.sh user@host [--bot]
#
# Copies compose.yaml, Caddyfile, .env and geo/, pulls and starts the stack, and on an empty database
# loads the CSVs and computes product embeddings. Safe to re-run. DEPLOY_DIR sets the remote directory
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

send compose.yaml Caddyfile .env geo
remote "chmod 600 .env && sudo docker compose ${profiles[*]} pull -q && \
  sudo docker compose ${profiles[*]} up -d --no-build --remove-orphans"

psql() { remote "sudo docker compose exec -T db psql -U uzex -d uzex -tAc \"$1\""; }
if [[ "$(psql "SELECT to_regclass('deals') IS NOT NULL")" != "t" ]]; then
  echo "empty database: loading CSVs"
  send data/uzex_spot_data
  remote "sudo docker compose run --rm api uzexify ingest --data-dir /data"
else
  remote "sudo docker compose run --rm api uzexify grant"  # roles are not in dumps; cheap and idempotent
fi
if [[ "$(psql "SELECT count(*) FROM products WHERE embedding IS NULL")" != "0" ]]; then
  echo "products without embeddings: computing them"
  remote "sudo docker compose run --rm api uzexify embed" \
    || echo "embedding failed; product search stays lexical until the next deploy" >&2
fi
remote "sudo docker compose restart api"

remote "sudo docker image prune -f >/dev/null; sudo docker compose ps --format '{{.Name}} {{.Status}}'"
