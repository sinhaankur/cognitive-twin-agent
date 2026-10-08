# Homebrew Cask for Vera — the free, zero-warning install for developers.
#
#   brew tap sinhaankur/vera https://github.com/sinhaankur/cognitive-twin-agent
#   brew install --cask vera
#
# (The tap command points brew at THIS repo, where the cask lives in Casks/.
#  No separate homebrew-vera repo is needed — the explicit URL handles it.)
#
# Why this exists: Homebrew downloads the app and removes the macOS quarantine
# flag itself, so there is NO Gatekeeper "unidentified developer" prompt — all
# free, no Apple Developer certificate. This is the cleanest install for anyone
# comfortable with one Terminal command. (Non-technical users should use the DMG
# + right-click → Open instead — see the README.)
#
# On each release: bump `version` and `sha256` (sha256 of the release .zip).
cask "vera" do
  version "0.3.0"
  sha256 "bb4f04f10baf0d001708ab2595dc85bb8315c4a139e1733392ee2fff2bfab4ab"

  url "https://github.com/sinhaankur/cognitive-twin-agent/releases/download/vera-v#{version}/Vera-v#{version}.zip"
  name "Vera"
  desc "Private, on-device AI companion — a twin of someone you love, on your Mac"
  homepage "https://github.com/sinhaankur/cognitive-twin-agent"

  depends_on macos: ">= :big_sur"

  app "Vera.app"

  # Vera sets up her own brain on first launch (installs Ollama + the right-sized
  # model), so the cask only places the app — no postflight needed. The one-line
  # installer stays available for the manual route.
  caveats <<~EOS
    Vera runs entirely on your Mac — nothing is uploaded.

    On first launch she sets up her brain (installs the local model engine and
    downloads a right-sized model for your Mac). Give her a few minutes, then
    click the orb to talk.

    Needs Apple Silicon. Open source under AGPL-3.0.
  EOS

  zap trash: [
    "~/.cognitive-twin",
    "~/Library/LaunchAgents/com.sinhaankur.vera.brain.plist",
    "~/Library/Logs/Vera",
  ]
end
