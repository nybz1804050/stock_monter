"""涨跌幅告警：穿越阈值时记录一条，避免同一轮重复刷屏。"""
import os
from collections import deque
from datetime import datetime

from .quotes import Quote


class AlertTracker:
    """维护每只股票的「是否已在阈值之外」状态，只在穿越瞬间产出告警。"""

    def __init__(self, threshold: float = 3.0, log_file: str = None,
                 memory: int = 200):
        self.threshold = threshold
        self.log_file = log_file
        self._state: dict[str, bool] = {}
        self.recent: deque[dict] = deque(maxlen=memory)

    def check(self, quotes: list[Quote], now: datetime = None) -> list[dict]:
        """返回本轮新产生的告警列表，并把它们写入日志与内存队列。"""
        now = now or datetime.now()
        stamp = now.strftime("%Y-%m-%d %H:%M:%S")
        fired: list[dict] = []
        for q in quotes:
            if q.pct is None:
                continue
            crossing = abs(q.pct) >= self.threshold
            if crossing and not self._state.get(q.code, False):
                item = {"time": stamp, "code": q.code, "name": q.name,
                        "pct": q.pct, "price": q.price,
                        "kind": "大涨" if q.pct > 0 else "大跌"}
                fired.append(item)
                self.recent.appendleft(item)
                self._write(item)
            self._state[q.code] = crossing
        return fired

    def _write(self, item: dict) -> None:
        if not self.log_file:
            return
        line = (f"[{item['time']}] {item['name']}({item['code']}) "
                f"{item['kind']} {item['pct']:+.2f}%  现价 {item['price']}")
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.log_file)), exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def as_list(self) -> list[dict]:
        return list(self.recent)

    def clear(self) -> None:
        """清空内存队列；日志文件保留（历史可查）。"""
        self.recent.clear()
        self._state.clear()


def read_history(log_file: str, limit: int = 50) -> list[str]:
    """读取告警日志的最后 limit 行（文件不存在返回空列表）。"""
    if not log_file or not os.path.exists(log_file):
        return []
    try:
        with open(log_file, encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip() for ln in f if ln.strip()]
        return lines[-limit:]
    except OSError:
        return []
