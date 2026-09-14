# -*- coding: utf-8 -*-
"""行情历史存储：把每次快照落到 SQLite，供走势图与接口查询。

只依赖标准库 sqlite3；写入失败不影响行情主流程（调用方自行忽略异常）。
"""
import os
import sqlite3
import threading
from typing import Dict, List, Optional

from .quotes import Quote

SCHEMA = """
CREATE TABLE IF NOT EXISTS quotes (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT    NOT NULL,
    code    TEXT    NOT NULL,
    name    TEXT    NOT NULL,
    price   REAL,
    pct     REAL,
    chg     REAL,
    source  TEXT
);
CREATE INDEX IF NOT EXISTS idx_quotes_code_ts ON quotes (code, ts);
"""


class HistoryStore:
    """SQLite 行情历史；同一个连接在多线程下用锁串行化。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        if db_path != ":memory:":
            parent = os.path.dirname(os.path.abspath(db_path))
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def record(self, quotes: List[Quote], ts: str) -> int:
        """批量写入一轮快照，返回写入条数。"""
        rows = [(ts, q.code, q.name, q.price, q.pct, q.chg, q.source) for q in quotes]
        if not rows:
            return 0
        with self._lock:
            self._conn.executemany(
                "INSERT INTO quotes (ts, code, name, price, pct, chg, source)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
            self._conn.commit()
        return len(rows)

    def history(self, code: str, limit: int = 120) -> List[Dict]:
        """按时间倒序取某只股票最近 limit 条记录（返回时正序，便于画图）。"""
        with self._lock:
            cur = self._conn.execute(
                "SELECT ts, price, pct FROM quotes WHERE code = ? ORDER BY id DESC LIMIT ?",
                (code, int(limit)))
            rows = cur.fetchall()
        return [{"ts": ts, "price": price, "pct": pct} for ts, price, pct in reversed(rows)]

    def codes(self) -> List[str]:
        with self._lock:
            cur = self._conn.execute("SELECT DISTINCT code FROM quotes ORDER BY code")
            return [r[0] for r in cur.fetchall()]

    def count(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0])

    def prune(self, keep_per_code: int = 500) -> int:
        """每只股票只保留最近 keep_per_code 条，返回删除行数。"""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM quotes WHERE id NOT IN ("
                "  SELECT id FROM ("
                "    SELECT id, ROW_NUMBER() OVER (PARTITION BY code ORDER BY id DESC) AS rn"
                "    FROM quotes) WHERE rn <= ?)", (int(keep_per_code),))
            self._conn.commit()
            return cur.rowcount or 0

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def open_store(db_path: Optional[str] = None) -> Optional[HistoryStore]:
    """容错打开：路径为空返回 None，打开失败也不抛出（历史只是增强功能）。"""
    if not db_path:
        return None
    try:
        return HistoryStore(db_path)
    except sqlite3.Error:
        return None
