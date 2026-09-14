# -*- coding: utf-8 -*-
"""配置层：默认值 < config.json < 环境变量，便于在不同环境调整行为。"""
import json
import os
from typing import Any, Dict

DEFAULTS: Dict[str, Any] = {
    "interval": 5.0,          # 行情刷新间隔（秒）
    "threshold": 3.0,         # 涨跌幅告警阈值（%）
    "host": "127.0.0.1",
    "port": 8000,
    "timeout": 6,             # 单次行情请求超时（秒）
    "retries": 1,             # 请求失败重试次数
    "history_limit": 500,     # 内存中保留的历史快照条数
    "db_path": "quotes.db",   # SQLite 行情库（相对项目根目录）
}

ENV_PREFIX = "STOCKMON_"


def _coerce(value: str, default: Any) -> Any:
    """按默认值的类型转换环境变量字符串。"""
    if isinstance(default, bool):
        return value.lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        try:
            return int(value)
        except ValueError:
            return default
    if isinstance(default, float):
        try:
            return float(value)
        except ValueError:
            return default
    return value


def load(base_dir: str = None, overrides: Dict[str, Any] = None) -> Dict[str, Any]:
    """合并配置：默认值 → config.json → 环境变量（STOCKMON_*）→ 显式 overrides。"""
    cfg = dict(DEFAULTS)

    if base_dir:
        path = os.path.join(base_dir, "config.json")
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
            except (json.JSONDecodeError, OSError):
                pass

    for key, default in DEFAULTS.items():
        env = os.environ.get(ENV_PREFIX + key.upper())
        if env is not None:
            cfg[key] = _coerce(env, default)

    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})
    return cfg
