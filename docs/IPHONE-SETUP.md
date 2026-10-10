# Connecting Vera on your iPhone

Vera thinks on *your* hardware, never a cloud. Your Mac does the thinking; your
iPhone is the window. This guide connects the two — privately, in about five
minutes.

> **The one idea to hold:** the phone doesn't run the model. It reaches the one on
> your Mac, over a private network only your devices can see. Nothing is public.

---

## Before you start

You'll need three things, all free:

| | What | Why |
|---|---|---|
| 🧠 | **Ollama** on your Mac | the model that does the thinking |
| 🔗 | **Tailscale** on your Mac *and* iPhone | the private link between them |
| 📱 | **Vera** on your iPhone | the window |

---

## Step 1 — Let your Mac answer on the private network

Out of the box, the model only talks to the Mac itself. We point it at your
Tailscale address so your phone can reach it — and *only* your phone, never the
open internet.

On the Mac, find your Tailscale address and set it:

```bash
tailscale ip -4                                   # e.g. 100.91.27.70
launchctl setenv OLLAMA_HOST "100.91.27.70:11434" # your address
```

Then **quit and reopen the Ollama app** so it picks that up. That's it for the Mac.

> Prefer it to stick after every restart? There's a one-time setup in
> [the longer notes](#make-it-permanent-optional) at the end.

---

## Step 2 — Turn on Tailscale on your iPhone

Open the **Tailscale** app on your phone and make sure it's **on** (signed into the
same account as your Mac).

This is the step people miss most often — if Tailscale is off on the phone, nothing
else will connect.

---

## Step 3 — Point Vera at your Mac

In Vera, open **Settings → Where she thinks**, and in the **top field** type your
Mac's Tailscale address:

```
100.91.27.70:11434
```

Tap **Test connection**. When it says **“Reached”**, you're done — Vera can think.

---

## If something's not connecting

- **“Model unreachable” or “Can't reach that host”** — Tailscale is probably off on
  the phone (Step 2), or the address in Settings is empty/wrong (Step 3).
- **It worked, then stopped after a Mac restart** — reopen the Ollama app once.
  (The setting is remembered; the app just needs a nudge to re-read it.)
- **“Can I use it away from home?”** — Yes. Tailscale works anywhere, privately.
  That's the point: everywhere you go, nothing on the open internet.

---

## Make it permanent *(optional)*

So Step 1 survives every Mac restart, create this once:

```bash
cat > ~/Library/LaunchAgents/com.sinhaankur.ollama-host.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.sinhaankur.ollama-host</string>
  <key>ProgramArguments</key>
  <array><string>/bin/launchctl</string><string>setenv</string>
    <string>OLLAMA_HOST</string><string>100.91.27.70:11434</string></array>
  <key>RunAtLoad</key><true/>
</dict></plist>
PLIST
launchctl load ~/Library/LaunchAgents/com.sinhaankur.ollama-host.plist
```

*(Use your own Tailscale address in place of `100.91.27.70`.)*

---

### A note on privacy

Vera is built to stay yours. The thinking happens on your Mac, the link is your
own private Tailscale network, and nothing is sent to anyone else. "Reachable from
anywhere" and "private" are both true here — that's the whole design.
