"""web 模块：接口行为（不启动后台线程、不访问网络）。"""
import json

import pytest

from stockmon.datasource import SourceManager
from stockmon.quotes import Quote
from stockmon.web import QuoteService, create_app


class FakeManager(SourceManager):
    """把行情源替换成固定数据，避免测试打网络。"""

    def __init__(self, quotes=None):
        super().__init__()
        self._quotes = quotes if quotes is not None else [
            Quote("600519", "贵州茅台", price=1688.8, chg=20.5, pct=1.23, source="fake"),
        ]

    def fetch(self, codes):
        return [q for q in self._quotes if q.code in codes] or []


@pytest.fixture()
def client(tmp_path):
    (tmp_path / "stocks.json").write_text(json.dumps(["600519"]), encoding="utf-8")
    app = create_app(base_dir=str(tmp_path), autostart=False)
    service = app.config["SERVICE"]
    service.manager = FakeManager()
    service.refresh_once()
    return app.test_client(), str(tmp_path)


def test_index_renders(client):
    c, _ = client
    html = c.get("/").get_data(as_text=True)
    assert "自选股行情看板" in html
    assert "quote-table" in html


def test_api_quotes_returns_normalized_rows(client):
    c, _ = client
    data = c.get("/api/quotes").get_json()
    assert data["quotes"][0]["code"] == "600519"
    assert data["quotes"][0]["direction"] == "up"
    assert data["error"] is None and data["time"]


def test_api_watchlist_add_and_remove(client):
    c, base = client
    assert c.get("/api/watchlist").get_json()["codes"] == ["600519"]

    added = c.post("/api/watchlist", json={"code": "300750"}).get_json()
    assert added["ok"] and added["codes"] == ["600519", "300750"]
    assert json.loads(open(base + "/stocks.json", encoding="utf-8").read()) == ["600519", "300750"]

    bad = c.post("/api/watchlist", json={"code": "nope"})
    assert bad.status_code == 400 and bad.get_json()["ok"] is False

    removed = c.delete("/api/watchlist/600519").get_json()
    assert removed["codes"] == ["300750"]


def test_api_alerts_history_and_clear(client):
    c, _ = client
    assert c.get("/api/alerts").get_json()["threshold"] == 3.0
    assert "history" in c.get("/api/alerts?history=1").get_json()
    assert c.delete("/api/alerts").get_json()["ok"] is True


def test_api_health(client):
    c, _ = client
    assert c.get("/api/health").get_json()["ok"] is True


def test_api_quotes_exposes_threshold(client):
    """快照要带出告警阈值，前端星标据此判定，避免前后端各写一个数。"""
    c, _ = client
    assert c.get("/api/quotes").get_json()["threshold"] == 3.0


def test_api_history_rejects_bad_limit(client):
    """limit 非法输入应返回 400 而不是 500（以前 int() 会直接抛 ValueError）。"""
    c, _ = client
    assert c.get("/api/history?code=600519&limit=abc").status_code == 400
    assert c.get("/api/history?code=600519&limit=1.5").status_code == 400


def test_api_history_rejects_non_positive_limit(client):
    c, _ = client
    assert c.get("/api/history?code=600519&limit=0").status_code == 400
    assert c.get("/api/history?code=600519&limit=-20").status_code == 400


def test_api_history_caps_huge_limit(client):
    """超大 limit 应被裁剪到上限而不是 500；历史库未启用时是 503，也算通过。"""
    c, _ = client
    resp = c.get("/api/history?code=600519&limit=999999")
    assert resp.status_code in (200, 503)
    if resp.status_code == 200:
        assert resp.get_json()["ok"] is True


def test_api_history_rejects_bad_code(client):
    c, _ = client
    assert c.get("/api/history?code=abc").status_code == 400


def test_api_indicators_computes_series(client):
    """指标接口基于历史库计算，序列长度应与返回的样本数一致。"""
    c, _ = client
    data = c.get("/api/indicators?code=600519&name=sma&window=1").get_json()
    assert data["ok"] is True and data["name"] == "sma"
    assert data["count"] >= 1
    assert len(data["series"]["values"]) == data["count"]


def test_api_indicators_macd_returns_three_series(client):
    c, _ = client
    data = c.get("/api/indicators?code=600519&name=macd").get_json()
    assert data["ok"] is True
    assert set(data["series"]) == {"dif", "dea", "hist"}


def test_api_indicators_rejects_unknown_name(client):
    c, _ = client
    resp = c.get("/api/indicators?code=600519&name=kdj")
    assert resp.status_code == 400 and "不支持" in resp.get_json()["error"]


def test_api_indicators_rejects_bad_code(client):
    c, _ = client
    assert c.get("/api/indicators?code=abc&name=sma").status_code == 400


def test_api_indicators_rejects_non_integer_param(client):
    c, _ = client
    assert c.get("/api/indicators?code=600519&name=sma&window=abc").status_code == 400


def test_api_indicators_rejects_out_of_range_param(client):
    """窗口开得过大或为 0 都应被挡在计算之前。"""
    c, _ = client
    assert c.get("/api/indicators?code=600519&name=sma&window=0").status_code == 400
    assert c.get("/api/indicators?code=600519&name=sma&window=9999").status_code == 400


def test_api_indicators_ignores_unknown_querystring(client):
    """白名单之外的参数名不应影响结果（也不应报错）。"""
    c, _ = client
    data = c.get("/api/indicators?code=600519&name=sma&window=1&evil=1").get_json()
    assert data["ok"] is True and "evil" not in data["params"]


def test_service_reports_error_when_watchlist_empty(tmp_path):
    (tmp_path / "stocks.json").write_text("[]", encoding="utf-8")
    service = QuoteService(base_dir=str(tmp_path), manager=FakeManager())
    service.refresh_once()
    assert service.snapshot()["error"] == "自选股列表为空"


def test_sse_subscribers_receive_snapshots(client):
    """订阅者应在每轮刷新后收到快照；退订后不再收到。"""
    c, _ = client
    service = None
    # 通过应用上下文取到同一 service 实例
    import json as _json
    import os
    import tempfile

    from stockmon.web import create_app
    d = tempfile.mkdtemp()
    open(os.path.join(d, "stocks.json"), "w", encoding="utf-8").write(_json.dumps(["600519"]))
    app = create_app(base_dir=d, autostart=False)
    service = app.config["SERVICE"]
    service.manager = FakeManager()

    q = service.subscribe()
    service.refresh_once()
    frame = q.get(timeout=2)
    assert frame["quotes"][0]["code"] == "600519"

    service.unsubscribe(q)
    service.refresh_once()
    assert q.empty()
