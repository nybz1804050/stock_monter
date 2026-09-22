"""浏览器页面：Flask 应用与 JSON 接口。

后台按固定间隔拉一次行情并缓存，页面只读缓存，避免每个浏览器标签都去打行情接口。
"""
import json
import logging
import os
import queue
import threading
from datetime import datetime
from typing import Optional

from flask import Flask, Response, jsonify, render_template, request

from . import alerts, indicators, watchlist
from . import config as config_mod
from .alerts import AlertTracker
from .datasource import SourceManager
from .quotes import Quote
from .storage import open_store

log = logging.getLogger(__name__)

# 单次历史查询的返回条数上限：防止 limit 传入超大值把整张表拉进内存。
HISTORY_LIMIT_MAX = 2000

# 指标参数的取值范围：下限 1，上限防止窗口开得过大导致一次请求算太久。
INDICATOR_PARAM_MAX = 500
INDICATOR_PARAMS = ("window", "period", "fast", "slow", "signal", "num_std")


def _parse_limit(raw, default: int = 120) -> int:
    """把 querystring 的 limit 转成合法条数；非法时抛 ValueError（调用方转 400）。"""
    try:
        value = int(raw if raw not in (None, "") else default)
    except (TypeError, ValueError):
        raise ValueError("limit 必须是整数") from None
    if value < 1:
        raise ValueError("limit 必须大于 0")
    return min(value, HISTORY_LIMIT_MAX)


class QuoteService:
    """后台轮询行情并缓存结果；线程安全（只用一个锁保护快照）。"""

    def __init__(self, base_dir: str = None, interval: float = 5.0,
                 threshold: float = 3.0, manager: SourceManager = None,
                 store=None, history_limit: int = 500):
        self.base_dir = base_dir
        self.interval = interval
        self.manager = manager or SourceManager()
        self.tracker = AlertTracker(threshold=threshold, log_file=self._log_path())
        self.store = store
        self.history_limit = history_limit
        self._lock = threading.Lock()
        self._quotes: list[Quote] = []
        self._updated_at: Optional[str] = None
        self._error: Optional[str] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._subscribers: list[queue.Queue] = []      # SSE 订阅者，每个连接一个队列

    def _log_path(self) -> str:
        import os

        from .watchlist import _base_dir
        return os.path.join(_base_dir(self.base_dir), "alerts.log")

    # ---------- 轮询 ----------
    def refresh_once(self) -> None:
        codes = watchlist.load(self.base_dir)
        if not codes:
            with self._lock:
                self._quotes, self._error = [], "自选股列表为空"
            return
        try:
            quotes = self.manager.fetch(codes)
            self.tracker.check(quotes)
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if self.store is not None:            # 历史落盘失败不影响行情
                try:
                    self.store.record(quotes, stamp)
                except Exception:                 # noqa: BLE001
                    log.warning("写入行情历史失败", exc_info=True)
            with self._lock:
                self._quotes = quotes
                self._updated_at = stamp
                self._error = None
            self._broadcast()
        except Exception as exc:      # noqa: BLE001
            with self._lock:
                self._error = str(exc)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        def loop():
            while not self._stop.is_set():
                self.refresh_once()
                self._stop.wait(self.interval)

        self._thread = threading.Thread(target=loop, name="quote-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # ---------- SSE 订阅 ----------
    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=8)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def _broadcast(self) -> None:
        """把最新快照推给所有订阅者；队列满说明该连接太慢，丢弃这一帧即可。"""
        payload = self.snapshot()
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(payload)
            except queue.Full:
                pass

    # ---------- 快照 ----------
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "time": self._updated_at,
                "source": self.manager.name,
                "interval": self.interval,
                "threshold": self.tracker.threshold,   # 前端星标用它，避免再写死一个 3
                "error": self._error,
                "quotes": [q.to_dict() for q in self._quotes],
                "alerts": self.tracker.as_list()[:50],
            }


def create_app(base_dir: str = None, interval: float = None,
               threshold: float = None, autostart: bool = True,
               config: dict = None) -> Flask:
    cfg = config or config_mod.load(base_dir, {"interval": interval, "threshold": threshold})
    interval = cfg["interval"]
    threshold = cfg["threshold"]
    db_path = cfg.get("db_path")
    if db_path and base_dir and not os.path.isabs(db_path):
        db_path = os.path.join(base_dir, db_path)
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    service = QuoteService(base_dir=base_dir, interval=interval, threshold=threshold,
                           store=open_store(db_path), history_limit=cfg.get("history_limit", 500))
    app.config["SERVICE"] = service
    if autostart:
        service.start()

    @app.get("/")
    def index():
        return render_template("index.html",
                               interval=interval, threshold=threshold)

    @app.get("/api/quotes")
    def api_quotes():
        return jsonify(service.snapshot())

    @app.get("/api/watchlist")
    def api_watchlist():
        return jsonify({"codes": watchlist.load(base_dir)})

    @app.post("/api/watchlist")
    def api_watchlist_add():
        payload = request.get_json(silent=True) or {}
        code = str(payload.get("code", "")).strip()
        try:
            codes = watchlist.add(code, base_dir)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        service.refresh_once()          # 新增后立刻拉一次，页面无需等下个周期
        return jsonify({"ok": True, "codes": codes})

    @app.delete("/api/watchlist/<code>")
    def api_watchlist_remove(code):
        codes = watchlist.remove(code, base_dir)
        service.refresh_once()
        return jsonify({"ok": True, "codes": codes})

    @app.get("/api/alerts")
    def api_alerts():
        """会话内告警 + 日志历史（history=1 时带出最近 50 条落盘记录）。"""
        snap = service.snapshot()
        payload = {"alerts": snap["alerts"], "threshold": threshold}
        if request.args.get("history"):
            payload["history"] = alerts.read_history(service.tracker.log_file, limit=50)
        return jsonify(payload)

    @app.delete("/api/alerts")
    def api_alerts_clear():
        service.tracker.clear()
        return jsonify({"ok": True})

    @app.get("/api/stream")
    def api_stream():
        """SSE 实时推送：每轮刷新推一帧快照，15 秒无数据发一次心跳。"""
        def gen():
            q = service.subscribe()
            try:
                yield "retry: 3000\n\n"
                while True:
                    try:
                        payload = q.get(timeout=15)
                    except queue.Empty:
                        yield ": keep-alive\n\n"
                        continue
                    yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
            finally:
                service.unsubscribe(q)

        return Response(gen(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/history")
    def api_history():
        """某只股票最近的价格序列（默认 120 条），用于前端走势图。"""
        code = (request.args.get("code") or "").strip()
        if not watchlist.is_valid_code(code):
            return jsonify({"ok": False, "error": "code 必须是 6 位数字"}), 400
        # limit 以前直接 int() 转换：非数字会抛 ValueError（500），超大值会一次拉爆内存。
        try:
            limit = _parse_limit(request.args.get("limit"))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        store = service.store
        if store is None:
            return jsonify({"ok": False, "error": "历史存储未启用"}), 503
        return jsonify({"ok": True, "code": code, "points": store.history(code, limit)})

    @app.get("/api/indicators")
    def api_indicators():
        """按需计算某只股票的技术指标，数据取自本地历史库。

        参数：code 必填；name 见 indicators.SUPPORTED；window/period/... 按指标取值；
        limit 控制参与计算的最近样本数（与 /api/history 同口径）。
        """
        code = (request.args.get("code") or "").strip()
        if not watchlist.is_valid_code(code):
            return jsonify({"ok": False, "error": "code 必须是 6 位数字"}), 400
        name = (request.args.get("name") or "").strip().lower()
        store = service.store
        if store is None:
            return jsonify({"ok": False, "error": "历史存储未启用"}), 503
        try:
            limit = _parse_limit(request.args.get("limit"), default=120)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        # 只认白名单里的参数名，避免任意 querystring 被透传进计算函数
        params = {}
        for key in INDICATOR_PARAMS:
            raw = request.args.get(key)
            if raw in (None, ""):
                continue
            try:
                params[key] = int(raw)
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": f"{key} 必须是整数"}), 400
            if not 1 <= params[key] <= INDICATOR_PARAM_MAX:
                return jsonify({"ok": False,
                                "error": f"{key} 必须在 1~{INDICATOR_PARAM_MAX} 之间"}), 400
        points = store.history(code, limit)
        try:
            series = indicators.compute(name, [p["price"] for p in points], **params)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "code": code, "name": name,
                        "params": params, "count": len(points),
                        "ts": [p["ts"] for p in points], "series": series})

    @app.get("/api/health")
    def api_health():
        snap = service.snapshot()
        return jsonify({"ok": snap["error"] is None, "time": snap["time"],
                        "source": snap["source"]})

    return app
