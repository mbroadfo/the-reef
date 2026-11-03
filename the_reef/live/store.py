"""Durable local ledger storage: an append-only JSONL file, a single-writer lock and independent checkpoints.

``FileEventStore`` satisfies the ``EventStore`` contract in ``the_reef.ledger.ledger``:

* Appends are atomic from the reader's point of view: one ``write`` of one newline-terminated line, flushed and
  ``fsync``ed before ``append`` returns. A crash can leave at most one *torn* last line. That line was never
  acknowledged, so on the next writer start it is moved aside (never silently dropped) and the ledger continues
  from the last intact event. A torn line is never read as an event.
* There is no update or delete path. ``seq`` must be previous + 1 and ``event_id`` must be new.
* One writer at a time: ``WriterLock`` holds an OS byte-range lock that the kernel releases when the process dies,
  so a crash never leaves a stale lock behind.
* After each append the new head is written to a ``CheckpointLog`` that can live in a different directory or on a
  different drive. ``Ledger(store, expected=log.latest())`` then detects tail truncation, which the hash chain alone
  cannot.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from the_reef.ledger.events import GENESIS_HASH, EventDraft, EventKind, LedgerEvent, canonical, digest
from the_reef.ledger.ledger import Checkpoint, TruncationError
from the_reef.ledger.state import LedgerError


class WriterBusy(RuntimeError):
    """Another process holds the writer lock."""


class StoreCorrupt(LedgerError):
    """A line in the middle of the ledger file cannot be read. Never repaired automatically."""


def _fsync_dir(path: Path) -> None:
    try:  # not supported on Windows
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write(path: Path, text: str) -> None:
    """Write a whole file so a reader sees the old content or the new content, never a mixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    for attempt in range(8):  # Windows: an indexer or antivirus can hold the new file for a moment
        try:
            os.replace(tmp, path)
            break
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.05 * (attempt + 1))
    _fsync_dir(path.parent)


# --- single-writer lock -----------------------------------------------------------------------------------

class WriterLock:
    """Exclusive, non-blocking, OS-level lock. Released by the kernel if the holder dies."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh = None

    def __enter__(self) -> "WriterLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt  # noqa: PLC0415

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl  # noqa: PLC0415

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            holder = ""
            try:
                holder = Path(str(self.path) + ".info").read_text(encoding="utf-8")
            except OSError:
                pass
            fh.close()
            raise WriterBusy(f"another process is writing {self.path.parent.name} {holder}".strip()) from exc
        self._fh = fh
        # Diagnostics only (the lock is the byte range, not this file).
        try:
            Path(str(self.path) + ".info").write_text(
                f"(pid {os.getpid()} on {socket.gethostname()} since {datetime.now(timezone.utc).isoformat()})", encoding="utf-8")
        except OSError:
            pass
        return self

    def __exit__(self, *exc: object) -> None:
        fh, self._fh = self._fh, None
        if fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt  # noqa: PLC0415

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl  # noqa: PLC0415

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


# --- checkpoints ----------------------------------------------------------------------------------------------

class CheckpointLog:
    """Append-only record of ledger heads, kept apart from the ledger file. Each line commits to the one before it,
    so rewriting an earlier checkpoint is detectable too."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _lines(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                out.append(json.loads(raw))
        return out

    def entries(self) -> list[dict]:
        return self._lines()

    def latest(self) -> Checkpoint | None:
        lines = self._lines()
        return Checkpoint(int(lines[-1]["seq"]), str(lines[-1]["head_hash"])) if lines else None

    @staticmethod
    def _sha(prev: str, seq: int, head: str, at: str) -> str:
        return digest(f"{prev}|{seq}|{head}|{at}")

    def verify_self(self) -> list[str]:
        problems, prev, last_seq = [], "", 0
        try:
            lines = self._lines()
        except (ValueError, KeyError) as exc:
            return [f"checkpoint log unreadable: {exc}"]
        for i, ln in enumerate(lines, 1):
            if ln.get("prev") != prev or ln.get("sha") != self._sha(prev, int(ln["seq"]), str(ln["head_hash"]), str(ln["at"])):
                problems.append(f"checkpoint line {i} does not chain to the one before it")
            if int(ln["seq"]) < last_seq:
                problems.append(f"checkpoint line {i} goes backwards ({ln['seq']} < {last_seq})")
            prev, last_seq = str(ln.get("sha")), int(ln["seq"])
        return problems

    def record(self, cp: Checkpoint, at: datetime | None = None) -> None:
        lines = self._lines()
        if lines and lines[-1]["seq"] == cp.seq and lines[-1]["head_hash"] == cp.head_hash:
            return
        stamp = (at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        prev = str(lines[-1]["sha"]) if lines else ""
        row = {"seq": cp.seq, "head_hash": cp.head_hash, "at": stamp, "prev": prev, "sha": self._sha(prev, cp.seq, cp.head_hash, stamp)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as fh:
            fh.write((json.dumps(row, sort_keys=True) + "\n").encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())


# --- the event file ---------------------------------------------------------------------------------------------

def encode(e: LedgerEvent) -> str:
    c = e.draft.content()
    return canonical({"seq": e.seq, "prev_hash": e.prev_hash, "hash": e.hash, **c})


def decode(line: str) -> LedgerEvent:
    o = json.loads(line)
    draft = EventDraft(o["event_id"], o["epoch_id"], EventKind(o["kind"]), datetime.fromisoformat(o["occurred_at"]), o["payload"])
    return LedgerEvent(int(o["seq"]), o["prev_hash"], o["hash"], draft)


@dataclass(frozen=True)
class LoadReport:
    events: int
    torn_tail_bytes: int = 0
    moved_to: str | None = None


class FileEventStore:
    """``EventStore`` over ``<dir>/ledger.jsonl``. Open with ``writable=True`` only while holding the ``WriterLock``."""

    def __init__(self, path: Path, *, writable: bool = False, checkpoints: CheckpointLog | None = None) -> None:
        self.path = path
        self.writable = writable
        self.checkpoints = checkpoints
        self._events: list[LedgerEvent] = []
        self._ids: set[str] = set()
        self.load_report = self._load()

    def _load(self) -> LoadReport:
        if not self.path.exists():
            if self.writable:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.touch()
            return LoadReport(0)
        data = self.path.read_bytes()
        parts = data.split(b"\n")  # the last part is empty when the file ends with a newline
        pos, torn_at, needs_newline = 0, None, False
        for i, raw in enumerate(parts):
            last = i == len(parts) - 1
            end = pos + len(raw) + (0 if last else 1)
            if raw.strip():
                try:
                    e = decode(raw.decode("utf-8"))
                    if not e.verify():
                        raise ValueError("event hash does not match its content")
                    if e.seq != len(self._events) + 1:
                        raise ValueError(f"expected seq {len(self._events) + 1}, found {e.seq}")
                except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
                    if all(not p.strip() for p in parts[i + 1:]):
                        torn_at = pos  # the final line only: a write that never finished
                        break
                    raise StoreCorrupt(f"{self.path.name}: the line after event {len(self._events)} is unreadable ({exc}); not repaired") from exc
                self._events.append(e)
                self._ids.add(e.draft.event_id)
                needs_newline = last  # a complete, valid event that only lost its newline
            pos = end
        torn_bytes, moved = 0, None
        if self.writable:
            if torn_at is not None:
                torn_bytes = len(data) - torn_at
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                aside = self.path.with_name(f"{self.path.stem}.torn-{stamp}.bin")
                aside.write_bytes(data[torn_at:])
                with self.path.open("r+b") as fh:
                    fh.truncate(torn_at)
                    fh.flush()
                    os.fsync(fh.fileno())
                moved = aside.name
            elif needs_newline:
                with self.path.open("ab") as fh:
                    fh.write(b"\n")
                    fh.flush()
                    os.fsync(fh.fileno())
        elif torn_at is not None:
            torn_bytes = len(data) - torn_at
        return LoadReport(len(self._events), torn_bytes, moved)

    def read_all(self) -> Sequence[LedgerEvent]:
        return tuple(self._events)

    def append(self, event: LedgerEvent) -> None:
        if not self.writable:
            raise LedgerError("store is open read-only")
        if event.seq != len(self._events) + 1:
            raise LedgerError("store sequence mismatch")
        if event.draft.event_id in self._ids:
            raise LedgerError("store already holds this event_id")
        line = (encode(event) + "\n").encode("utf-8")
        with self.path.open("ab") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
        self._events.append(event)
        self._ids.add(event.draft.event_id)
        if self.checkpoints is not None:
            self.checkpoints.record(Checkpoint(event.seq, event.hash))

    def sync_checkpoint(self) -> None:
        """Record the current head (a checkpoint write can lag an append by one step; see the ledger contract)."""
        if self.checkpoints is not None and self._events:
            self.checkpoints.record(Checkpoint(self._events[-1].seq, self._events[-1].hash))


def verify_against(events: Sequence[LedgerEvent], log: CheckpointLog) -> list[str]:
    """Every preserved checkpoint must still be part of the ledger's history."""
    problems = log.verify_self()
    by_seq = {e.seq: e.hash for e in events}
    for ln in log.entries():
        seq = int(ln["seq"])
        if seq > len(events):
            problems.append(f"ledger holds {len(events)} events; a preserved checkpoint says at least {seq} (tail truncated?)")
        elif by_seq.get(seq) != ln["head_hash"]:
            problems.append(f"ledger history at seq {seq} differs from the preserved checkpoint")
    return problems


def preserve_copy(ledger_file: Path, dest_dir: Path, seq: int, head_hash: str) -> Path:
    """A point-in-time copy of the ledger file next to the checkpoints (a different location from the ledger)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"ledger-{seq:06d}-{head_hash[:12]}.jsonl"
    if not dest.exists():
        tmp = dest.with_name(dest.name + ".tmp")
        shutil.copyfile(ledger_file, tmp)
        os.replace(tmp, dest)
    return dest


__all__ = ["CheckpointLog", "FileEventStore", "GENESIS_HASH", "LoadReport", "StoreCorrupt", "TruncationError", "WriterBusy",
           "WriterLock", "atomic_write", "decode", "encode", "preserve_copy", "verify_against"]
