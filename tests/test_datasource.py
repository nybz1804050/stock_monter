# -*- coding: utf-8 -*-
"""datasource 模块：代码映射、报文解析与数据源自动切换（全部离线）。"""
import pytest

from stockmon import datasource
from stockmon.datasource import (SourceManager, eastmoney_secid, parse_eastmoney,
                                 parse_tencent, tencent_code)
from stockmon.quotes import normalize_all

EASTMONEY_PAYLOAD = {"data": {"diff": [
    {"f12": "600519", "f14": "贵州茅台", "f2": 1688.8, "f3": 1.23, "f4": 20.5},
    {"f12": "300750", "f14": "宁德时代", "f2": 210.5, "f3": -2.10, "f4": -4.5},
]}}

def _tencent_line(prefixed: str, name: str, price: str, chg: str, pct: str) -> str:
    """按腾讯行情的真实字段位置拼一条报文：key 带市场前缀，字段 2 是 6 位代码，31=涨跌额、32=涨跌幅。"""
    bare = prefixed[2:]
    fields = ["1", name, bare, price, "0", "0"] + ["0"] * 25
    fields += [chg, pct]
    return f'v_{prefixed}="' + "~".join(fields) + '";'


TENCENT_TEXT = (_tencent_line("sh600519", "贵州茅台", "1688.80", "20.50", "1.23") + "\n"
                'v_pv_none_match="1";\n')


def test_code_mapping():
    assert eastmoney_secid("600519") == "1.600519"
    assert eastmoney_secid("300750") == "0.300750"
    assert tencent_code("600519") == "sh600519"
    assert tencent_code("300750") == "sz300750"
    assert tencent_code("830799") == "bj830799"


def test_parse_eastmoney_flat_and_object_diff():
    rows = parse_eastmoney(EASTMONEY_PAYLOAD)
    assert [r["code"] for r in rows] == ["600519", "300750"]
    assert rows[1]["pct"] == -2.10
    single = parse_eastmoney({"data": {"diff": {"0": {"f12": "600000", "f14": "浦发银行",
                                                     "f2": 10.1, "f3": 0.5, "f4": 0.05}}}})
    assert single[0]["code"] == "600000"


def test_parse_tencent_skips_unmatched_lines():
    rows = parse_tencent(TENCENT_TEXT)
    assert len(rows) == 1                      # v_pv_none_match 这类行被跳过
    assert rows[0]["code"] == "600519"
    assert rows[0]["name"] == "贵州茅台"
    assert rows[0]["price"] == "1688.80"       # 纯解析层保留原始字符串

    # 归一化层负责把字符串转成数值
    quotes = normalize_all(rows, source="tencent")
    assert quotes[0].price == 1688.80
    assert quotes[0].pct == 1.23
    assert quotes[0].chg == 20.50
    assert quotes[0].direction == "up"


def test_source_manager_switches_after_two_failures(monkeypatch):
    calls = {"eastmoney": 0, "tencent": 0}

    def flaky(codes):
        calls["eastmoney"] += 1
        raise RuntimeError("boom")

    def ok(codes):
        calls["tencent"] += 1
        return ["ok"]

    monkeypatch.setitem(datasource.FETCHERS, "eastmoney", flaky)
    monkeypatch.setitem(datasource.FETCHERS, "tencent", ok)

    mgr = SourceManager()
    with pytest.raises(RuntimeError):
        mgr.fetch(["600519"])          # 第 1 次失败：仍留在原源
    assert mgr.name == "eastmoney"
    with pytest.raises(RuntimeError):
        mgr.fetch(["600519"])          # 第 2 次失败：切换
    assert mgr.name == "tencent"
    assert mgr.fetch(["600519"]) == ["ok"]
    assert calls["eastmoney"] == 2 and calls["tencent"] == 1


def test_source_manager_resets_failure_counter_on_success(monkeypatch):
    state = {"fail": True}

    def maybe(codes):
        if state["fail"]:
            raise RuntimeError("down")
        return ["ok"]

    monkeypatch.setitem(datasource.FETCHERS, "eastmoney", maybe)
    mgr = SourceManager()
    with pytest.raises(RuntimeError):
        mgr.fetch(["600519"])
    state["fail"] = False
    assert mgr.fetch(["600519"]) == ["ok"]
    assert mgr.fails == 0


def test_request_retries_then_succeeds(monkeypatch):
    """瞬时网络错误应重试；成功即返回，不再多余请求。"""
    import requests as _rq
    calls = {"n": 0}

    class FakeResp:
        status_code = 200

    def fake_get(url, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _rq.ConnectionError("temporary")
        return FakeResp()

    monkeypatch.setattr(datasource.requests, "get", fake_get)
    monkeypatch.setattr(datasource.time, "sleep", lambda *_: None)
    resp = datasource._request("http://example.invalid", {}, retries=1)
    assert resp.status_code == 200 and calls["n"] == 2


def test_request_raises_after_retries_exhausted(monkeypatch):
    import pytest as _pytest
    import requests as _rq

    def always_fail(url, headers=None, timeout=None):
        raise _rq.Timeout("down")

    monkeypatch.setattr(datasource.requests, "get", always_fail)
    monkeypatch.setattr(datasource.time, "sleep", lambda *_: None)
    with _pytest.raises(_rq.Timeout):
        datasource._request("http://example.invalid", {}, retries=2)
