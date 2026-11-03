"""Durable ledger: atomic appends, torn-write recovery, single writer, independent checkpoints."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from tests.live.harness import DAYS, FIRST_INDEX, after_close
from the_reef.ledger import events as ev
from the_reef.ledger.ledger import AppendResult, Checkpoint, Ledger
from the_reef.ledger.state import LedgerError
from the_reef.live import epoch
from the_reef.live.epoch import LiveError
from the_reef.live.store import CheckpointLog, FileEventStore, StoreCorrupt, WriterBusy, WriterLock

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def new_ledger(tmp_path, *, writable=True):
    cps = CheckpointLog(tmp_path / "cp" / "e.jsonl")
    store = FileEventStore(tmp_path / "e" / "ledger.jsonl", writable=writable, checkpoints=cps)
    return Ledger(store, expected=cps.latest()), store, cps


def fund(led, n=3):
    led.append(ev.epoch_opened("E", T0, Decimal("1000")))
    for i in range(n):
        led.append(ev.sleeve_created("E", T0, f"s{i}"))


def test_restart_reproduces_the_books(tmp_path):
    led, store, cps = new_ledger(tmp_path)
    fund(led)
    digest, head = led.state.digest(), led.state.head_hash
    again, _, _ = new_ledger(tmp_path)
    assert again.state.digest() == digest and again.state.head_hash == head
    assert cps.latest() == Checkpoint(4, head)


def test_duplicate_append_is_a_noop_and_conflict_is_refused(tmp_path):
    led, store, _ = new_ledger(tmp_path)
    fund(led)
    assert led.append(ev.sleeve_created("E", T0, "s0")) is AppendResult.DUPLICATE
    assert len(store.read_all()) == 4
    clash = ev.EventDraft(ev.sleeve_created("E", T0, "s0").event_id, "E", ev.EventKind.SLEEVE_CREATED, T0, {"sleeve_id": "other"})
    with pytest.raises(LedgerError):
        led.append(clash)
    with pytest.raises(LedgerError, match="sequence|event_id"):
        store.append(store.read_all()[0])


def test_torn_last_line_is_set_aside_and_never_read_as_an_event(tmp_path):
    led, store, _ = new_ledger(tmp_path)
    fund(led)
    path = store.path
    good = path.read_bytes()
    path.write_bytes(good + b'{"seq":5,"prev_hash":"abc","hash":"de')  # power cut mid-write
    ro = FileEventStore(path, writable=False)
    assert len(ro.read_all()) == 4 and ro.load_report.torn_tail_bytes > 0
    assert path.read_bytes() != good  # a reader never repairs
    led2, store2, _ = new_ledger(tmp_path)
    assert len(store2.read_all()) == 4
    assert store2.load_report.moved_to and (path.parent / store2.load_report.moved_to).exists()
    assert path.read_bytes() == good
    assert led2.append(ev.sleeve_created("E", T0, "s9")) is AppendResult.APPENDED  # carries on from the last intact event
    assert Ledger(FileEventStore(path)).state.last_seq == 5


def test_a_complete_event_that_only_lost_its_newline_is_kept(tmp_path):
    led, store, _ = new_ledger(tmp_path)
    fund(led)
    store.path.write_bytes(store.path.read_bytes().rstrip(b"\n"))
    _, store2, _ = new_ledger(tmp_path)
    assert len(store2.read_all()) == 4 and store2.path.read_bytes().endswith(b"\n")


def test_corruption_in_the_middle_is_not_repaired(tmp_path):
    led, store, _ = new_ledger(tmp_path)
    fund(led)
    lines = store.path.read_bytes().split(b"\n")
    lines[1] = lines[1][:20] + b"#" + lines[1][21:]
    store.path.write_bytes(b"\n".join(lines))
    with pytest.raises(StoreCorrupt):
        FileEventStore(store.path)


def test_an_edited_event_is_refused(tmp_path):
    led, store, _ = new_ledger(tmp_path)
    fund(led)
    rows = [json.loads(x) for x in store.path.read_text().splitlines()]
    rows[0]["payload"]["initial_cash"] = "999999"
    store.path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    with pytest.raises(StoreCorrupt):  # the event no longer hashes to its recorded hash
        FileEventStore(store.path)


def test_only_one_writer_at_a_time_and_the_lock_is_released(tmp_path):
    lock = tmp_path / "e" / "ledger.lock"
    with WriterLock(lock):
        with pytest.raises(WriterBusy):
            with WriterLock(lock):
                pass
    with WriterLock(lock):  # released on exit
        pass


def test_a_read_only_store_cannot_append(tmp_path):
    led, store, _ = new_ledger(tmp_path)
    fund(led)
    ro = FileEventStore(store.path, writable=False)
    with pytest.raises(LedgerError, match="read-only"):
        ro.append(store.read_all()[0])


def test_tail_truncation_is_caught_by_the_independent_checkpoint(live):
    live.run(after_close(DAYS[FIRST_INDEX]))
    path = live.paths.ledger_file(live.spec.epoch_id)
    lines = path.read_bytes().split(b"\n")
    path.write_bytes(b"\n".join(lines[:-6]) + b"\n")  # drop the last events: still a valid, shorter chain
    assert Ledger(FileEventStore(path)).state.last_seq > 0  # the chain alone cannot tell
    with pytest.raises(LiveError, match="checkpoint"):
        epoch.open_ledger(live.paths, live.spec.epoch_id, writable=False)
    rep = live.run(after_close(DAYS[FIRST_INDEX]))
    assert rep.status == "SAFE_HOLD" and "checkpoint" in " ".join(rep.reasons)


def test_a_history_rewritten_and_rechained_from_the_start_is_caught(live):
    live.run(after_close(DAYS[FIRST_INDEX]))
    path = live.paths.ledger_file(live.spec.epoch_id)
    events = list(FileEventStore(path).read_all())
    forged = Ledger()
    for e in events:
        d = e.draft
        if d.kind is ev.EventKind.ATTESTATION and d.payload.get("subtype") == "CHARTER":  # an edit the books cannot object to
            d = ev.EventDraft(d.event_id, d.epoch_id, d.kind, d.occurred_at, {**ev.thaw(d.payload), "activated_at": "2020-01-01T00:00:00+00:00"})
        forged.append(d)
    path.unlink()
    store = FileEventStore(path, writable=True)
    for e in forged.store.read_all():
        store.append(e)
    with pytest.raises(LiveError):  # a perfectly valid chain, but not the one that was preserved
        epoch.open_ledger(live.paths, live.spec.epoch_id, writable=False)


def test_tampering_with_the_checkpoint_log_is_detected(live):
    live.run(after_close(DAYS[FIRST_INDEX]))
    cp = live.paths.checkpoint_file(live.spec.epoch_id)
    lines = cp.read_text().splitlines()
    row = json.loads(lines[2])
    row["head_hash"] = "0" * 64
    lines[2] = json.dumps(row, sort_keys=True)
    cp.write_text("\n".join(lines) + "\n")
    assert CheckpointLog(cp).verify_self()
    with pytest.raises(LiveError):
        epoch.open_ledger(live.paths, live.spec.epoch_id, writable=False)


def test_a_crash_between_the_event_and_its_checkpoint_is_recovered(live):
    live.run(after_close(DAYS[FIRST_INDEX]))
    cp = live.paths.checkpoint_file(live.spec.epoch_id)
    lines = cp.read_text().splitlines()
    cp.write_text("\n".join(lines[:-1]) + "\n")  # the last checkpoint write never happened
    led = epoch.open_ledger(live.paths, live.spec.epoch_id, writable=True)  # the store is longer than the checkpoint: accepted
    assert CheckpointLog(cp).latest().seq == led.state.last_seq  # and the missing checkpoint is recorded on load
    assert not CheckpointLog(cp).verify_self()
