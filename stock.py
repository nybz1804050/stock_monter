"""A 股自选股实时价格监控（双数据源自动切换）—— 极简 GUI 窗口版

数据源：
    主源：东方财富 push2.eastmoney.com（限流较多，偶尔封 IP）
    备源：腾讯行情 qt.gtimg.cn（宽松稳定）
    东财连续失败 2 次自动切腾讯，东财恢复后自动切回。

用法：
    python stock_monitor.py          启动 GUI 窗口，持续刷新
    Ctrl+C 或关闭窗口退出

自选股列表在 stocks.txt 里维护，每行一个代码，# 开头为注释。
"""
import sys
import tkinter as tk
from datetime import datetime
from tkinter import ttk

import requests

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

# 颜色定义（GUI 用）
COLOR_RISE = "#FF4444"      # 涨（红）
COLOR_FALL = "#00AA00"     # 跌（绿）
COLOR_ALERT = "#FFAA00"    # 告警标记（橙）

# 数据源状态：{"name": 当前源, "fails": 连续失败次数}
SOURCE = {"name": "eastmoney", "fails": 0}

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
    for _name, fetcher in (
        (SOURCE["name"], fetch_eastmoney if SOURCE["name"] == "eastmoney" else fetch_tencent),
    ):
        try:
            quotes = fetcher(codes)
            if SOURCE["fails"]:
                print(f"[数据源 {SOURCE['name']} 恢复正常]")
            SOURCE["fails"] = 0
            return quotes
        except Exception as e:
            SOURCE["fails"] += 1
            if SOURCE["fails"] >= 2:
                new = "tencent" if SOURCE["name"] == "eastmoney" else "eastmoney"
                print(f"[数据源 {SOURCE['name']} 连续失败，切换到 {new}]")
                SOURCE["name"], SOURCE["fails"] = new, 0
                raise RuntimeError(f"数据源已切换到 {new}，下一轮用新源重试") from e
            raise RuntimeError(f"{SOURCE['name']} 拉取失败：{e}") from e

def fmt_num(v, suffix=""):
    return "--" if v is None else f"{v:.2f}{suffix}"

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
            print(f"⚠ {msg}")
            with open(ALERT_LOG, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        alert_state[q["code"]] = crossing


class StockMonitorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("A股自选股监控")
        self.root.geometry("600x400")
        self.root.attributes("-topmost", True)   # 窗口始终置顶

        # 数据
        self.codes = load_codes()
        if not self.codes:
            tk.messagebox.showerror("错误", "stocks.txt 中没有有效股票代码")
            self.root.destroy()
            return
        self.alert_state = {}
        self.quotes = []

        # 顶部信息栏：时间、数据源、刷新间隔
        self.info_var = tk.StringVar()
        info_label = tk.Label(root, textvariable=self.info_var, anchor="w", font=("Arial", 10))
        info_label.pack(fill="x", padx=10, pady=5)

        # Treeview 表格
        columns = ("代码", "名称", "现价", "涨跌幅", "涨跌额", "提醒")
        self.tree = ttk.Treeview(root, columns=columns, show="headings", height=15)
        for col in columns:
            self.tree.heading(col, text=col)
            if col in ("代码", "名称"):
                self.tree.column(col, width=80, anchor="center")
            elif col == "提醒":
                self.tree.column(col, width=60, anchor="center")
            else:
                self.tree.column(col, width=100, anchor="e")
        self.tree.pack(fill="both", expand=True, padx=10, pady=5)

        # 状态栏（显示刷新状态）
        self.status_var = tk.StringVar(value="就绪")
        status_bar = tk.Label(root, textvariable=self.status_var, anchor="w", relief="sunken", font=("Arial", 9))
        status_bar.pack(fill="x", padx=10, pady=(0, 5))

        # 启动定时刷新
        self.update_data()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def update_data(self):
        """拉取数据并更新界面，同时检查告警"""
        try:
            self.status_var.set("正在拉取数据...")
            quotes = fetch_quotes(self.codes)
            self.quotes = quotes
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.info_var.set(f"更新时间：{now}  数据源：{SOURCE['name']}  刷新间隔：{REFRESH_SECONDS}s")

            # 检查告警（写入日志）
            check_alerts(quotes, self.alert_state, now)

            # 刷新表格
            self.update_table(quotes)
            self.status_var.set(f"更新成功  {len(quotes)} 只股票")
        except Exception as e:
            self.status_var.set(f"更新失败：{e}，{REFRESH_SECONDS}s 后重试...")
            print(f"更新失败：{e}")

        # 定时下一次刷新
        self.root.after(REFRESH_SECONDS * 1000, self.update_data)

    def update_table(self, quotes):
        """清空并重新填充表格，带颜色和告警标记"""
        # 清空现有行
        for item in self.tree.get_children():
            self.tree.delete(item)

        for q in quotes:
            pct = q["pct"]
            chg = q["chg"]
            # 涨跌颜色
            if pct is not None and pct > 0:
                color = COLOR_RISE
            elif pct is not None and pct < 0:
                color = COLOR_FALL
            else:
                color = "black"

            # 告警标记
            alert_flag = "★" if (pct is not None and abs(pct) >= ALERT_THRESHOLD) else ""

            # 插入行，使用tag标记颜色
            values = (
                q["code"],
                q["name"][:6],
                fmt_num(q["price"]),
                fmt_num(pct, "%"),
                fmt_num(chg),
                alert_flag
            )
            item = self.tree.insert("", "end", values=values)
            # 设置颜色（只对价格、涨跌幅、涨跌额三列）
            for col_idx in (2, 3, 4):  # 现价、涨跌幅、涨跌额
                self.tree.tag_configure(f"color_{col_idx}", foreground=color)
                self.tree.item(item, tags=(f"color_{col_idx}",))

    def on_close(self):
        """关闭窗口时退出程序"""
        self.root.destroy()
        sys.exit(0)


def main():
    # 若无有效股票代码则退出
    codes = load_codes()
    if not codes:
        print("stocks.txt 里没有有效代码，请添加后重试")
        sys.exit(1)

    root = tk.Tk()
    StockMonitorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
