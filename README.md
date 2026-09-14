# 自选股行情看板（A 股实时监控）

一个轻量的 A 股自选股行情监控工具：命令行里看行情，也可以起一个本地网页看板，
在页面上直接增删要监控的股票。行情数据来自东方财富与腾讯两路公开接口，**主源连续失败会自动切换备源**。

## 功能

- **双数据源自动切换**：主源东方财富（偶尔限流/封 IP），备源腾讯行情；连续失败 2 次自动切换，恢复后自动切回。
- **浏览器看板**：表格展示代码/名称/现价/涨跌幅/涨跌额，涨红跌绿，支持按代码或名称筛选，可手动刷新。
- **页面内管理自选股**：输入 6 位代码即可添加，标签或行情行上点「移除」即删除，改动落盘到 `stocks.json`。
- **涨跌幅告警**：涨跌幅超过阈值（默认 ±3%）时打星标、写入 `alerts.log`，网页右侧实时显示，支持查看历史与清空。
- **两种使用方式**：控制台持续刷新，或浏览器页面（后台服务按间隔拉取并缓存，多个页面共享一份数据）。

## 目录结构

```
stock_monter/
├── app.py                  # 浏览器看板启动入口
├── stock_monitor.py        # 控制台版入口
├── stock.py                # 早期 Tkinter 窗口版（保留）
├── stockmon/               # 核心包
│   ├── quotes.py           # 行情数据结构与归一化
│   ├── datasource.py       # 东财/腾讯数据源与自动切换
│   ├── watchlist.py        # 自选股读写与校验
│   ├── alerts.py           # 涨跌幅告警
│   └── web.py              # Flask 应用与 JSON 接口
├── templates/index.html    # 看板页面
├── static/                 # 页面样式与脚本
├── tests/                  # 离线单元测试（pytest）
├── stocks.txt              # 自选股（旧格式，只读兼容）
└── requirements.txt
```

## 安装

```bash
pip install -r requirements.txt
```

依赖：`requests`（拉取行情）、`flask`（浏览器看板）；测试需要 `pytest`。

## 使用

### 1. 浏览器看板（推荐）

```bash
python app.py                 # http://127.0.0.1:8000
python app.py --port 9000     # 换端口
python app.py --interval 3    # 行情刷新间隔（秒）
python app.py --threshold 5   # 告警阈值（%）
python app.py --open          # 启动后自动打开浏览器
```

打开页面后：上方可筛选、手动刷新；右侧「自选股管理」可增删股票；「涨跌幅告警」可查看历史或清空。

### 2. 控制台监控

```bash
python stock_monitor.py               # 持续刷新
python stock_monitor.py --once        # 只拉一次
python stock_monitor.py --interval 3  # 刷新间隔
python stock_monitor.py --threshold 5 # 告警阈值
```

### 自选股列表

- 网页端增删会自动写入 `stocks.json`（每行一个 6 位代码，带校验与去重）。
- 也兼容旧的 `stocks.txt`：每行一个代码，`#` 开头是注释；当 `stocks.json` 不存在时会读取它。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 行情看板页面 |
| GET | `/api/quotes` | 当前行情快照（含数据源、更新时间、告警、错误信息） |
| GET | `/api/watchlist` | 当前自选股代码列表 |
| POST | `/api/watchlist` | 添加自选股，body `{"code": "600519"}` |
| DELETE | `/api/watchlist/<code>` | 移除自选股 |
| GET | `/api/alerts?history=1` | 告警列表；带 `history=1` 时附带日志历史 |
| DELETE | `/api/alerts` | 清空会话内告警 |
| GET | `/api/health` | 健康检查（是否取到行情、当前数据源） |

## 开发

```bash
python -m pytest tests -q     # 32 个离线用例：解析、数据源切换、自选股、告警、接口
```

测试全部走本地样例报文与假数据源，不访问网络。

## 说明

- 行情来自公开接口，可能有延迟或缺失（缺失字段在页面上显示 `--`）。
- 数据仅供参考，不构成投资建议。
