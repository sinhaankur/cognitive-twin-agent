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

The doctor runs six checks and prints ✓/✗ for each, then a single verdict:

1. **Data sealed at rest** — every personal store sealed + owner-only.
2. **Secrets in Keychain** — no plaintext credentials in the environment.
3. **Key protection** — the sealing key is in the macOS Keychain (device-bound).
4. **Network egress** — scans the code; every network call goes to *your* Gmail /
   Google OAuth, nothing else. The LLM stays local. Any new/unknown egress is
   flagged for review.
5. **Git hygiene** — no secret, token, or sealed file is tracked by git.
6. **Local HTTP surface** — the Mind/Brain viz server binds `127.0.0.1` only
   (never off-machine), and state-changing endpoints are **POST + same-origin**
   so no page you visit can change Vera behind your back (CSRF closed).

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

**The one cloud door — Claude, doubly opt-in.** If you already have Claude, Vera
can borrow it for a turn — but only after two deliberate acts: an Anthropic API
key must exist (Keychain `ANTHROPIC_API_KEY`, or env), **and** the switch must be
on (`CTWIN_USE_CLAUDE=1`, or `"claude": {"enabled": true}` in `agent_config.json`).
Either one alone does nothing. Cloud models always appear as `claude/…` in the
picker and in every route readout, so a cloud turn is never silent; the policy
router never auto-picks them (`allowCloudFallback` stays `false`).

## The one narrow network touchpoint: connectors you turn on

Some capabilities (Gmail) must talk to *your* provider over the network — that's
unavoidable for any email client. When you connect one:

- **Gmail OAuth** (`gmail_oauth.py`): the OAuth tokens are sealed with the same
  device-bound key (`gmail_token.sealed`, `0600`). Email content only ever travels
  between your Mac and Google to fetch/send it — never to any third party, never
  to a Vera server (there isn't one). Everything Vera *derives* (the local index,
  summaries, drafts, account inventory) stays sealed on this device.

## Portability + multiple devices (design)

**Today (works):** `vault export <file>` writes one bundle, re-encrypted under a
passphrase *you* choose (PBKDF2-SHA256, 600k rounds). On the other device `vault
import <file>` unpacks it and immediately re-seals everything under *that* device's
key. You move it however you like; it's ciphertext the whole way.

**The invariant that makes multi-device safe:** each device holds its own at-rest
key in its own Keychain, and **no key ever leaves a device**. Only the
passphrase-encrypted bundle travels. A device compromise therefore stays contained
to that one device — there is no shared key that unlocks the fleet.

**Two private transports** (Vera never uses a third-party server for this):

1. **iCloud private** — the encrypted bundle is written to *your* iCloud Drive.
   Apple relays the ciphertext between your devices end-to-end; it's unreadable to
   Apple and to us (there is no "us" — no Vera server). Works offline-asynchronously
   (drop on A, pick up on B whenever it next syncs).
2. **Direct device-to-device** — devices exchange the bundle over your local
   network (AirDrop-style / a paired local link). No cloud at all; requires both
   devices online and near each other.

**What automatic sync still needs (not yet built), on top of this foundation:**

- **Merge, not overwrite.** `import` currently overwrites. Append-only logs
  (`memory.jsonl`, `places.jsonl`, `mail.jsonl`) merge cleanly by
  timestamp/dedupe; single-document STATE files need a last-writer-wins (or
  field-level) merge. This is the real engineering.
- **Device trust / pairing.** A step to enrol a new device (e.g. a one-time code
  shown on device A, entered on device B) so only *your* devices ever join.
- **Conflict visibility.** If two devices edited the same STATE offline, surface
  it rather than silently pick one.

None of this changes the security kernel (`security.py`) or the sealed stores —
sync is a layer *above* the one sealed path, which is exactly why the foundation
was built first. A per-device diagram is in the project [README](./README.md).

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
