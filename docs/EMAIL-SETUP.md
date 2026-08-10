# Connecting Vera to your email (Gmail)

Vera reads your inbox to know your life — who writes to you, which accounts you
have, what you actually use — and keeps a **sealed, on-device index**. Nothing
leaves this Mac except the fetch to *your* Gmail. This is the 5-minute setup.

There are two ways to connect. **Start with the app-password path** — it works
today with everything already built. OAuth is optional and nicer long-term.

---

## Path A — App password over IMAP (recommended, works now)

Gmail won't accept your normal password for apps; you generate a one-time
**app password**. This also sidesteps 2FA cleanly.

### 1. Turn on 2-Step Verification (if you haven't)
<https://myaccount.google.com/signinoptions/twosv> → enable it. App passwords
require it.

### 2. Create an app password
<https://myaccount.google.com/apppasswords>

- App name: `Vera` (any label)
- Google shows a **16-character password** like `abcd efgh ijkl mnop`.
  Copy it (spaces don't matter).

### 3. Give Vera your address + store the password in the Keychain
```bash
# your address goes in the environment (it's not secret)
export IMAP_USER="h99311@gmail.com"
export IMAP_HOST="imap.gmail.com"        # default; you can skip this
export IMAP_PORT="993"                    # default; you can skip this

# the password goes in the macOS Keychain, NOT a plaintext .env
python3 -m cognitive_twin.secrets_store set IMAP_PASSWORD
# (paste the 16-char app password at the hidden prompt)
```

> Put the two `export` lines in your `.env` or shell profile so they persist. The
> **password never touches disk in plaintext** — it lives in the Keychain, read
> via `secrets_store`.

### 4. Verify + first sync
```bash
python3 -m cognitive_twin.security doctor        # should still say ✓ SAFE
python3 -m cognitive_twin.mail_store sync         # indexes your inbox (sealed)
python3 -m cognitive_twin.account_inventory report
```

That's it. Ask Vera "which accounts should I close?" and the skills do the rest.

---

## Path B — OAuth 2.0 (optional, no app password)

OAuth lets Vera connect without a stored password, using Google's consent screen.
It needs a one-time Google Cloud setup. The tokens Vera receives are **sealed with
the same device-bound key** as everything else.

### 1. Create a Google Cloud project
<https://console.cloud.google.com/projectcreate> → name it (e.g. `vera-mail`).

### 2. Enable the Gmail API
APIs & Services → **Library** → search **Gmail API** → **Enable**.

### 3. Configure the consent screen
APIs & Services → **OAuth consent screen** → **External** → fill the basics →
add your own Google account under **Test users** (so only you can use it).

### 4. Create an OAuth client — **Desktop app**
APIs & Services → **Credentials** → **Create credentials** → **OAuth client ID**
→ Application type **Desktop app** → Create. Copy the **client ID** and
**client secret**.

### 5. Store the client id/secret in the Keychain
```bash
python3 -m cognitive_twin.secrets_store set GOOGLE_OAUTH_CLIENT_ID
python3 -m cognitive_twin.secrets_store set GOOGLE_OAUTH_CLIENT_SECRET
# redirect URI default is http://127.0.0.1:8765/callback — keep it unless you changed it
```

### 6. Run the consent flow once
```bash
python3 -m cognitive_twin.gmail_oauth login     # opens your browser; approve
python3 -m cognitive_twin.gmail_oauth status     # should say: connected ✓
```

Vera now holds a sealed refresh token and can read/send without a password. (Wiring
the mail index to use OAuth's XOAUTH2 instead of the app password is the same
`mail_store sync` command; the token path is already in `gmail_oauth.py`.)

---

## What Vera can do once connected

| Command | What it does |
|---|---|
| `mail_store sync` | Index new mail (headers only, read-only — never marks mail read) |
| `account_inventory report` | Accounts grouped: mostly-used / unused / dormant / useless |
| `account_inventory unused` | Just the ones to close/cancel |
| `account_inventory useless` | Unsubscribe candidates |
| `mail_store search "invoice"` | Search your sealed index |
| `email_triage report` | good / marketing / spam pass on recent mail |

Through Vera (agent + voice), the same capabilities are the skills **sync_email,
account_inventory, unused_accounts, search_email, triage_inbox**.

## Privacy, restated

- **Read-only.** IMAP opens the mailbox read-only with `BODY.PEEK`; Vera never
  marks, moves, or deletes anything.
- **Headers only** by default — enough to know your accounts, without storing
  message bodies.
- **Sealed on-device.** Every indexed message is encrypted at rest with your
  device-bound key; the index reads as noise off this Mac.
- **No third party.** Mail travels only between this Mac and Google. There is no
  Vera server. The LLM that reasons over it runs locally.
- **Suggests, never acts.** Vera flags accounts to close/unsubscribe; it never
  unsubscribes, closes, or sends on its own.

Check any time: `python3 -m cognitive_twin.security doctor`.
