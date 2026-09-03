# Vera — Inbox Triage (browser extension)

A **thin capture layer** for Vera. It reads your **already-logged-in** mail tab
(Yahoo Mail / Gmail) and asks your **local Vera core** to sort the messages into
*real · marketing · spam · unsure* — so you can see what's junk without handing
Vera a password.

## The flow

```
You (logged into Yahoo in your browser)
  │
  │  click the Vera extension → it reads the visible inbox list
  ▼
Extension  ──POST messages──▶  local Vera  (127.0.0.1:7878)
                                  │  classifies on-device (rules + local LLM)
  ◀──────────── verdicts ───────┘
  ▼
Popup shows the report (junk first)
```

**Nothing leaves your machine.** No password is read or sent — only the sender /
subject / snippet the page already shows. It never deletes, moves, or marks
anything: pure read-only triage.

## Install (developer mode)

1. Start your **local Vera** (the macOS app, or run the server:
   `python3 -m cognitive_twin.voice.server`). It listens on `127.0.0.1:7878`.
2. In Chrome/Edge: `chrome://extensions` → toggle **Developer mode** →
   **Load unpacked** → pick this `extensions/browser/` folder.
   (Firefox: `about:debugging` → This Firefox → Load Temporary Add-on →
   pick `manifest.json`.)
3. Open your **Yahoo Mail** inbox, click the Vera icon, hit **Triage this inbox**.

## Notes / limits

- It reads what's **on screen** — scroll the inbox to load more rows first for a
  bigger sample.
- Web selectors can break when Yahoo/Gmail change their page; the scraper has a
  generic fallback, and the selectors live in one file (`scrape.js`).
- The heavy lifting (classification) is the same engine the IMAP path uses
  (`cognitive_twin/email_triage.py` → `classify_web`), so the browser and
  direct-IMAP flows agree.
