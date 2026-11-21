#!/usr/bin/env bash
# up.sh — one command to make Vera work, with your latest changes, and SHOW you.
#
# The whole build/run grind in one go: sync the brain into its runtime home,
# (re)start the service, rebuild + install the Mac app when its Swift changed,
# then print a plain-English readiness report so you can SEE she's working.
#
#   ./scripts/up.sh            sync brain + restart + build app (if changed) + report
#   ./scripts/up.sh --brain    just the brain (skip the Mac app build — fastest)
#   ./scripts/up.sh --report   don't change anything, just show me where things stand
#
# It never leaves her worse: each step is guarded, and the service install only
# swaps in the new brain after it answers a health check.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
MODE="${1:-all}"

step()  { printf "\n\033[1m▸ %s\033[0m\n" "$*"; }
ok()    { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn()  { printf "  \033[33m!\033[0m %s\n" "$*"; }

# ── report-only: show understanding, touch nothing ─────────────────────────────
if [ "$MODE" = "--report" ]; then
  python3 -m cognitive_twin doctor
  exit $?
fi

# ── 1) brain → runtime home + (re)start the service ────────────────────────────
step "Syncing her brain and (re)starting the service"
if bash scripts/install-service.sh >/tmp/vera-up-service.log 2>&1; then
  ok "brain synced + up (launchd-managed on :7878)"
else
  warn "service install hit a snag — see /tmp/vera-up-service.log"
  tail -5 /tmp/vera-up-service.log 2>/dev/null | sed 's/^/    /'
fi

# ── 2) Mac app — rebuild only when its Swift actually changed ───────────────────
if [ "$MODE" != "--brain" ]; then
  step "Mac app"
  NEED_BUILD=1
  APP="/Applications/Vera.app/Contents/MacOS/Vera"
  if [ -f "$APP" ]; then
    # newest swift source vs the installed binary — skip the build if nothing's newer
    NEWEST_SRC="$(find macos/Vera/Sources -name '*.swift' -newer "$APP" 2>/dev/null | head -1)"
    [ -z "$NEWEST_SRC" ] && NEED_BUILD=0
  fi
  if [ "$NEED_BUILD" = "1" ]; then
    if bash macos/Vera/build-app.sh >/tmp/vera-up-app.log 2>&1; then
      ok "app rebuilt + installed (your Swift changes are live)"
    else
      warn "app build failed — see /tmp/vera-up-app.log (brain is still up)"
      tail -6 /tmp/vera-up-app.log 2>/dev/null | sed 's/^/    /'
    fi
  else
    ok "app unchanged — nothing to rebuild"
  fi
fi

# ── 3) the point: SHOW that it works, in plain words ───────────────────────────
step "Is she ready?"
echo
python3 -m cognitive_twin doctor
