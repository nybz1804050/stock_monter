"""技术指标计算：基于历史价格序列的均线、动量与波动指标。

设计约定（各函数统一遵守，便于前端与接口复用）：

- **纯函数**：只依赖标准库，不读文件、不发请求，输入即全部上下文。
- **输入按时间正序**（最早的在前），与 `HistoryStore.history()` 的返回顺序一致。
- **输出与输入等长**：数据不足的前若干个点用 `None` 占位，这样前端可以直接
  按下标与价格序列对齐，不必再算偏移量。
- 价格为 `None` 的点视为缺失，参与计算时按「跳过」处理，但不会让整条序列报废。

指标口径说明（避免与行情软件的差异引起误读）：

- EMA 用标准递推 `α = 2 / (window + 1)`，并以首个有效价格为种子。
- RSI 用 Wilder 平滑（等价于 `α = 1 / period` 的 EMA），而非简单均值。
- 布林带取的是**总体标准差**（除以 n），与常见行情软件一致。
- MACD 返回 `(dif, dea, hist)` 三条，其中 `hist = (dif - dea) * 2`（国内习惯的柱值）。
"""
from collections.abc import Sequence
from typing import Any, NamedTuple, Optional

Number = Optional[float]


def _clean(values: Sequence[Any]) -> list[Number]:
    """把输入统一成 float 或 None 的列表，非数字一律视为缺失。"""
    out: list[Number] = []
    for v in values or []:
        if v is None:
            out.append(None)
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            out.append(None)
    return out


def sma(values: Sequence[Any], window: int) -> list[Number]:
    """简单移动平均。前 window-1 个点返回 None。

    窗口内遇到 None 时该点返回 None（宁可留空也不给一个缺数据的均值）。
    """
    if window < 1:
        raise ValueError("window 必须大于 0")
    vals = _clean(values)
    out: list[Number] = [None] * len(vals)
    if window > len(vals):
        return out
    # 滑动窗口：进入时加、离开时减，避免每个点都重算一次 sum
    total = 0.0
    missing = 0
    for i, v in enumerate(vals):
        if v is None:
            missing += 1
        else:
            total += v
        if i >= window:
            old = vals[i - window]
            if old is None:
                missing -= 1
            else:
                total -= old
        if i >= window - 1 and missing == 0:
            out[i] = total / window
    return out


def ema(values: Sequence[Any], window: int) -> list[Number]:
    """指数移动平均，以前一个 EMA 值递推；序列开头无值处返回 None。"""
    if window < 1:
        raise ValueError("window 必须大于 0")
    vals = _clean(values)
    out: list[Number] = [None] * len(vals)
    alpha = 2.0 / (window + 1)
    prev: Number = None
    for i, v in enumerate(vals):
        if v is None:
            continue
        prev = v if prev is None else alpha * v + (1 - alpha) * prev
        out[i] = prev
    return out


def rsi(values: Sequence[Any], period: int = 14) -> list[Number]:
    """相对强弱指标（Wilder 平滑），取值 0~100；数据不足处为 None。"""
    if period < 1:
        raise ValueError("period 必须大于 0")
    vals = _clean(values)
    out: list[Number] = [None] * len(vals)
    gains: list[float] = []
    losses: list[float] = []
    avg_gain: Number = None
    avg_loss: Number = None
    prev: Number = None
    for i, v in enumerate(vals):
        if v is None:
            continue
        if prev is not None:
            change = v - prev
            gain = max(change, 0.0)
            loss = max(-change, 0.0)
            if avg_gain is None:                   # 仍在攒够前 period 个变化
                gains.append(gain)
                losses.append(loss)
                if len(gains) == period:
                    avg_gain = sum(gains) / period
                    avg_loss = sum(losses) / period
                    out[i] = _rsi_value(avg_gain, avg_loss)
            else:                                  # Wilder 平滑递推
                avg_gain = (avg_gain * (period - 1) + gain) / period
                avg_loss = (avg_loss * (period - 1) + loss) / period
                out[i] = _rsi_value(avg_gain, avg_loss)
        prev = v
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


class Macd(NamedTuple):
    """MACD 三线；字段名与常见行情软件一致。"""

    dif: list[Number]
    dea: list[Number]
    hist: list[Number]


def macd(values: Sequence[Any], fast: int = 12, slow: int = 26,
         signal: int = 9) -> Macd:
    """MACD：快慢 EMA 之差（DIF）、其 signal 期 EMA（DEA）、以及柱值 HIST。"""
    if fast < 1 or slow < 1 or signal < 1:
        raise ValueError("fast/slow/signal 必须大于 0")
    if fast >= slow:
        raise ValueError("fast 必须小于 slow")
    vals = _clean(values)
    fast_line = ema(vals, fast)
    slow_line = ema(vals, slow)
    dif: list[Number] = [
        None if (f is None or s is None) else f - s
        for f, s in zip(fast_line, slow_line)
    ]
    dea = ema(dif, signal)
    hist: list[Number] = [
        None if (d is None or e is None) else (d - e) * 2
        for d, e in zip(dif, dea)
    ]
    return Macd(dif=dif, dea=dea, hist=hist)


class Bollinger(NamedTuple):
    """布林带：中轨与上下轨。"""

    mid: list[Number]
    upper: list[Number]
    lower: list[Number]


def bollinger(values: Sequence[Any], window: int = 20,
              num_std: float = 2.0) -> Bollinger:
    """布林带：window 日均线为中轨，上下轨为中轨 ± num_std 倍总体标准差。"""
    if window < 1:
        raise ValueError("window 必须大于 0")
    vals = _clean(values)
    mid = sma(vals, window)
    upper: list[Number] = [None] * len(vals)
    lower: list[Number] = [None] * len(vals)
    for i in range(len(vals)):
        if mid[i] is None:
            continue
        window_vals = vals[i - window + 1:i + 1]
        if any(v is None for v in window_vals):
            continue
        mean = mid[i]
        var = sum((v - mean) ** 2 for v in window_vals) / window
        std = var ** 0.5
        upper[i] = mean + num_std * std
        lower[i] = mean - num_std * std
    return Bollinger(mid=mid, upper=upper, lower=lower)


# 支持的指标名 → (计算函数, 默认参数)，供接口层做参数校验与默认值填充。
SUPPORTED = {
    "sma": (sma, {"window": 5}),
    "ema": (ema, {"window": 5}),
    "rsi": (rsi, {"period": 14}),
    "boll": (bollinger, {"window": 20, "num_std": 2.0}),
    "macd": (macd, {"fast": 12, "slow": 26, "signal": 9}),
}


def compute(name: str, values: Sequence[Any], **params: Any):
    """按名字计算指标；未知名字或参数非法时抛 ValueError（供接口转成 400）。"""
    key = str(name or "").strip().lower()
    if key not in SUPPORTED:
        options = "/".join(sorted(SUPPORTED))
        raise ValueError(f"不支持的指标：{name}（可选 {options}）")
    func, defaults = SUPPORTED[key]
    merged = dict(defaults)
    for k, v in (params or {}).items():
        if v is None:
            continue
        try:
            merged[k] = int(v)
        except (TypeError, ValueError):
            raise ValueError(f"参数 {k} 必须是整数") from None
    result = func(values, **merged)
    if isinstance(result, tuple):        # NamedTuple 形式的指标
        return {name: list(seq) for name, seq in zip(result._fields, result)}
    return {"values": result}
