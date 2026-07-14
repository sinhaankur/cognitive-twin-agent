"""
Vault tests — memory sealed at rest (device+account key) and the portable
passphrase bundle for moving to another device. Pure module: the tests pin
the key so they never touch the real Keychain, and point CTWIN_MEMORY_DIR at
a scratch folder so they never touch real memory.

Run: python -m pytest tests/ -q   (or: python tests/test_vault.py)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cognitive_twin import vault

KEY_A = b"\x42" * 32
KEY_B = b"\x43" * 32


def _scratch() -> Path:
    d = Path(tempfile.mkdtemp(prefix="ctwin-vault-test-"))
    os.environ["CTWIN_MEMORY_DIR"] = str(d)
    vault._key_cache = KEY_A
    return d


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except Exception:
        return True


def test_rfc8439_self_test():
    vault._self_test()                  # raises if the cipher is broken


def test_line_roundtrip():
    _scratch()
    line = json.dumps({"prompt": "mom's birthday is june 3", "type": "knowledge"})
    sealed = vault.seal_line(line)
    assert vault.is_sealed_line(sealed)
    assert "birthday" not in sealed
    assert vault.open_line(sealed) == line


def test_two_seals_differ_but_open_the_same():
    _scratch()
    a, b = vault.seal_line("same text"), vault.seal_line("same text")
    assert a != b                       # fresh nonce every time
    assert vault.open_line(a) == vault.open_line(b) == "same text"


def test_tamper_detected():
    _scratch()
    sealed = vault.seal_line("truth")
    broken = sealed[:-4] + ("AAAA" if not sealed.endswith("AAAA") else "BBBB")
    assert _raises(lambda: vault.open_line(broken))


def test_wrong_key_refuses():
    _scratch()
    sealed = vault.seal_line("secret")
    vault._key_cache = KEY_B            # another device's key
    assert _raises(lambda: vault.open_line(sealed))


def test_file_roundtrip():
    _scratch()
    data = json.dumps({"k": 3}).encode()
    sealed = vault.seal_bytes(data)
    assert vault.is_sealed_bytes(sealed)
    assert vault.open_bytes(sealed) == data


def test_migrate_seals_plaintext_lines():
    d = _scratch()
    f = d / "memory.jsonl"
    f.write_text('{"prompt": "old plain memory"}\n' + vault.seal_line('{"prompt": "new"}') + "\n")
    assert vault.migrate_jsonl(f) == 1
    assert all(vault.is_sealed_line(ln) for ln in f.read_text().splitlines())
    assert vault.migrate_jsonl(f) == 0  # second run: nothing left to do


def test_memory_records_sealed_and_reads_back():
    d = _scratch()
    from cognitive_twin import memory
    memory.record("remember the anniversary", "noted", source="test")
    assert "anniversary" not in (d / "memory.jsonl").read_text()   # sealed on disk
    got = memory.entries()
    assert got and got[-1]["prompt"] == "remember the anniversary"


def test_export_import_roundtrip():
    d = _scratch()
    from cognitive_twin import memory
    memory.record("dad's birthday is in may", "noted", source="test")
    bundle = d / "move.ctwin-vault"
    r = vault.export_bundle(bundle, "correct horse")
    assert r["files"] >= 1
    assert "birthday" not in bundle.read_text()    # the bundle leaks nothing

    # "another device": different at-rest key, fresh memory dir
    other = Path(tempfile.mkdtemp(prefix="ctwin-vault-other-"))
    os.environ["CTWIN_MEMORY_DIR"] = str(other)
    vault._key_cache = KEY_B
    vault.import_bundle(bundle, "correct horse")
    got = memory.entries()
    assert any(e["prompt"] == "dad's birthday is in may" for e in got)
    # and it landed re-sealed for the new device
    assert "birthday" not in (other / "memory.jsonl").read_text()


def test_import_wrong_passphrase_or_short():
    d = _scratch()
    from cognitive_twin import memory
    memory.record("private thing", "noted", source="test")
    assert _raises(lambda: vault.export_bundle(d / "x.ctwin-vault", "tiny"))  # short pass
    bundle = d / "move.ctwin-vault"
    vault.export_bundle(bundle, "right one")
    other = Path(tempfile.mkdtemp(prefix="ctwin-vault-else-"))
    os.environ["CTWIN_MEMORY_DIR"] = str(other)
    assert _raises(lambda: vault.import_bundle(bundle, "wrong one"))


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items())
           if n.startswith("test_") and callable(g)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
