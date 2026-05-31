# A股科技细分ETF量化交易系统

> 个人学习用途，不作为投资参考。

本项目是本地运行的 A股科技类 ETF 半自动量化辅助交易系统，覆盖自动数据拉取、数据缓存、指标、评分、策略、风控、回测、日报、日志、图表、CLI 和 Streamlit 面板。系统只生成交易辅助建议、风险状态、策略信号和回测结果，不连接券商接口，不自动下单。

## v2.0 工作台

v2.0 的目标不是堆功能，而是把 v1.0 工具打磨成每天能打开看的个人量化工作台：

- 策略注册系统：策略统一注册、统一评估，默认包含趋势追涨、强趋势回调、风控测试仓。
- 信号中心：按日期生成 `reports/signals/{date}_signal_center.csv/json`，包含信号、置信度、风控权限、失效条件和解释。
- 更完整的盘中自动刷新：固定刷新槽仍为 9:35、10:35、11:30、13:30、14:35，并生成刷新状态。
- 定时任务：CLI 支持查看计划、运行到期刷新槽、本地循环调度。
- 更强的回测可信度：保留次日开盘成交、防前视、滑点、手续费、100 份约束，并输出信号轨迹和更多绩效诊断。
- 风控状态持久化：风险状态落盘到 `data/state/risk_state.json`，页面和 CLI 均可同步。
- Streamlit Cloud 稳定部署：内置部署健康检查，主文件路径固定为 `app/streamlit_app.py`。
- 页面体验重构：面板升级为工作台、信号中心、盘中刷新、风控状态、回测实验室、报告中心、配置数据、部署健康和 UZI 项目分析。
- 更专业的报告和可解释信号：日报内置信号中心解释表，不只给结论，也给触发原因和失效条件。

## 数据架构

系统按“一次性交付”的原则内置完整数据链路，不要求每天手动上传快照。

优先级固定为：

```text
自动数据源优先 → 本地缓存兜底 → 手动CSV只兜底
```

- 日线：优先通过 AKShare `fund_etf_hist_em` 自动拉取并增量更新，缓存到 `data/raw/` 和 `data/processed/`。
- 盘中：优先通过 AKShare `fund_etf_spot_em` 自动拉取 ETF 实时行情，缓存到 `data/cache/realtime_etf_spot.csv` 和 `data/snapshots/`。
- 本地缓存：自动数据源失败时读取最近一次实时行情缓存。
- 手动 CSV：只有自动源和缓存都不可用时，才读取 `data/snapshots/input_snapshot.csv` 作为兜底。

固定盘中刷新时间：

```text
09:35 集合竞价后
10:35
11:30
13:30
14:35
```

## 风险声明

本系统仅用于个人学习、交易辅助和策略复盘，不构成投资建议。ETF 价格会波动，科技类 ETF 波动尤其明显。系统可能产生错误信号，历史回测不代表未来收益，交易风险由使用者自行承担。

## 安装

```powershell
cd E:\tech_etf_quant_system_full_spec_v1
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

如果使用 uv：

```powershell
uv sync
```

## 初始化

```powershell
python -m tech_etf_quant.cli init
```

初始化会创建 `config/`、`data/`、`logs/`、`reports/` 等目录，并准备交易日志、观察日志、风控日志和错误日志。

## 更新数据

```powershell
python -m tech_etf_quant.cli update-data
```

系统优先使用 AKShare 的 `fund_etf_hist_em` 下载前复权 ETF 日线数据，保存到：

- `data/raw/{symbol}.csv`
- `data/processed/{symbol}.csv`

如果外部数据源不可用，系统会记录到 `logs/error_log.csv` 并生成确定性的本地样例行情，确保评分、日报、回测和面板仍可运行。

离线生成样例数据：

```powershell
python -m tech_etf_quant.cli update-data --sample-only
```

## ETF池修改

ETF 池在 `config/etf_pool.csv`：

```csv
symbol,name,group,role,priority,enabled,notes
```

将 `enabled` 改成 `true` 或 `false` 可以控制是否纳入系统。策略和评分不会硬编码 ETF 池，启动时会读取该配置。

## 生成评分

```powershell
python -m tech_etf_quant.cli score --date 2026-05-31
```

输出保存到：

```text
reports/daily/{date}_ranking.csv
```

## 生成日报

```powershell
python -m tech_etf_quant.cli report --date 2026-05-31
```

输出：

- `reports/daily/{date}_daily_report.md`
- `reports/daily/{date}_daily_report.html`

## 运行回测

```powershell
python -m tech_etf_quant.cli backtest --start 2021-01-01 --end 2026-05-31
```

输出：

- `reports/backtest/equity_curve.csv`
- `reports/backtest/trades.csv`
- `reports/backtest/positions.csv`
- `reports/backtest/performance.json`
- `reports/backtest/backtest_report.html`
- `reports/charts/equity_curve.png`
- `reports/charts/drawdown_curve.png`
- `reports/charts/trade_points.html`

## 启动面板

```powershell
streamlit run app/streamlit_app.py
```

或：

```powershell
python -m tech_etf_quant.cli dashboard
```

面板固定绑定 `localhost`；端口由 Streamlit 自动选择并打印在终端里，例如 `http://localhost:8501`。面板包含首页概览、ETF池、今日排名、风控状态、每日交易报告、回测结果、交易日志、盘中自动刷新和 UZI 项目分析。

v2.0 CLI 常用入口：

```powershell
python -m tech_etf_quant.cli signals --date 2026-05-31
python -m tech_etf_quant.cli schedule --date 2026-05-31
python -m tech_etf_quant.cli schedule --date 2026-05-31 --run-due
python -m tech_etf_quant.cli risk-state --sync
python -m tech_etf_quant.cli deploy-check
```

本地循环调度：

```powershell
python -m tech_etf_quant.cli schedule --loop
```

## 盘中自动刷新

默认自动拉取盘中实时行情：

```powershell
python -m tech_etf_quant.cli watch --date 2026-05-31 --time 10:35
```

立即刷新日线缓存和盘中实时行情：

```powershell
python -m tech_etf_quant.cli refresh-now --date 2026-05-31 --time 10:35
```

只刷新盘中实时行情：

```powershell
python -m tech_etf_quant.cli refresh-now --date 2026-05-31 --time 10:35 --skip-daily
```

系统会输出盘中观察建议，并写入：

- `data/snapshots/{date}_snapshot.csv`
- `data/snapshots/{date}_realtime_{time}.csv`
- `data/cache/realtime_etf_spot.csv`
- `logs/watch_log.csv`

手动 CSV 只作为兜底。兜底字段：

```text
date,time,symbol,price,pct_change,amount,volume,high,low,open,prev_close,note
```

当自动源和本地缓存都不可用时，可以把行情软件导出的快照放到：

```text
data/snapshots/input_snapshot.csv
```

然后强制使用手动兜底：

```powershell
python -m tech_etf_quant.cli watch --date 2026-05-31 --time 10:35 --source manual
```

## UZI 项目内分析

UZI-Skill 只作为当前项目的本地分析引擎接入，不安装到全局 Codex skills，不影响项目外对话。配置在：

```text
config/uzi.yaml
```

本地引擎目录为：

```text
vendor/UZI-Skill
```

该目录已加入 `.gitignore`，不会提交到 GitHub。分析任务和输出默认写入：

```text
reports/uzi/
```

准备项目内 UZI 引擎：

```powershell
python -m tech_etf_quant.cli uzi --target 512480 --command quick-scan --ensure
```

只生成本地任务文件：

```powershell
python -m tech_etf_quant.cli uzi --target 512480 --command quick-scan
```

直接运行 UZI 自带 `run.py`：

```powershell
python -m tech_etf_quant.cli uzi --target 512480 --command quick-scan --run
```

可选命令包括 `analyze-stock`、`quick-scan`、`scan-trap`、`dcf`、`comps`、`lbo`、`initiate`、`ic-memo`、`investor-panel`、`trap-detector`。所有输出仍然遵守本项目声明：个人学习用途，不作为投资参考。

## 常见错误处理

- AKShare 日线下载失败：查看 `logs/error_log.csv`；系统会使用本地样例数据兜底。
- AKShare 盘中实时行情失败：系统先读取 `data/cache/realtime_etf_spot.csv`；缓存也没有时才使用手动 CSV。
- 指定日期没有交易日数据：系统会使用该日期之前最近一个可用交易日参与评分。
- 买入数量不足 100 份：撮合器会拒绝交易。
- 现金不足或触及 1000 元现金保留线：撮合器会拒绝或缩小交易。
- 账户权益低于 7360 元：进入 `HARD_DEFENSE`，停止主仓，只允许测试仓。

## 测试

```powershell
pytest
```

测试覆盖指标计算、评分排序、风控触发、仓位约束和回测输出。
