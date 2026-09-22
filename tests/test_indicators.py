"""indicators 模块：均线/动量/波动指标的数值正确性与边界行为。"""
import pytest

from stockmon import indicators

# ---------- 简单移动平均 ----------

def test_sma_basic():
    assert indicators.sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_sma_window_one_returns_self():
    assert indicators.sma([1.5, 2.5], 1) == [1.5, 2.5]


def test_sma_short_series_is_all_none():
    assert indicators.sma([1, 2], 5) == [None, None]


def test_sma_missing_value_makes_that_point_none():
    """窗口里出现缺失值时不给出"缺数据的均值"，宁可留空。"""
    assert indicators.sma([1, None, 3], 2) == [None, None, None]
    # 缺失值滑出窗口后又可以正常计算
    assert indicators.sma([1, None, 3, 4], 2) == [None, None, None, 3.5]


def test_sma_rejects_bad_window():
    with pytest.raises(ValueError):
        indicators.sma([1, 2, 3], 0)


def test_sma_accepts_strings_from_api():
    """行情接口给的是字符串数字，应能直接算。"""
    assert indicators.sma(["1", "2", "3"], 3) == [None, None, 2.0]


# ---------- 指数移动平均 ----------

def test_ema_seeds_with_first_value():
    out = indicators.ema([1, 2, 3], 2)
    assert out[0] == 1.0
    assert out[1] == pytest.approx(5 / 3)
    assert out[2] == pytest.approx(23 / 9)


def test_ema_constant_series_stays_constant():
    assert indicators.ema([7, 7, 7, 7], 3) == [7.0, 7.0, 7.0, 7.0]


def test_ema_leading_none_stays_none():
    assert indicators.ema([None, None, 4, 4], 2)[:2] == [None, None]


# ---------- RSI ----------

def test_rsi_all_gains_is_100():
    out = indicators.rsi([1, 2, 3, 4, 5], period=3)
    assert out[-1] == 100.0


def test_rsi_all_losses_is_0():
    out = indicators.rsi([5, 4, 3, 2, 1], period=3)
    assert out[-1] == 0.0


def test_rsi_warms_up_gradually():
    """前 period 个变化用来做种子，更早的点没有值。"""
    out = indicators.rsi([1, 2, 3, 4, 5], period=3)
    assert out[:3] == [None, None, None]
    assert out[3] == 100.0


def test_rsi_flat_series_is_neutral():
    assert indicators.rsi([5, 5, 5, 5], period=2)[-1] == 50.0


def test_rsi_rejects_bad_period():
    with pytest.raises(ValueError):
        indicators.rsi([1, 2, 3], period=0)


# ---------- MACD ----------

def test_macd_returns_three_aligned_series():
    values = list(range(1, 60))
    result = indicators.macd(values)
    assert set(result._fields) == {"dif", "dea", "hist"}
    for series in result:
        assert len(series) == len(values)


def test_macd_hist_is_double_the_gap():
    """国内习惯的柱值是 (DIF - DEA) * 2。"""
    values = [10, 11, 12, 11, 13, 14, 15, 14, 16, 17, 18, 17, 19, 20, 21]
    result = indicators.macd(values, fast=3, slow=6, signal=3)
    for d, e, h in zip(result.dif, result.dea, result.hist):
        if d is None or e is None or h is None:
            continue
        assert h == pytest.approx((d - e) * 2)


def test_macd_rejects_fast_ge_slow():
    with pytest.raises(ValueError):
        indicators.macd([1, 2, 3], fast=26, slow=12)


# ---------- 布林带 ----------

def test_bollinger_midline_equals_sma():
    values = [1, 2, 3, 4, 5, 6]
    band = indicators.bollinger(values, window=3, num_std=2.0)
    assert band.mid == indicators.sma(values, 3)


def test_bollinger_band_width():
    """[1,2,3] 均值 2、总体标准差 sqrt(2/3)，上下轨各偏 2 倍标准差。"""
    band = indicators.bollinger([1, 2, 3], window=3, num_std=2.0)
    std = (2 / 3) ** 0.5
    assert band.mid[2] == pytest.approx(2.0)
    assert band.upper[2] == pytest.approx(2.0 + 2 * std)
    assert band.lower[2] == pytest.approx(2.0 - 2 * std)


def test_bollinger_constant_series_has_zero_width():
    band = indicators.bollinger([5, 5, 5, 5], window=3, num_std=2.0)
    assert band.upper[3] == pytest.approx(5.0)
    assert band.lower[3] == pytest.approx(5.0)


def test_bollinger_rejects_bad_window():
    with pytest.raises(ValueError):
        indicators.bollinger([1, 2, 3], window=0)


# ---------- 统一入口 compute ----------

def test_compute_dispatches_single_series():
    assert indicators.compute("sma", [1, 2, 3], window=3)["values"][-1] == 2.0


def test_compute_returns_named_series_for_multi_output():
    out = indicators.compute("macd", list(range(1, 30)))
    assert set(out) == {"dif", "dea", "hist"}


def test_compute_uses_defaults_when_params_absent():
    assert indicators.compute("sma", [1, 2, 3, 4, 5])["values"][-1] == 3.0


def test_compute_rejects_unknown_name():
    with pytest.raises(ValueError) as exc:
        indicators.compute("kdj", [1, 2, 3])
    assert "不支持" in str(exc.value)


def test_compute_rejects_non_integer_param():
    with pytest.raises(ValueError):
        indicators.compute("sma", [1, 2, 3], window="abc")
