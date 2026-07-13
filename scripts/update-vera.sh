#!/usr/bin/env bash
# update-vera.sh — keep Vera current from her own repo. No downloads, no
# installers: `git pull` IS the update.
#
# Why this works: the app runs the Python agent straight from this repo, so a
# pull updates her brain immediately (the app's watchdog restarts the server).
# Only the Swift shell (macos/) needs a rebuild — and only when it changed.
#
#   ./scripts/update-vera.sh            # update, restart only what changed
#   ./scripts/update-vera.sh --check    # say what would change, do nothing
#
# Safe by design:
#   - fast-forward only — local commits or edits are never overwritten; a
#     dirty or diverged repo is left exactly as it is.
#   - /Applications/Vera.app is replaced only after a fresh build succeeded.
#   - offline? she stays as she is; nothing errors.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

say() { echo "[update-vera] $*"; }
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

command -v git >/dev/null 2>&1 || { say "git not found — skipped."; exit 0; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { say "not a git repo — skipped."; exit 0; }

# anything new upstream? (quiet no-op when offline; local-ahead counts as current)
git fetch --quiet origin 2>/dev/null || { say "offline — she stays as she is."; exit 0; }
N="$(git rev-list --count 'HEAD..@{u}' 2>/dev/null || echo 0)"
if [ "$N" = "0" ]; then
  [ "$CHECK" = 1 ] && say "already up to date."
  exit 0
fi

if [ "$CHECK" = 1 ]; then
  say "update available: $N new commit(s)."
  git log --oneline 'HEAD..@{u}' | sed 's/^/  /'
  exit 0
fi

# never clobber local work — an update must not cost the user anything
if ! git diff --quiet || ! git diff --cached --quiet; then
  say "repo has local changes — leaving them alone. Commit/stash, then rerun."
  exit 0
fi

CHANGED="$(git diff --name-only "HEAD..@{u}")"
git merge --ff-only '@{u}' --quiet || { say "history diverged — resolve manually."; exit 0; }
say "updated to $(git rev-parse --short HEAD)."

# the brain updates on next server start — nudge it now; the app brings it back
if pgrep -f "cognitive_twin.voice.server" >/dev/null 2>&1; then
  pkill -f "cognitive_twin.voice.server" 2>/dev/null || true
  say "voice server restarting with the new brain."
fi

# rebuild + reinstall the shell only when the mac app itself changed
if echo "$CHANGED" | grep -q "^macos/"; then
  say "mac app changed — rebuilding…"
  (cd macos/Vera && ./build-app.sh) || { say "build failed — keeping the installed app."; exit 0; }
  if [ -d "/Applications/Vera.app" ]; then
    osascript -e 'tell application "Vera" to quit' >/dev/null 2>&1 || true
    sleep 1
    rm -rf "/Applications/Vera.app"
    ditto "macos/Vera/Vera.app" "/Applications/Vera.app"
    say "reinstalled /Applications/Vera.app — relaunching."
    open -a "/Applications/Vera.app"
  else
    say "built macos/Vera/Vera.app (not installed to /Applications — copy it once, updates then flow)."
  fi
fi
say "done."
