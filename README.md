# 自选股行情看板（A 股实时监控）

一个轻量的 A 股自选股行情监控工具：命令行里看行情，也可以起一个本地网页看板，
在页面上直接增删要监控的股票。行情数据来自东方财富与腾讯两路公开接口，**主源连续失败会自动切换备源**。

## 功能

- **双数据源自动切换**：主源东方财富（偶尔限流/封 IP），备源腾讯行情；连续失败 2 次自动切换，恢复后自动切回；单个源内部对瞬时网络错误做重试 + 线性退避。
- **浏览器看板**：表格展示代码/名称/现价/涨跌幅/涨跌额，涨红跌绿，支持按代码或名称筛选，**点击表头可排序**。
- **迷你走势图**：每行绘制最近 60 个价格点的走势线（涨红跌绿），数据来自本地 SQLite 历史库。
- **实时推送**：服务端 SSE（`/api/stream`）推送每轮行情，前端断线自动退回定时轮询。
- **页面内管理自选股**：输入 6 位代码即可添加，标签或行情行上点「移除」即删除，改动落盘到 `stocks.json`。
- **涨跌幅告警**：涨跌幅超过阈值（默认 ±3%）时打星标、写入 `alerts.log`，网页右侧实时显示，支持查看历史与清空。
- **两种使用方式**：控制台持续刷新，或浏览器页面（后台服务按间隔拉取并缓存，多个页面共享一份数据）。
- **可配置 / 可容器化**：`config.json` + `STOCKMON_*` 环境变量；附带 Dockerfile 与 GitHub Actions CI。

## 目录结构

```
stock_monter/
├── app.py                  # 浏览器看板启动入口
├── stock_monitor.py        # 控制台版入口
├── stock.py                # 早期 Tkinter 窗口版（保留）
├── stockmon/               # 核心包
│   ├── quotes.py           # 行情数据结构与归一化
│   ├── datasource.py       # 东财/腾讯数据源、自动切换与重试
│   ├── watchlist.py        # 自选股读写与校验
│   ├── alerts.py           # 涨跌幅告警
│   ├── storage.py          # SQLite 行情历史
│   ├── config.py           # 配置加载（默认值/文件/环境变量）
│   └── web.py              # Flask 应用、JSON 接口与 SSE
├── config.example.json     # 配置示例
├── Dockerfile              # 容器化部署
├── templates/index.html    # 看板页面
├── static/                 # 页面样式与脚本
├── tests/                  # 离线单元测试（pytest，45 个用例）
├── pyproject.toml          # ruff / pytest 配置
├── .github/workflows/ci.yml# CI：lint + 测试
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

## 配置

优先级：默认值 < `config.json` < 环境变量（`STOCKMON_*`）< 命令行参数。

```json
{ "interval": 5.0, "threshold": 3.0, "host": "127.0.0.1", "port": 8000, "retries": 2 }
```

```bash
STOCKMON_INTERVAL=3 STOCKMON_PORT=9000 python app.py
```

可配置项见 `stockmon/config.py` 的 `DEFAULTS`（刷新间隔、告警阈值、监听地址端口、请求超时与重试、历史库路径等）。

## 容器化部署

```bash
docker build -t stock-monter .
docker run -d -p 8000:8000 -v $(pwd)/data:/app/data stock-monter
```

容器内默认监听 `0.0.0.0:8000`，自选股与历史库写入挂载的 `/app/data`。

## 开发

```bash
python -m pytest tests -q     # 45 个离线用例：解析、数据源切换/重试、自选股、告警、历史、配置、接口
ruff check .                  # 代码规范检查（pyproject.toml 配置）
```

测试全部走本地样例报文与假数据源，不访问网络；CI（GitHub Actions）在 Python 3.9/3.11 上跑 lint + 测试。

## 说明

- 行情来自公开接口，可能有延迟或缺失（缺失字段在页面上显示 `--`）。
- 数据仅供参考，不构成投资建议。
