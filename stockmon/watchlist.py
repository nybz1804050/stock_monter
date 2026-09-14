"""自选股列表的读写与校验。

存储优先级：
    stocks.json —— 新格式（列表），Web 端增删改都写这里；
    stocks.txt  —— 老格式（每行一个代码，# 注释），只读兼容，首次保存时自动迁移。
"""
import json
import os
import re
from collections.abc import Iterable

CODE_RE = re.compile(r"^\d{6}$")
DEFAULT_CODES = ["600519", "300750", "300059"]


def is_valid_code(code: str) -> bool:
    """A 股代码：6 位数字。"""
    return bool(CODE_RE.match((code or "").strip()))


def _base_dir(base_dir: str = None) -> str:
    return base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def json_path(base_dir: str = None) -> str:
    return os.path.join(_base_dir(base_dir), "stocks.json")


def txt_path(base_dir: str = None) -> str:
    return os.path.join(_base_dir(base_dir), "stocks.txt")


def load(base_dir: str = None) -> list[str]:
    """读取自选股；json 优先，其次 txt，都没有则返回默认列表（不落盘）。"""
    jp = json_path(base_dir)
    if os.path.exists(jp):
        try:
            with open(jp, encoding="utf-8") as f:
                data = json.load(f)
            codes = [str(c).strip() for c in (data if isinstance(data, list) else data.get("codes", []))]
            return [c for c in codes if is_valid_code(c)]
        except (json.JSONDecodeError, OSError):
            pass
    tp = txt_path(base_dir)
    if os.path.exists(tp):
        with open(tp, encoding="utf-8") as f:
            codes = [line.split()[0].strip() for line in f
                     if line.strip() and not line.startswith("#")]
        codes = [c for c in codes if is_valid_code(c)]
        if codes:
            return codes
    return list(DEFAULT_CODES)


def save(codes: Iterable[str], base_dir: str = None) -> list[str]:
    """去重 + 校验后写入 stocks.json，返回实际保存的列表。"""
    cleaned: list[str] = []
    for code in codes:
        code = str(code).strip()
        if is_valid_code(code) and code not in cleaned:
            cleaned.append(code)
    with open(json_path(base_dir), "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    return cleaned


def add(code: str, base_dir: str = None) -> list[str]:
    code = (code or "").strip()
    if not is_valid_code(code):
        raise ValueError("股票代码必须是 6 位数字")
    codes = load(base_dir)
    if code not in codes:
        codes.append(code)
    return save(codes, base_dir)


def remove(code: str, base_dir: str = None) -> list[str]:
    codes = [c for c in load(base_dir) if c != (code or "").strip()]
    return save(codes, base_dir)
