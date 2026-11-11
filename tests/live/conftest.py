from __future__ import annotations

from datetime import date

import pytest

from tests.live.harness import Live

END = date(2026, 11, 30)  # past Thanksgiving (2026-11-26, closed) and the early close of 2026-11-27


@pytest.fixture(scope="session")
def reference(tmp_path_factory):
    """One uninterrupted day-by-day run through END, shared by tests that compare other runs against it."""
    lv = Live.create(tmp_path_factory.mktemp("reference"))
    lv.activate()
    reports = lv.run_through(END)
    events = list(lv.ledger().store.read_all())
    buys = [e for e in events if e.draft.kind.value == "FILL" and e.draft.payload["side"] == "BUY"]
    assert buys, "the reference scenario must trade"
    return {"live": lv, "events": events, "reports": reports, "first_buy": buys[0],
            "digest": lv.ledger().state.digest(), "head": lv.ledger().state.head_hash}


@pytest.fixture()
def live(tmp_path):
    lv = Live.create(tmp_path)
    lv.activate()
    return lv
