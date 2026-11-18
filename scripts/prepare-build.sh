#!/usr/bin/env bash
# prepare-build.sh — ONE command that prepares Vera's build for ALL devices, so
# "we know the app" everywhere from a single, verified source.
#
# Ankur's ask: "prepare the build so that we know the app, for all the devices."
# This does NOT invent new build systems — it runs the per-device builds that
# already exist, in order, verifying the shared brain first so a broken core can't
# ship to any device:
#
#   1. CORE      verify the shared Python brain (imports, syntax, the new code-sense)
#   2. MAC       the unified Vera service   (scripts/install-vera.sh)
#   3. IPHONE    the iOS app                (ios/build-ios.sh — regenerate + compile)
#   4. TAILNET   cross-device reachability  (VERA_HOST=0.0.0.0 over Tailscale)
#
# SAFETY: by default this is a DRY RUN that only verifies the core and reports what
# each device build would do — it does NOT restart the live brain or kick off long
# Xcode builds (those are the user's to run). Pass --apply to actually run the Mac +
# iPhone builds. The live brain is sacred; we never restart it implicitly.
#
#   ./scripts/prepare-build.sh            verify core + report the plan (safe)
#   ./scripts/prepare-build.sh --apply    also run the Mac + iPhone builds
#   ./scripts/prepare-build.sh --mac      only prepare the Mac build (+ --apply to run)
#   ./scripts/prepare-build.sh --ios      only prepare the iPhone build (+ --apply to run)
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 1

APPLY=0; WANT_MAC=1; WANT_IOS=1
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    --mac)   WANT_MAC=1; WANT_IOS=0 ;;
    --ios)   WANT_MAC=0; WANT_IOS=1 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  esac
done

VERSION="$(python3 -c "import cognitive_twin as c; print(c.__version__)" 2>/dev/null || echo '?')"
bold() { printf "\033[1m%s\033[0m\n" "$1"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
bad()  { printf "  \033[31m✗\033[0m %s\n" "$1"; }
note() { printf "  \033[2m%s\033[0m\n" "$1"; }

bold "Vera build — one app, every device   (v$VERSION)"
echo

# ── 1. CORE: the shared brain must be sound before any device ships ────────────
bold "1. CORE — the shared brain"
CORE_OK=1
if python3 -c "import ast,sys; [ast.parse(open(f).read()) for f in sys.argv[1:]]" \
     cognitive_twin/cli.py cognitive_twin/code_sense.py cognitive_twin/rag.py 2>/dev/null; then
  ok "source parses (cli, code_sense, rag)"
else
  bad "a core file has a syntax error — fix before building"; CORE_OK=0
fi
if python3 -c "from cognitive_twin import code_sense, rag, cli" 2>/dev/null; then
  ok "core modules import cleanly"
else
  bad "a core module failed to import"; CORE_OK=0
fi
# code-sense readiness (coding mode) — informational, not fatal
if python3 -c "from cognitive_twin import code_sense; raise SystemExit(0 if code_sense.is_ready() else 1)" 2>/dev/null; then
  ok "coding mode ready (code index present)"
else
  note "coding mode not indexed yet — run:  ctwin code index"
fi
echo
if [ "$CORE_OK" != "1" ]; then
  bad "Core failed — not preparing any device build. Fix the core first."
  exit 1
fi

# ── 2. MAC: the unified Vera service ───────────────────────────────────────────
if [ "$WANT_MAC" = "1" ]; then
  bold "2. MAC — the unified Vera service"
  note "build: scripts/install-vera.sh  (syncs brain → ~/Library/Application Support/Vera, (re)starts the one launchd service)"
  if [ "$APPLY" = "1" ]; then
    if [ -x scripts/install-vera.sh ]; then
      bash scripts/install-vera.sh && ok "Mac build prepared (service installed/updated)" \
        || bad "Mac build reported an error — see output above"
    else
      bash scripts/install-service.sh && ok "Mac build prepared (via install-service.sh)" \
        || bad "Mac build reported an error — see output above"
    fi
  else
    note "DRY RUN — not restarting the live brain. Run with --apply, or yourself:"
    echo "        bash scripts/install-vera.sh"
  fi
  echo
fi

# ── 3. IPHONE: the iOS app ─────────────────────────────────────────────────────
if [ "$WANT_IOS" = "1" ]; then
  bold "3. IPHONE — the iOS app"
  if [ -f ios/build-ios.sh ]; then
    note "build: ios/build-ios.sh  (xcodegen generate → xcodebuild for the simulator)"
    if command -v xcodegen >/dev/null 2>&1 && command -v xcodebuild >/dev/null 2>&1; then
      if [ "$APPLY" = "1" ]; then
        ( cd ios && bash build-ios.sh ) && ok "iPhone build prepared (compiled)" \
          || bad "iPhone build reported an error — open ios/Anita.xcodeproj in Xcode"
      else
        note "DRY RUN — not launching Xcode. Run with --apply, or yourself:"
        echo "        (cd ios && ./build-ios.sh)"
      fi
    else
      note "xcodegen/xcodebuild not both present — regenerate + build in Xcode:"
      echo "        (cd ios && xcodegen generate) && open ios/Anita.xcodeproj"
    fi
  else
    bad "ios/build-ios.sh missing — iOS build path not found"
  fi
  echo
fi

# ── 4. TAILNET: cross-device reachability ──────────────────────────────────────
bold "4. TAILNET — reach the one app from every device"
TS="$(command -v tailscale || echo /Applications/Tailscale.app/Contents/MacOS/Tailscale)"
if [ -x "$TS" ] && "$TS" status >/dev/null 2>&1; then
  HOSTNAME_TS="$("$TS" status --self 2>/dev/null | awk 'NR==1{print $2}')"
  ok "Tailscale up — other devices reach Vera at:  http://${HOSTNAME_TS:-<this-mac>}:7878"
  note "the brain must bind the tailnet for this: start it with VERA_HOST=0.0.0.0 (the vera-app launcher does)"
else
  note "Tailscale not detected — devices on the same network can still reach:  http://$(hostname):7878 (bind VERA_HOST=0.0.0.0)"
fi
echo

# ── summary ────────────────────────────────────────────────────────────────────
bold "The app, on every device"
echo "   💻 Mac     — Vera.app + the unified brain service (:7878)"
echo "   📱 iPhone  — the iOS app (ios/Anita.xcodeproj), talks to the hub"
echo "   🌐 Any     — browser on the tailnet → http://<this-mac>:7878"
echo
if [ "$APPLY" != "1" ]; then
  note "This was a safe dry run (core verified, builds NOT run). To build for real:"
  echo "        bash scripts/prepare-build.sh --apply"
fi
