from datetime import date

from tests.live.harness import DAYS, FIRST_INDEX, Live, after_close


def test_activate_and_two_sessions(tmp_path):
    lv = Live.create(tmp_path)
    c = lv.activate()
    assert c["paper_only"] and c["execution_basis"] == "SIMULATED_FROM_DAILY_OHLC"
    r = lv.run(after_close(DAYS[FIRST_INDEX]))
    assert r.status == "ADVANCED", r.reasons
    assert r.processed == [DAYS[FIRST_INDEX].isoformat()]
    r2 = lv.run(after_close(DAYS[FIRST_INDEX]))
    assert r2.status == "UP_TO_DATE" and r2.appended == 0
    print(r.as_dict())
