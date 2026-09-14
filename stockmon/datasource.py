# -*- coding: utf-8 -*-
"""行情数据源：东方财富（主）/ 腾讯（备），带连续失败自动切换。

两个数据源都返回 [Quote, ...]；任何异常都向上抛，由 SourceManager 决定是否切换。
"""
import logging
import time
from typing import Callable, Dict, List

import requests

from .quotes import normalize_all

log = logging.getLogger(__name__)

EASTMONEY_URL = ("https://push2.eastmoney.com/api/qt/ulist.np/get"
                 "?fltt=2&secids={secids}&fields=f2,f3,f4,f12,f14")
TENCENT_URL = "https://qt.gtimg.cn/q={codes}"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "*/*",
}
TIMEOUT = 6
FAILS_TO_SWITCH = 2      # 连续失败几次后切换数据源
RETRIES = 1              # 单个数据源内部的瞬时失败重试次数
BACKOFF = 0.5            # 重试前等待秒数（线性退避）


def eastmoney_secid(code: str) -> str:
    """代码 → 东财 secid（6 开头沪市=1，其余深市/北交所=0）。"""
    return ("1." if code.startswith("6") else "0.") + code


def tencent_code(code: str) -> str:
    """代码 → 腾讯代码（带市场前缀 sh/sz/bj）。"""
    if code.startswith("6"):
        return "sh" + code
    if code.startswith(("8", "4", "92")):
        return "bj" + code
    return "sz" + code


def parse_eastmoney(payload: dict) -> List[dict]:
    """解析东财 ulist 返回体（抽成纯函数，便于离线测试）。"""
    diff = (payload.get("data") or {}).get("diff") or []
    if isinstance(diff, dict):          # 单只股票时 diff 是对象
        diff = list(diff.values())
    return [{"code": d.get("f12"), "name": d.get("f14"), "price": d.get("f2"),
             "pct": d.get("f3"), "chg": d.get("f4")} for d in diff]


def parse_tencent(text: str) -> List[dict]:
    """解析腾讯行情文本（v_sh600519="1~贵州茅台~600519~..."; 以 ~ 分隔，GBK 解码后传入）。"""
    out = []
    for line in (text or "").strip().split(";"):
        line = line.strip()
        if not line.startswith("v_") or '"' not in line:
            continue
        fields = line.split('"')[1].split("~")
        if len(fields) < 33:
            continue
        out.append({"code": fields[2], "name": fields[1], "price": fields[3],
                    "chg": fields[31], "pct": fields[32]})
    return out


def _request(url: str, headers: dict, retries: int = RETRIES, backoff: float = BACKOFF):
    """带重试与线性退避的 GET：网络类异常才重试，最后一次仍失败则抛出。"""
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return requests.get(url, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as exc:      # 连接/超时类问题值得重试
            last_exc = exc
            if attempt < retries:
                log.debug("请求失败（第 %d 次），%.1fs 后重试：%s", attempt + 1, backoff * (attempt + 1), exc)
                time.sleep(backoff * (attempt + 1))
    raise last_exc


def fetch_eastmoney(codes: List[str]) -> List[dict]:
    resp = _request(EASTMONEY_URL.format(secids=",".join(eastmoney_secid(c) for c in codes)), HEADERS)
    quotes = normalize_all(parse_eastmoney(resp.json()), source="eastmoney")
    if not quotes:
        raise ValueError("eastmoney 返回空数据")
    return quotes


def fetch_tencent(codes: List[str]) -> List[dict]:
    resp = _request(TENCENT_URL.format(codes=",".join(tencent_code(c) for c in codes)),
                    {"User-Agent": HEADERS["User-Agent"]})
    quotes = normalize_all(parse_tencent(resp.content.decode("gbk", errors="replace")),
                           source="tencent")
    if not quotes:
        raise ValueError("tencent 返回空数据")
    return quotes


FETCHERS: Dict[str, Callable[[List[str]], List[dict]]] = {
    "eastmoney": fetch_eastmoney,
    "tencent": fetch_tencent,
}


class SourceManager:
    """维护当前数据源；连续失败 FAILS_TO_SWITCH 次后自动切到另一个源。"""

    def __init__(self, primary: str = "eastmoney", fails_to_switch: int = FAILS_TO_SWITCH):
        self.name = primary
        self.fails = 0
        self.fails_to_switch = fails_to_switch

    @property
    def backup(self) -> str:
        return "tencent" if self.name == "eastmoney" else "eastmoney"

    def fetch(self, codes: List[str]) -> List[dict]:
        """用当前源拉取；失败累计到阈值就切换并抛错，让调用方下一轮用新源。"""
        try:
            quotes = FETCHERS[self.name](codes)
            if self.fails:
                log.info("数据源 %s 已恢复", self.name)
            self.fails = 0
            return quotes
        except Exception as exc:            # noqa: BLE001 —— 网络类异常都要兜住
            self.fails += 1
            if self.fails >= self.fails_to_switch:
                log.warning("数据源 %s 连续失败 %d 次，切换到 %s",
                            self.name, self.fails, self.backup)
                self.name, self.fails = self.backup, 0
                raise RuntimeError(f"数据源已切换到 {self.name}，下一轮用新源重试") from exc
            raise RuntimeError(f"{self.name} 拉取失败：{exc}") from exc
