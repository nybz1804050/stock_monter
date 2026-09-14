# -*- coding: utf-8 -*-
"""quotes 模块：字段归一化与涨跌方向。"""
from stockmon.quotes import Quote, normalize, normalize_all, quote_map


def test_normalize_full_fields():
    q = normalize({"code": "600519", "name": "贵州茅台", "price": "1688.80",
                   "pct": "1.23", "chg": "20.50"}, source="eastmoney")
    assert q.code == "600519"
    assert q.price == 1688.80
    assert q.pct == 1.23
    assert q.chg == 20.50
    assert q.source == "eastmoney"
    assert q.direction == "up"


def test_normalize_handles_placeholder_values():
    q = normalize({"code": "000001", "name": "平安银行", "price": "-", "pct": None, "chg": ""})
    assert q.price is None and q.pct is None and q.chg is None
    assert q.direction == "flat"


def test_normalize_requires_code_and_name():
    assert normalize({"code": "", "name": "空代码"}) is None
    assert normalize({"code": "600000"}) is None


def test_normalize_all_filters_invalid_rows():
    rows = [{"code": "600000", "name": "浦发银行", "price": "10.1"},
            {"code": "", "name": "坏数据"},
            {"code": "000002", "name": "万科A", "price": "8.8"}]
    assert [q.code for q in normalize_all(rows)] == ["600000", "000002"]


def test_direction_down_and_flat():
    assert Quote("1", "跌", pct=-0.5).direction == "down"
    assert Quote("1", "平", pct=0).direction == "flat"


def test_quote_map_keys_by_code():
    quotes = [Quote("600000", "浦发银行"), Quote("000002", "万科A")]
    assert set(quote_map(quotes)) == {"600000", "000002"}
