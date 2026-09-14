"""storage 模块：SQLite 历史读写与裁剪。"""
from stockmon.quotes import Quote
from stockmon.storage import HistoryStore, open_store


def make_store(tmp_path):
    return HistoryStore(str(tmp_path / "q.db"))


def test_record_and_history_roundtrip(tmp_path):
    store = make_store(tmp_path)
    quotes = [Quote("600519", "贵州茅台", price=1688.8, pct=1.2),
              Quote("300750", "宁德时代", price=210.5, pct=-0.8)]
    assert store.record(quotes, "2026-09-14 13:00:00") == 2
    assert store.record(quotes, "2026-09-14 13:00:05") == 2

    points = store.history("600519", limit=10)
    assert [p["ts"] for p in points] == ["2026-09-14 13:00:00", "2026-09-14 13:00:05"]
    assert points[0]["price"] == 1688.8
    assert store.codes() == ["300750", "600519"] or store.codes() == ["300750", "600519"][::-1]
    assert store.count() == 4


def test_history_unknown_code_is_empty(tmp_path):
    assert make_store(tmp_path).history("000000") == []


def test_record_empty_list_is_noop(tmp_path):
    store = make_store(tmp_path)
    assert store.record([], "2026-09-14 13:00:00") == 0
    assert store.count() == 0


def test_prune_keeps_latest_per_code(tmp_path):
    store = make_store(tmp_path)
    for i in range(6):
        store.record([Quote("600519", "贵州茅台", price=100 + i)], f"2026-09-14 13:00:0{i}")
    store.prune(keep_per_code=2)
    points = store.history("600519", limit=10)
    assert len(points) == 2
    assert points[-1]["price"] == 105


def test_open_store_tolerates_bad_path():
    assert open_store(None) is None
    assert open_store("") is None
