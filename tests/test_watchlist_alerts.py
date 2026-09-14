"""watchlist 与 alerts 模块（离线，使用临时目录）。"""
import datetime
import json
import os

import pytest

from stockmon import alerts, watchlist
from stockmon.quotes import Quote


# ---------------- watchlist ----------------
def test_load_prefers_json(tmp_path):
    (tmp_path / "stocks.json").write_text(json.dumps(["600519", "300750"]), encoding="utf-8")
    (tmp_path / "stocks.txt").write_text("000001\n", encoding="utf-8")
    assert watchlist.load(str(tmp_path)) == ["600519", "300750"]


def test_load_falls_back_to_txt_and_ignores_comments(tmp_path):
    (tmp_path / "stocks.txt").write_text("# 注释\n600519\n\n300750\n", encoding="utf-8")
    assert watchlist.load(str(tmp_path)) == ["600519", "300750"]


def test_load_returns_defaults_when_nothing_exists(tmp_path):
    assert watchlist.load(str(tmp_path)) == watchlist.DEFAULT_CODES


def test_add_dedupes_and_persists(tmp_path):
    watchlist.save(["600519"], str(tmp_path))
    codes = watchlist.add("600519", str(tmp_path))       # 重复添加不应产生第二份
    assert codes == ["600519"]
    codes = watchlist.add("300750", str(tmp_path))
    assert codes == ["600519", "300750"]
    assert json.loads((tmp_path / "stocks.json").read_text(encoding="utf-8")) == codes


@pytest.mark.parametrize("bad", ["abc", "60051", "6005199", "", "60-519"])
def test_add_rejects_invalid_codes(tmp_path, bad):
    with pytest.raises(ValueError):
        watchlist.add(bad, str(tmp_path))


def test_remove(tmp_path):
    watchlist.save(["600519", "300750"], str(tmp_path))
    assert watchlist.remove("600519", str(tmp_path)) == ["300750"]
    assert watchlist.remove("000000", str(tmp_path)) == ["300750"]   # 不存在也不报错


def test_save_cleans_and_orders(tmp_path):
    assert watchlist.save(["300750", "bad", "300750", "600519"], str(tmp_path)) == ["300750", "600519"]


# ---------------- alerts ----------------
def test_alert_fires_once_per_crossing(tmp_path):
    log_file = os.path.join(str(tmp_path), "alerts.log")
    tracker = alerts.AlertTracker(threshold=3.0, log_file=log_file)
    now = datetime.datetime(2026, 9, 14, 10, 0, 0)
    rising = Quote("600519", "贵州茅台", price=1688.8, pct=3.5)

    fired = tracker.check([rising], now)
    assert len(fired) == 1 and fired[0]["kind"] == "大涨"
    assert tracker.check([rising], now) == []            # 仍在阈值外 → 不重复告警

    # 回落到阈值内，再冲上去应再次告警
    tracker.check([Quote("600519", "贵州茅台", price=1600.0, pct=0.4)], now)
    assert len(tracker.check([rising], now)) == 1
    assert os.path.exists(log_file)
    assert len(alerts.read_history(log_file)) == 2


def test_alert_ignores_missing_pct(tmp_path):
    tracker = alerts.AlertTracker(threshold=3.0, log_file=None)
    assert tracker.check([Quote("600519", "贵州茅台", price=None, pct=None)]) == []


def test_clear_resets_state(tmp_path):
    tracker = alerts.AlertTracker(threshold=3.0, log_file=None)
    q = Quote("600519", "贵州茅台", price=1.0, pct=5.0)
    tracker.check([q])
    tracker.clear()
    assert tracker.as_list() == []
    assert len(tracker.check([q])) == 1                  # 清空后可再次告警


def test_read_history_missing_file_is_empty(tmp_path):
    assert alerts.read_history(os.path.join(str(tmp_path), "nope.log")) == []
