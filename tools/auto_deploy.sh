#!/usr/bin/env bash
# Auto-deploy (CD): run on the server every few minutes (cron / systemd timer).
#
# If GitHub has a newer commit on master AND that commit's tests passed on GitHub
# (CI green), it pulls the code, rebuilds the app and checks it is healthy.
# If the new version is not healthy, it goes back to the previous version.
#
# Nothing is pushed to the server from outside: the server asks GitHub itself.
# .env, the database and the logs are untouched (they are not in git / live in volumes).
#
# Setup (once, on the server):  see docs/DEPLOYMENT.md -> "Auto-deploy"
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
BRANCH="${BRANCH:-master}"
REPO="${GITHUB_REPO:-vatsmesra22-bit/ocrproject}"   # owner/name, for the CI check
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/healthz}"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') auto-deploy: $*"; }

cd "$APP_DIR"
# only one run at a time
exec 9>"/tmp/auto_deploy.$(id -u).lock"
flock -n 9 || { log "another run is still going - skipped"; exit 0; }

git fetch --quiet origin "$BRANCH"
current=$(git rev-parse HEAD)
latest=$(git rev-parse "origin/$BRANCH")
[ "$current" = "$latest" ] && exit 0   # nothing new

# deploy only code whose tests passed on GitHub
ci=$(curl -fsS -m 20 "https://api.github.com/repos/$REPO/commits/$latest/check-runs" \
     | grep -o '"conclusion": *"[a-z_]*"' | head -1 | grep -o '[a-z_]*"$' | tr -d '"' || true)
if [ "$ci" != "success" ]; then
    log "new commit ${latest:0:7} - tests not passed yet (${ci:-pending}) - waiting"
    exit 0
fi

log "deploying ${latest:0:7} (was ${current:0:7})"
git merge --ff-only --quiet "origin/$BRANCH"
docker compose up -d --build

healthy=no
for _ in $(seq 1 30); do
    sleep 5
    if curl -fsS -m 5 "$HEALTH_URL" >/dev/null 2>&1; then healthy=yes; break; fi
done

if [ "$healthy" = yes ]; then
    log "live: ${latest:0:7} is healthy"
else
    log "NOT healthy - going back to ${current:0:7}"
    git reset --hard --quiet "$current"
    docker compose up -d --build
    exit 1
fi
