"""A 股自选股实时价格监控（控制台版）

依赖 stockmon 包：数据源在东财/腾讯之间自动切换，自选股列表见 stocks.json（兼容 stocks.txt）。

用法：
    python stock_monitor.py          持续刷新监控
    python stock_monitor.py --once   只拉取一次，方便测试
    Ctrl+C 退出
"""
import argparse
import logging
import sys
import time
from datetime import datetime

from stockmon import watchlist
from stockmon.alerts import AlertTracker
from stockmon.datasource import SourceManager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REFRESH_SECONDS = 5
ALERT_THRESHOLD = 3.0
ALERT_LOG = "alerts.log"

RED, GREEN, YELLOW, RESET, BOLD = "\033[31m", "\033[32m", "\033[33m", "\033[0m", "\033[1m"


def enable_ansi_windows() -> None:
    """Windows 旧版 cmd 默认不解析 ANSI 颜色，尝试启用一下，失败无所谓。"""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except Exception:      # noqa: BLE001
            pass


def fmt(value, suffix="") -> str:
    return "--" if value is None else f"{value:.2f}{suffix}"


def render(quotes, now: str, source: str) -> None:
    sys.stdout.write("\033[2J\033[H")          # 清屏 + 光标回左上角
    print(f"{BOLD}A 股自选股实时监控  {now}  数据源:{source}  刷新 {REFRESH_SECONDS}s{RESET}")
    print("-" * 60)
    for q in quotes:
        color = RED if q.direction == "up" else GREEN if q.direction == "down" else ""
        flag = f"{YELLOW} ★{RESET}" if q.pct is not None and abs(q.pct) >= ALERT_THRESHOLD else ""
        print(f"{q.code:<8}{q.name[:6]:<10}{fmt(q.price):>10}"
              f"{color}{fmt(q.pct, '%'):>10}{RESET}{color}{fmt(q.chg):>10}{RESET}{flag}")


def main() -> None:
    parser = argparse.ArgumentParser(description="A 股自选股实时价格监控")
    parser.add_argument("--once", action="store_true", help="只拉取一次")
    parser.add_argument("--interval", type=float, default=REFRESH_SECONDS, help="刷新间隔（秒）")
    parser.add_argument("--threshold", type=float, default=ALERT_THRESHOLD, help="告警阈值（%）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    enable_ansi_windows()

    codes = watchlist.load()
    if not codes:
        print("自选股列表为空，请先在 stocks.json 或 stocks.txt 中添加代码")
        sys.exit(1)

    manager = SourceManager()
    tracker = AlertTracker(threshold=args.threshold, log_file=ALERT_LOG)

    if args.once:
        quotes = manager.fetch(codes)
        for q in quotes:
            print(f"{q.name}({q.code})  现价 {fmt(q.price)}  涨跌幅 {fmt(q.pct, '%')}")
        tracker.check(quotes)
        return

    print(f"已加载 {len(codes)} 只自选股，开始监控……（Ctrl+C 退出）")
    while True:
        try:
            quotes = manager.fetch(codes)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            render(quotes, now, manager.name)
            for item in tracker.check(quotes):
                print(f"{YELLOW}⚠ {item['name']}({item['code']}) {item['kind']} "
                      f"{item['pct']:+.2f}%  现价 {item['price']}{RESET}")
        except Exception as exc:      # noqa: BLE001 —— 网络异常不应终止监控
            print(f"\n{exc}，{args.interval}s 后重试……")
        sys.stdout.flush()
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            break
    print("\n已停止监控。")


if __name__ == "__main__":
    main()
