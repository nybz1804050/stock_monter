"""行情数据结构与解析结果的归一化。"""
from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass
class Quote:
    """单只股票的实时行情快照。"""

    code: str
    name: str
    price: Optional[float] = None
    chg: Optional[float] = None      # 涨跌额
    pct: Optional[float] = None      # 涨跌幅（%）
    source: str = ""                 # 哪个数据源给出的

    @property
    def direction(self) -> str:
        """up / down / flat —— 供前端着色使用。"""
        if self.pct is None or self.pct == 0:
            return "flat"
        return "up" if self.pct > 0 else "down"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["direction"] = self.direction
        return data


def _to_float(value: Any) -> Optional[float]:
    """把行情接口里的数字字段转成 float；'-'、None、空串统一视为无值。"""
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize(raw: dict[str, Any], source: str = "") -> Optional[Quote]:
    """把数据源返回的原始 dict 归一化成 Quote，字段缺失则返回 None。"""
    code = str(raw.get("code") or "").strip()
    name = str(raw.get("name") or "").strip()
    if not code or not name:
        return None
    return Quote(
        code=code,
        name=name,
        price=_to_float(raw.get("price")),
        chg=_to_float(raw.get("chg")),
        pct=_to_float(raw.get("pct")),
        source=source,
    )


def normalize_all(items: list[dict[str, Any]], source: str = "") -> list[Quote]:
    quotes = [normalize(it, source) for it in items or []]
    return [q for q in quotes if q is not None]


def quote_map(quotes: list[Quote]) -> dict[str, Quote]:
    """代码 → Quote，便于按自选股顺序回填。"""
    return {q.code: q for q in quotes}
