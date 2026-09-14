# -*- coding: utf-8 -*-
"""浏览器页面：Flask 应用与 JSON 接口。

后台按固定间隔拉一次行情并缓存，页面只读缓存，避免每个浏览器标签都去打行情接口。
"""
import logging
import threading
import time
from datetime import datetime
from typing import List, Optional

from flask import Flask, jsonify, render_template, request

from . import alerts
from . import config as config_mod
from . import watchlist
from .alerts import AlertTracker
from .datasource import SourceManager
from .quotes import Quote

log = logging.getLogger(__name__)


class QuoteService:
    """后台轮询行情并缓存结果；线程安全（只用一个锁保护快照）。"""

    def __init__(self, base_dir: str = None, interval: float = 5.0,
                 threshold: float = 3.0, manager: SourceManager = None):
        self.base_dir = base_dir
        self.interval = interval
        self.manager = manager or SourceManager()
        self.tracker = AlertTracker(threshold=threshold, log_file=self._log_path())
        self._lock = threading.Lock()
        self._quotes: List[Quote] = []
        self._updated_at: Optional[str] = None
        self._error: Optional[str] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _log_path(self) -> str:
        from .watchlist import _base_dir
        import os
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
            with self._lock:
                self._quotes = quotes
                self._updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._error = None
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

    # ---------- 快照 ----------
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "time": self._updated_at,
                "source": self.manager.name,
                "interval": self.interval,
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
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    service = QuoteService(base_dir=base_dir, interval=interval, threshold=threshold)
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

    @app.get("/api/health")
    def api_health():
        snap = service.snapshot()
        return jsonify({"ok": snap["error"] is None, "time": snap["time"],
                        "source": snap["source"]})

    return app
