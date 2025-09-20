# Monitoring System & Docker化方案

## 架构概览
- 单一 FastAPI 服务：启动时注册后台协程执行股票监控，同时提供 REST API 和前端面板。
- 数据采集：每隔固定间隔（默认 10 分钟）调用 `tvs.StockScreener().get()` 获取 150 条股票数据。
- 数据持久化：使用 SQLite（默认 `/app/data/monitor.db`）存储快照和 AnalystRating 变动记录。
- 前端面板：通过 FastAPI 模板 + Chart.js 展示 AnalystRating 变动列表及相邻价格走势。
- Docker 镜像：基于 `python:3.11-slim`，封装服务及依赖，暴露 8000 端口与持久化挂载点。

## 功能模块
### 1. 配置与日志
- `Settings` 类（pydantic-settings）支持环境变量 / `.env` / CLI 参数。
  - 关键参数：抓取间隔、数据库路径、日志等级、最大重试次数等。
- `logging.config.dictConfig` 初始化日志，输出到 stdout 并可选文件；关键事件包含结构化信息。

### 2. 数据模型
- 表 `snapshots(symbol TEXT, retrieved_at DATETIME, analyst_rating TEXT, price REAL, raw_json TEXT, PRIMARY KEY(symbol, retrieved_at))`。
- 表 `rating_changes(id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, changed_at DATETIME, old_rating TEXT, new_rating TEXT, price_before REAL, price_after REAL, snapshot_id INTEGER)`。
- 建立索引 `idx_snapshots_symbol_time` 加速查询，所有写入在单线程事务内完成。

### 3. 后台监控任务
- 初始化数据库（如无表则创建）。
- 每轮执行：
  1. 抓取数据并转换为内部结构。
  2. 将每条记录写入 `snapshots`。
  3. 对比上一条 AnalystRating，若变化则写入 `rating_changes` 并打印 / 记录日志。
- 提供重试机制与错误日志；捕获 `KeyboardInterrupt` 优雅停机。

### 4. API 与前端
- REST 接口：
  - `GET /api/rating_changes`：分页返回变动事件。
  - `GET /api/symbol/{symbol}/history`：返回指定时间窗口的快照数据。
  - `GET /healthz`：返回最近抓取状态供健康检查。
- 前端页面：
  - `/` 提供简易面板（Jinja2 模板 + Tailwind/原生 CSS + Chart.js）。
  - 列表展示最近 AnalystRating 变动，可点击查看窗口内价格走势。

### 5. Docker 化
- Dockerfile 步骤：
  1. 复制项目，并使用 `pip install .` 安装库。
  2. 安装运行依赖：`fastapi`, `uvicorn[standard]`, `pydantic-settings`, `jinja2`, `python-dotenv` 等。
  3. 创建非 root 用户，工作目录 `/app`，准备 `/app/data` 作为卷挂载点。
  4. `ENTRYPOINT` 运行 `uvicorn monitor_app:app --host 0.0.0.0 --port 8000`。
  5. `HEALTHCHECK` 请求 `http://localhost:8000/healthz`。
- README 指引：
  ```bash
  docker build -t tvscreener-monitor .
  docker run -v $(pwd)/data:/app/data -e INTERVAL_SECONDS=600 -p 8000:8000 tvscreener-monitor
  ```

## 验证计划
- 本地运行脚本进行一次抓取，确保数据库与日志生成正确。
- 模拟 AnalystRating 变化验证对比与日志输出。
- 构建 Docker 镜像并运行，访问 `/healthz` 与前端页面确认功能正常。

