# -*- coding: utf-8 -*-
"""A 股自选股实时价格监控（双数据源自动切换）

数据源：
    主源：东方财富 push2.eastmoney.com（限流较多，偶尔封 IP）
    备源：腾讯行情 qt.gtimg.cn（宽松稳定）
    东财连续失败 2 次自动切腾讯，东财恢复后自动切回。

用法：
    python stock_monitor.py          持续刷新监控
    python stock_monitor.py --once   只拉取一次，方便测试
    Ctrl+C 退出

自选股列表在 stocks.txt 里维护，每行一个代码，# 开头为注释。
"""
import sys
import time
from datetime import datetime

import requests

# Windows 下 Python 默认按 GBK 输出，Git Bash 按 UTF-8 显示会乱码，统一成 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------- 配置 ----------
REFRESH_SECONDS = 5          # 刷新间隔（秒）
ALERT_THRESHOLD = 3.0        # 涨跌幅提醒阈值（%），超过即记录到 alerts.log
STOCKS_FILE = "stocks.txt"   # 自选股列表，每行一个代码
ALERT_LOG = "alerts.log"

EASTMONEY_URL = ("https://push2.eastmoney.com/api/qt/ulist.np/get"
                 "?fltt=2&secids={secids}&fields=f2,f3,f4,f12,f14")
TENCENT_URL = "https://qt.gtimg.cn/q={codes}"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "*/*",
}

RED = "\033[31m"      # 涨
GREEN = "\033[32m"    # 跌
YELLOW = "\033[33m"   # 告警
RESET = "\033[0m"
BOLD = "\033[1m"

# 数据源状态：{"name": 当前源, "fails": 连续失败次数}
SOURCE = {"name": "eastmoney", "fails": 0}

def enable_ansi_windows():
    """Windows 旧版 cmd 默认不解析 ANSI 颜色，尝试启用一下，失败无所谓。"""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

def eastmoney_secid(code):
    """代码 → 东财 secid（6 开头沪市=1，深市/北交所=0）。"""
    return ("1." if code.startswith("6") else "0.") + code

def tencent_code(code):
    """代码 → 腾讯代码（带市场前缀：sh/sz/bj）。"""
    if code.startswith("6"):
        return "sh" + code
    if code.startswith(("8", "4", "92")):
        return "bj" + code
    return "sz" + code

def load_codes():
    """读取 stocks.txt；不存在则创建一份带示例的。"""
    try:
        with open(STOCKS_FILE, encoding="utf-8") as f:
            codes = [
                line.split()[0].strip()
                for line in f
                if line.strip() and not line.startswith("#")
            ]
        return [c for c in codes if c]
    except FileNotFoundError:
        with open(STOCKS_FILE, "w", encoding="utf-8") as f:
            f.write("# 每行一个股票代码，# 开头为注释，例如：\n600519\n300750\n300059\n")
        return ["600519", "300750", "300059"]

def fetch_eastmoney(codes):
    """东财批量实时行情，返回 [{code, name, price, pct, chg}, ...]。"""
    resp = requests.get(
        EASTMONEY_URL.format(secids=",".join(eastmoney_secid(c) for c in codes)),
        headers=HEADERS, timeout=6,
    )
    diff = (resp.json().get("data") or {}).get("diff") or []
    if isinstance(diff, dict):          # 单只股票时 diff 是对象，兼容一下
        diff = list(diff.values())
    quotes = []
    for d in diff:
        try:
            quotes.append({
                "code": d.get("f12", "--"),
                "name": d.get("f14", "--"),
                "price": float(d["f2"]) if d.get("f2") not in (None, "-") else None,
                "pct": float(d["f3"]) if d.get("f3") not in (None, "-") else None,
                "chg": float(d["f4"]) if d.get("f4") not in (None, "-") else None,
            })
        except (TypeError, ValueError, KeyError):
            continue
    if not quotes:
        raise ValueError("eastmoney 返回空数据")
    return quotes

def fetch_tencent(codes):
    """腾讯批量实时行情（GBK 编码，~ 分隔），返回同结构列表。"""
    resp = requests.get(
        TENCENT_URL.format(codes=",".join(tencent_code(c) for c in codes)),
        headers={"User-Agent": HEADERS["User-Agent"]}, timeout=6,
    )
    text = resp.content.decode("gbk", errors="replace")
    quotes = []
    for line in text.strip().split(";"):
        line = line.strip()
        if not line.startswith("v_") or '"' not in line:
            continue                        # 跳过空行和 v_pv_none_match（未匹配）
        f = line.split('"')[1].split("~")
        try:
            quotes.append({
                "code": f[2],
                "name": f[1],
                "price": float(f[3]),
                "chg": float(f[31]),
                "pct": float(f[32]),
            })
        except (IndexError, ValueError):
            continue
    if not quotes:
        raise ValueError("tencent 返回空数据")
    return quotes

def fetch_quotes(codes):
    """按当前源拉取；连续失败 2 次自动切换数据源。"""
    for name, fetcher in (
        (SOURCE["name"], fetch_eastmoney if SOURCE["name"] == "eastmoney" else fetch_tencent),
    ):
        try:
            quotes = fetcher(codes)
            if SOURCE["fails"]:
                print(f"{YELLOW}[数据源 {SOURCE['name']} 恢复正常]{RESET}")
            SOURCE["fails"] = 0
            return quotes
        except Exception as e:
            SOURCE["fails"] += 1
            if SOURCE["fails"] >= 2:
                new = "tencent" if SOURCE["name"] == "eastmoney" else "eastmoney"
                print(f"{YELLOW}[数据源 {SOURCE['name']} 连续失败，切换到 {new}]{RESET}")
                SOURCE["name"], SOURCE["fails"] = new, 0
                raise RuntimeError(f"数据源已切换到 {new}，下一轮用新源重试")
            raise RuntimeError(f"{SOURCE['name']} 拉取失败：{e}")

def fmt_num(v, suffix=""):
    return "--" if v is None else f"{v:.2f}{suffix}"

def render(quotes, now):
    sys.stdout.write("\033[2J\033[H")   # 清屏，光标回左上角
    # print(f"{BOLD}A 股自选股实时监控  {now}  数据源:{SOURCE['name']}  "
    #       f"刷新间隔 {REFRESH_SECONDS}s{RESET}")
    # print("-" * 66)
    # print(f"{'代码':<8}{'名称':<12}{'现价':>10}{'涨跌幅':>10}{'涨跌额':>10}")
    # print("-" * 66)
    for q in quotes:
        color = RED if (q["pct"] or 0) > 0 else GREEN if (q["pct"] or 0) < 0 else ""
        flag = f"{YELLOW} ★{RESET}" if q["pct"] is not None and abs(q["pct"]) >= ALERT_THRESHOLD else ""
        name = q["name"][:6]  # 名称过长截断，保持对齐
        print(f"{q['code']:<8}{name:<10}{fmt_num(q['price']):>12}"
              f"{color}{fmt_num(q['pct'], '%'):>11}{RESET}{color}{fmt_num(q['chg']):>11}{RESET}{flag}")
    # print("-" * 66)
    # print(f"涨跌幅超过 ±{ALERT_THRESHOLD}% 会标 ★ 并写入 {ALERT_LOG}，Ctrl+C 退出")

def check_alerts(quotes, alert_state, now):
    """涨跌幅越过阈值时记录一条告警，同一轮越过只记一次。"""
    for q in quotes:
        pct = q["pct"]
        if pct is None:
            continue
        crossing = abs(pct) >= ALERT_THRESHOLD
        if crossing and not alert_state.get(q["code"], False):
            msg = (f"[{now}] {q['name']}({q['code']}) "
                   f"{'大涨' if pct > 0 else '大跌'} {pct:+.2f}%  现价 {q['price']}")
            print(f"\n{YELLOW}⚠ {msg}{RESET}")
            with open(ALERT_LOG, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        alert_state[q["code"]] = crossing

def main():
    enable_ansi_windows()
    codes = load_codes()
    if not codes:
        print("stocks.txt 里没有有效代码，请添加后重试")
        sys.exit(1)

    if "--once" in sys.argv:
        quotes = None
        for name, fetcher in (("eastmoney", fetch_eastmoney), ("tencent", fetch_tencent)):
            try:
                quotes = fetcher(codes)
                print(f"[数据源 {name}]")
                break
            except Exception:
                continue
        if quotes is None:
            print("两个数据源都拉取失败，稍后再试")
            sys.exit(1)
        for q in quotes:
            print(f"{q['name']}({q['code']})  现价 {fmt_num(q['price'])}  "
                  f"涨跌幅 {fmt_num(q['pct'], '%')}")
        return

    alert_state = {}
    print(f"已加载 {len(codes)} 只自选股，开始监控……")
    while True:
        try:
            quotes = fetch_quotes(codes)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            render(quotes, now)
            check_alerts(quotes, alert_state, now)
        except Exception as e:
            print(f"\n{e}，{REFRESH_SECONDS}s 后重试……")
        sys.stdout.flush()
        try:
            time.sleep(REFRESH_SECONDS)
        except KeyboardInterrupt:
            break
    print("\n已停止监控。")

if __name__ == "__main__":
    main()
