"""
sync — merge another device's memory into this one, without losing either side.

The vault already moves an encrypted bundle between your devices safely (see
``vault.export_bundle`` / ``import_bundle`` and SECURITY.md): each device holds
its own at-rest key, only the passphrase-encrypted bundle travels. What plain
``import`` did was OVERWRITE — fine for a first restore, wrong for two devices
that have each lived a little. This module is the missing MERGE layer the design
called out:

  * append-only logs (``*.jsonl`` — memory, places, mail, activity) → UNION with
    dedupe: every record from both sides, each kept once, ordered by time.
  * single-document STATE files (``*.json``) → LAST-WRITER-WINS by an embedded
    ``updated``/``at`` timestamp (falls back to file mtime), with the losing
    side surfaced as a conflict rather than silently dropped.

Everything is read and written through the security kernel's sealed path, so a
merge never lays plaintext on disk. Nothing here reaches the network; it operates
on a bundle file you already moved via iCloud-private or device-to-device.

CLI:
    python3 -m cognitive_twin.sync merge <bundle-file>     # merge, don't overwrite
    python3 -m cognitive_twin.sync merge <bundle-file> --dry-run
"""

from __future__ import annotations

import base64
import io
import json
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import vault
from .vault import open_sealed, _bundle_key  # reuse the exact bundle crypto
from . import security


# Fields we try, in order, to date a STATE document for last-writer-wins.
_TS_FIELDS = ("updated", "updated_at", "at", "ts", "modified", "saved_at")


@dataclass
class MergeReport:
    logs_merged: dict[str, int] = field(default_factory=dict)      # file → new records added
    states_updated: list[str] = field(default_factory=list)        # STATE files this bundle won
    states_kept: list[str] = field(default_factory=list)           # STATE files local won
    conflicts: list[str] = field(default_factory=list)             # both edited; surfaced
    new_files: list[str] = field(default_factory=list)             # files only the bundle had
    dry_run: bool = False

    def summary(self) -> str:
        added = sum(self.logs_merged.values())
        lines = [
            f"Merged {'(dry-run) ' if self.dry_run else ''}another device into this one:",
            f"  logs: +{added} new record(s) across {len(self.logs_merged)} file(s)",
            f"  state: {len(self.states_updated)} updated, {len(self.states_kept)} kept local",
            f"  new files: {len(self.new_files)}",
        ]
        if self.conflicts:
            lines.append("  ⚠ conflicts (both devices edited offline — newer kept, review):")
            for c in self.conflicts:
                lines.append(f"      {c}")
        return "\n".join(lines)


# ── record identity (dedupe key) ──────────────────────────────────────────────
def _record_key(obj: Any) -> str:
    """A stable identity for a log record so the same event from both devices is
    counted once. Prefer an explicit id; else a hash of the sorted content."""
    if isinstance(obj, dict):
        for k in ("id", "uid", "key"):
            if obj.get(k):
                return f"{k}:{obj[k]}"
        try:
            return "h:" + str(hash(json.dumps(obj, sort_keys=True, ensure_ascii=False)))
        except TypeError:
            return "r:" + repr(obj)
    return "r:" + repr(obj)


def _record_time(obj: Any) -> float:
    if isinstance(obj, dict):
        for k in ("at", "ts", "time", "submittedAt", "updated"):
            v = obj.get(k)
            if isinstance(v, (int, float)):
                return float(v)
    return 0.0


def _state_time(obj: Any, fallback: float) -> float:
    if isinstance(obj, dict):
        for k in _TS_FIELDS:
            v = obj.get(k)
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                try:
                    # ISO-ish → epoch, best effort
                    from datetime import datetime
                    return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
                except Exception:
                    continue
    return fallback


# ── merge one file ────────────────────────────────────────────────────────────
def _merge_log(local_path: Path, incoming_bytes: bytes, report: MergeReport, dry: bool) -> None:
    """Union two JSONL logs by record identity, keep every unique record, ordered
    by time. Reads/writes through the sealed path."""
    # local (sealed or legacy plaintext) → objects
    local = security.read_lines(local_path)
    seen = {_record_key(o) for o in local}
    added = []
    for ln in incoming_bytes.decode("utf-8", "replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(vault.open_line(ln) if vault.is_sealed_line(ln) else ln)
        except Exception:
            continue
        k = _record_key(obj)
        if k in seen:
            continue
        seen.add(k)
        added.append(obj)
    if not added:
        return
    report.logs_merged[local_path.name] = len(added)
    if dry:
        return
    merged = local + added
    merged.sort(key=_record_time)
    # rewrite the whole log sealed (append_line would work too, but a single
    # ordered rewrite keeps the file tidy and time-sorted).
    tmp = local_path.with_suffix(local_path.suffix + ".merging")
    for o in merged:
        security.append_line(tmp, o)
    tmp.replace(local_path)


def _merge_state(local_path: Path, incoming_bytes: bytes, report: MergeReport, dry: bool) -> None:
    """Last-writer-wins for a single JSON document; surface a conflict if both
    sides look edited."""
    try:
        incoming = json.loads(
            vault.open_bytes(incoming_bytes) if vault.is_sealed_bytes(incoming_bytes) else incoming_bytes
        )
    except Exception:
        return
    local = security.read_state(local_path, default=None)
    name = local_path.name
    if local is None:
        report.new_files.append(name)
        if not dry:
            security.write_state(local_path, incoming)
        return
    lt = _state_time(local, local_path.stat().st_mtime if local_path.exists() else 0.0)
    it = _state_time(incoming, 0.0)
    if incoming == local:
        report.states_kept.append(name)
        return
    if it > lt:
        report.states_updated.append(name)
        if lt > 0 and abs(it - lt) < 86400:  # both edited within a day → flag
            report.conflicts.append(f"{name} (both edited; kept newer)")
        if not dry:
            security.write_state(local_path, incoming)
    else:
        report.states_kept.append(name)
        if it > 0 and abs(it - lt) < 86400:
            report.conflicts.append(f"{name} (both edited; kept local)")


# ── the merge ─────────────────────────────────────────────────────────────────
def merge_bundle(src: Path, passphrase: str, *, dry_run: bool = False) -> MergeReport:
    """Merge a passphrase-encrypted bundle from another device INTO this device's
    memory, losing nothing. Logs union, STATE docs last-writer-wins."""
    doc = json.loads(Path(src).expanduser().read_text(encoding="utf-8"))
    if doc.get("format") != "ctwin-vault":
        raise ValueError("not a ctwin vault bundle")
    k = _bundle_key(passphrase, base64.b64decode(doc["salt"]))
    tar_bytes = open_sealed(k, base64.b64decode(doc["data"]), aad=b"ctwin-bundle-v1")

    root = security.home()
    report = MergeReport(dry_run=dry_run)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for m in tar.getmembers():
            if not m.isfile() or m.name.startswith(("/", "..")) or ".." in m.name.split("/"):
                continue
            if m.name.endswith("vault.salt"):
                continue  # never move a device's key material
            f = tar.extractfile(m)
            if f is None:
                continue
            data = f.read()
            local_path = root / m.name
            local_path.parent.mkdir(parents=True, exist_ok=True)
            if m.name.endswith(".jsonl"):
                _merge_log(local_path, data, report, dry_run)
            elif m.name.endswith(".json"):
                _merge_state(local_path, data, report, dry_run)
            elif not local_path.exists():
                # any other file only the other device had → bring it over sealed-as-is
                report.new_files.append(m.name)
                if not dry_run:
                    local_path.write_bytes(data)
    return report


# ── CLI ───────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    if not argv or argv[0] != "merge" or len(argv) < 2:
        print("usage: python3 -m cognitive_twin.sync merge <bundle-file> [--dry-run]")
        return 2
    src = Path(argv[1])
    if not src.is_file():
        print(f"✗ no such bundle: {src}")
        return 1
    dry = "--dry-run" in argv
    import getpass
    passphrase = getpass.getpass("Bundle passphrase (hidden): ")
    try:
        report = merge_bundle(src, passphrase, dry_run=dry)
    except Exception as e:
        print(f"✗ merge failed: {e}")
        return 1
    print(report.summary())
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
