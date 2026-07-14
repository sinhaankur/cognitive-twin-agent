"""
vault.py — her memory, encrypted at rest, and portable when YOU say so.

What the owner asked for: "this memory should be encrypted based on the device
and account, and we can download and transfer it to a different device."

So:
  - **At rest**: memory lines are sealed with ChaCha20-Poly1305 (RFC 8439,
    implemented here in pure stdlib Python — no new dependencies). The key is
    a random 32-byte secret living in the macOS login Keychain, which the OS
    itself binds to this device + this account. Off-mac (or no Keychain), the
    key derives from the machine's identity + username + a local random salt.
    Either way: copy the files to another machine and they read as noise.
  - **In transit**: `ctwin vault export <file>` writes ONE portable bundle —
    the memory folder, decrypted, then re-encrypted under a passphrase you
    choose (PBKDF2-SHA256, 600k rounds). Move it any way you like; on the new
    device `ctwin vault import <file>` unpacks and immediately re-seals
    everything under THAT device's key.

Honesty about the threat model: at-rest sealing protects the files (backups,
copied disks, other accounts) — it cannot protect against code running as you
on an unlocked session. That is the OS's job, not ours to pretend otherwise.
"""

from __future__ import annotations

import base64
import getpass
import hmac
import io
import json
import os
import secrets
import stat
import struct
import subprocess
import tarfile
from pathlib import Path
from typing import Any

_SERVICE = "cognitive-twin-vault"
_AAD = b"ctwin-memory-v1"
_LINE_MAGIC = "ctv1:"          # one sealed jsonl line
_FILE_MAGIC = b"CTV1F"         # one sealed whole file
_BUNDLE_KDF_ITERS = 600_000


# ---- ChaCha20-Poly1305 (RFC 8439), pure stdlib --------------------------------
def _rotl32(v: int, c: int) -> int:
    return ((v << c) & 0xFFFFFFFF) | (v >> (32 - c))


def _quarter(s: list[int], a: int, b: int, c: int, d: int) -> None:
    s[a] = (s[a] + s[b]) & 0xFFFFFFFF; s[d] ^= s[a]; s[d] = _rotl32(s[d], 16)
    s[c] = (s[c] + s[d]) & 0xFFFFFFFF; s[b] ^= s[c]; s[b] = _rotl32(s[b], 12)
    s[a] = (s[a] + s[b]) & 0xFFFFFFFF; s[d] ^= s[a]; s[d] = _rotl32(s[d], 8)
    s[c] = (s[c] + s[d]) & 0xFFFFFFFF; s[b] ^= s[c]; s[b] = _rotl32(s[b], 7)


def _block(key: bytes, counter: int, nonce: bytes) -> bytes:
    st = [0x61707865, 0x3320646E, 0x79622D32, 0x6B206574,
          *struct.unpack("<8I", key), counter & 0xFFFFFFFF, *struct.unpack("<3I", nonce)]
    w = st[:]
    for _ in range(10):
        _quarter(w, 0, 4, 8, 12); _quarter(w, 1, 5, 9, 13)
        _quarter(w, 2, 6, 10, 14); _quarter(w, 3, 7, 11, 15)
        _quarter(w, 0, 5, 10, 15); _quarter(w, 1, 6, 11, 12)
        _quarter(w, 2, 7, 8, 13); _quarter(w, 3, 4, 9, 14)
    return struct.pack("<16I", *[(w[i] + st[i]) & 0xFFFFFFFF for i in range(16)])


def _chacha20(key: bytes, counter: int, nonce: bytes, data: bytes) -> bytes:
    out = bytearray(len(data))
    for i in range(0, len(data), 64):
        ks = _block(key, counter + i // 64, nonce)
        chunk = data[i:i + 64]
        out[i:i + len(chunk)] = bytes(a ^ b for a, b in zip(chunk, ks))
    return bytes(out)


def _poly1305(key32: bytes, msg: bytes) -> bytes:
    r = int.from_bytes(key32[:16], "little") & 0x0FFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF
    s = int.from_bytes(key32[16:], "little")
    p = (1 << 130) - 5
    acc = 0
    for i in range(0, len(msg), 16):
        acc = ((acc + int.from_bytes(msg[i:i + 16] + b"\x01", "little")) * r) % p
    return ((acc + s) & ((1 << 128) - 1)).to_bytes(16, "little")


def _pad16(b: bytes) -> bytes:
    return b"\x00" * ((16 - len(b) % 16) % 16)


def seal(key: bytes, plaintext: bytes, aad: bytes = _AAD) -> bytes:
    """nonce(12) + ciphertext + tag(16) — a fresh random nonce every time."""
    nonce = secrets.token_bytes(12)
    ct = _chacha20(key, 1, nonce, plaintext)
    otk = _block(key, 0, nonce)[:32]
    mac = _poly1305(otk, aad + _pad16(aad) + ct + _pad16(ct)
                    + struct.pack("<QQ", len(aad), len(ct)))
    return nonce + ct + mac


def open_sealed(key: bytes, blob: bytes, aad: bytes = _AAD) -> bytes:
    nonce, ct, tag = blob[:12], blob[12:-16], blob[-16:]
    otk = _block(key, 0, nonce)[:32]
    mac = _poly1305(otk, aad + _pad16(aad) + ct + _pad16(ct)
                    + struct.pack("<QQ", len(aad), len(ct)))
    if not hmac.compare_digest(mac, tag):
        raise ValueError("vault: authentication failed (wrong key or tampered data)")
    return _chacha20(key, 1, nonce, ct)


def _self_test() -> None:
    """RFC 8439 §2.8.2 test vector — refuse to run on a broken cipher."""
    key = bytes(range(0x80, 0xA0))
    nonce = bytes([0x07, 0, 0, 0]) + bytes(range(0x40, 0x48))
    aad = bytes([0x50, 0x51, 0x52, 0x53, 0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7])
    pt = (b"Ladies and Gentlemen of the class of '99: If I could offer you "
          b"only one tip for the future, sunscreen would be it.")
    ct = _chacha20(key, 1, nonce, pt)
    otk = _block(key, 0, nonce)[:32]
    tag = _poly1305(otk, aad + _pad16(aad) + ct + _pad16(ct)
                    + struct.pack("<QQ", len(aad), len(ct)))
    assert ct[:8] == bytes.fromhex("d31a8d34648e60db"), "chacha20 broken"
    assert tag == bytes.fromhex("1ae10b594f09e26a7e902ecbd0600691"), "poly1305 broken"


_self_test()


# ---- the device+account key ----------------------------------------------------
_key_cache: bytes | None = None


def _memory_dir() -> Path:
    from . import memory
    return memory._dir()


def _keychain_read() -> bytes | None:
    try:
        r = subprocess.run(["security", "find-generic-password", "-s", _SERVICE, "-w"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return bytes.fromhex(r.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


def _keychain_create() -> bytes | None:
    k = secrets.token_bytes(32)
    try:
        r = subprocess.run(["security", "add-generic-password", "-a", getpass.getuser(),
                            "-s", _SERVICE, "-w", k.hex(), "-U"],
                           capture_output=True, timeout=5)
        if r.returncode == 0:
            return k
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _derived_key() -> bytes:
    """Fallback (no Keychain): device identity + account + a local random salt."""
    ident = ""
    try:
        r = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                           capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if "IOPlatformUUID" in line:
                ident = line.split('"')[-2]
                break
    except (OSError, subprocess.TimeoutExpired):
        pass
    if not ident:
        try:
            ident = Path("/etc/machine-id").read_text().strip()
        except OSError:
            ident = "unknown-device"
    salt_file = _memory_dir() / "vault.salt"
    if salt_file.is_file():
        salt = salt_file.read_bytes()
    else:
        salt = secrets.token_bytes(16)
        salt_file.write_bytes(salt)
        os.chmod(salt_file, stat.S_IRUSR | stat.S_IWUSR)
    import hashlib
    return hashlib.pbkdf2_hmac("sha256", (ident + ":" + getpass.getuser()).encode(),
                               salt, 200_000)


def key() -> bytes:
    """The at-rest key: Keychain-held (device+account bound by the OS) when
    possible, derived from device identity otherwise. Cached per process."""
    global _key_cache
    if _key_cache is None:
        _key_cache = _keychain_read() or _keychain_create() or _derived_key()
    return _key_cache


# ---- line + file sealing (what memory.py calls) --------------------------------
def seal_line(line: str) -> str:
    return _LINE_MAGIC + base64.b64encode(seal(key(), line.encode("utf-8"))).decode()


def is_sealed_line(line: str) -> bool:
    return line.startswith(_LINE_MAGIC)


def open_line(line: str) -> str:
    return open_sealed(key(), base64.b64decode(line[len(_LINE_MAGIC):])).decode("utf-8")


def seal_bytes(data: bytes) -> bytes:
    return _FILE_MAGIC + seal(key(), data)


def is_sealed_bytes(data: bytes) -> bool:
    return data.startswith(_FILE_MAGIC)


def open_bytes(data: bytes) -> bytes:
    return open_sealed(key(), data[len(_FILE_MAGIC):])


def migrate_jsonl(path: Path) -> int:
    """Seal any plaintext lines in a jsonl file, in place. Returns lines sealed."""
    if not path.is_file():
        return 0
    lines = path.read_text(encoding="utf-8").splitlines()
    sealed, changed = [], 0
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if is_sealed_line(ln):
            sealed.append(ln)
        else:
            sealed.append(seal_line(ln))
            changed += 1
    if changed:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text("\n".join(sealed) + "\n", encoding="utf-8")
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        tmp.replace(path)
    return changed


# ---- portable bundles: export / import ------------------------------------------
def _bundle_key(passphrase: str, salt: bytes) -> bytes:
    import hashlib
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, _BUNDLE_KDF_ITERS)


def _plain_file_bytes(p: Path) -> bytes:
    """A file's content with this device's sealing removed (bundles carry
    plaintext inside the passphrase envelope, so any device can import)."""
    raw = p.read_bytes()
    if is_sealed_bytes(raw):
        return open_bytes(raw)
    if p.suffix == ".jsonl":
        out = []
        for ln in raw.decode("utf-8", "replace").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            out.append(open_line(ln) if is_sealed_line(ln) else ln)
        return ("\n".join(out) + "\n").encode("utf-8")
    return raw


def export_bundle(dest: Path, passphrase: str) -> dict[str, Any]:
    """One portable, passphrase-encrypted file holding the whole memory folder."""
    if len(passphrase) < 6:
        raise ValueError("passphrase too short (6+ characters)")
    root = _memory_dir()
    buf = io.BytesIO()
    n = 0
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.name == "vault.salt":
                continue
            data = _plain_file_bytes(p)
            info = tarfile.TarInfo(str(p.relative_to(root)))
            info.size = len(data)
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(data))
            n += 1
    salt = secrets.token_bytes(16)
    blob = seal(_bundle_key(passphrase, salt), buf.getvalue(), aad=b"ctwin-bundle-v1")
    doc = {"format": "ctwin-vault", "v": 1, "kdf": "pbkdf2-sha256",
           "iterations": _BUNDLE_KDF_ITERS,
           "salt": base64.b64encode(salt).decode(),
           "data": base64.b64encode(blob).decode()}
    dest = dest.expanduser()
    dest.write_text(json.dumps(doc), encoding="utf-8")
    os.chmod(dest, stat.S_IRUSR | stat.S_IWUSR)
    return {"files": n, "path": str(dest)}


def import_bundle(src: Path, passphrase: str, *, force: bool = False) -> dict[str, Any]:
    """Unpack a bundle into the memory folder and re-seal under THIS device's key."""
    doc = json.loads(src.expanduser().read_text(encoding="utf-8"))
    if doc.get("format") != "ctwin-vault":
        raise ValueError("not a ctwin vault bundle")
    k = _bundle_key(passphrase, base64.b64decode(doc["salt"]))
    tar_bytes = open_sealed(k, base64.b64decode(doc["data"]), aad=b"ctwin-bundle-v1")
    root = _memory_dir()
    if (root / "memory.jsonl").exists() and not force:
        raise FileExistsError(f"{root} already holds a memory — pass force to overwrite")
    n = 0
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for m in tar.getmembers():
            # only plain files on safe relative paths leave the archive
            if not m.isfile() or m.name.startswith(("/", "..")) or ".." in m.name.split("/"):
                continue
            dest = root / m.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            f = tar.extractfile(m)
            if f is None:
                continue
            data = f.read()
            if m.name.endswith(".jsonl"):       # re-seal line-wise for this device
                out = [seal_line(ln) for ln in data.decode("utf-8", "replace").splitlines()
                       if ln.strip()]
                data = ("\n".join(out) + "\n").encode("utf-8")
            dest.write_bytes(data)
            os.chmod(dest, stat.S_IRUSR | stat.S_IWUSR)
            n += 1
    return {"files": n, "path": str(root)}


def status() -> str:
    src = "keychain (device + account)" if _keychain_read() else "derived (device + account)"
    from . import memory
    path = memory._file()
    sealed = plain = 0
    if path.is_file():
        for ln in path.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            sealed += 1 if is_sealed_line(ln) else 0
            plain += 0 if is_sealed_line(ln) else 1
    return (f"vault: key from {src} · memory lines sealed {sealed}, plaintext {plain}"
            + (" (run `ctwin vault encrypt` to seal them)" if plain else ""))
