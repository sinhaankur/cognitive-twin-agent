# Security — Vera's kernel

Vera holds your life: your memory, how you work, where you go, and (opt-in) your
email. The rule is simple and absolute:

> **Everything personal is sealed at rest, on this machine, and reasoned over
> on-device. Nothing leaves your computer unless you explicitly allow it.**

This is not a feature; it's the kernel. Every personal store routes through one
guarded path so "secured" is the default and the *only* path — never a thing a
module has to remember.

## The kernel: `cognitive_twin/security.py`

All personal data goes to disk through the kernel, which always seals it:

- **STATE** (single JSON docs — mood, rhythms, soul, persona, activity summary):
  `security.write_state(path, obj)` / `read_state(path, default)`.
- **LOG** (append-only JSONL — activity samples, places/visits, mail index):
  `security.append_line(path, obj)` / `read_lines(path)`.

No feature writes personal data to a file directly. If you add a personal store,
add it to `STATE_STORES` / `LOG_STORES` in `security.py` and use these functions —
that's the whole contract.

## How the sealing works: `cognitive_twin/vault.py`

- **Cipher:** ChaCha20-Poly1305 (RFC 8439), implemented in pure stdlib — no new
  crypto dependency.
- **Key:** a random 32-byte secret in the **macOS login Keychain**, which the OS
  binds to *this Mac + this account*. Off-Mac (or no Keychain), the key derives
  from the machine's identity + username + a local random salt.
- **Result:** copy any of Vera's files to another machine or account and they read
  as **noise**. There is nothing to decrypt them with elsewhere.
- **Permissions:** every file the kernel creates is `0600` (owner-only). The audit
  flags anything group/other-readable.

## Verify it yourself

**One command for the whole answer:**

```bash
python3 -m cognitive_twin.security doctor      # "am I safe?" — one verdict
```

The doctor runs five checks and prints ✓/✗ for each, then a single verdict:

1. **Data sealed at rest** — every personal store sealed + owner-only.
2. **Secrets in Keychain** — no plaintext credentials in the environment.
3. **Key protection** — the sealing key is in the macOS Keychain (device-bound).
4. **Network egress** — scans the code; every network call goes to *your* Gmail /
   Google OAuth, nothing else. The LLM stays local. Any new/unknown egress is
   flagged for review.
5. **Git hygiene** — no secret, token, or sealed file is tracked by git.

Finer-grained tools:

```bash
python3 -m cognitive_twin.security audit          # per-store at-rest state
python3 -m cognitive_twin.security seal-all        # seal anything still plaintext (idempotent)
python3 -m cognitive_twin.secrets_store audit      # per-secret: keychain / env-plaintext / absent
```

`audit` reports each store as `sealed` / `PLAINTEXT` / `absent` / `empty`, and
warns on world-readable files. `seal-all` self-heals: it reads any legacy
plaintext store and re-seals it in place, without losing data.

## Secrets live in the Keychain, not `.env`

Credentials (`IMAP_PASSWORD`, the OAuth client secret) belong in the macOS
Keychain, not a plaintext `.env`. Move them once:

```bash
python3 -m cognitive_twin.secrets_store set IMAP_PASSWORD        # hidden prompt
python3 -m cognitive_twin.secrets_store migrate                  # or: move known .env secrets in
```

Then delete those lines from `.env`. Code reads secrets via
`secrets_store.get(name)` — Keychain first, environment only as a legacy fallback
(and it migrates an env-only value into the Keychain when it sees one).

## Reasoning stays on-device

Vera reasons with a **local LLM** (Ollama / an OpenAI-compatible local server).
Your personal data is fed to that local model at runtime — it is not sent to a
cloud API by default, and it is never used to train anything.

## The one narrow network touchpoint: connectors you turn on

Some capabilities (Gmail) must talk to *your* provider over the network — that's
unavoidable for any email client. When you connect one:

- **Gmail OAuth** (`gmail_oauth.py`): the OAuth tokens are sealed with the same
  device-bound key (`gmail_token.sealed`, `0600`). Email content only ever travels
  between your Mac and Google to fetch/send it — never to any third party, never
  to a Vera server (there isn't one). Everything Vera *derives* (the local index,
  summaries, drafts, account inventory) stays sealed on this device.

## Portability, when *you* choose it: `ctwin vault export/import`

To move Vera to a new machine, `vault export <file>` writes one bundle,
re-encrypted under a passphrase *you* choose (PBKDF2-SHA256, 600k rounds). On the
new device `vault import <file>` unpacks it and immediately re-seals everything
under *that* device's key. You move it however you like; it's ciphertext the whole
way.

## Honest threat model

At-rest sealing protects your **files** — backups, a copied disk, another account
on the same Mac, a lost laptop. It **cannot** protect against code running as you
on an unlocked session; that is the operating system's job, and we don't pretend
otherwise. What Vera guarantees is the part Vera controls: your data is sealed,
owner-only, on-device, and never leaves without your explicit action.

## Reporting

This is a personal, single-author project (© Ankur Sinha). If you find a way that
personal data could be written unsealed, leaked off-device, or read from another
account, that's a kernel bug — treat it as the highest priority and fix the path
in `security.py`, not the symptom in a feature.
