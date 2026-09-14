# -*- coding: utf-8 -*-
"""启动浏览器行情看板。

用法：
    python app.py                     默认 http://127.0.0.1:8000
    python app.py --port 9000         指定端口
    python app.py --interval 3        行情刷新间隔（秒）
    python app.py --open              启动后自动打开浏览器
"""
import argparse
import logging
import threading
import webbrowser

from stockmon.web import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="A 股自选股行情看板（浏览器版）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--interval", type=float, default=5.0, help="行情刷新间隔（秒）")
    parser.add_argument("--threshold", type=float, default=3.0, help="告警阈值（%%）")
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = create_app(interval=args.interval, threshold=args.threshold)
    url = f"http://{args.host}:{args.port}/"
    print(f"行情看板已启动：{url}（Ctrl+C 退出）")
    if args.open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False)


if __name__ == "__main__":
    main()
