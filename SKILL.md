---
name: ibkr-readonly
description: IBKR 投资研究与只读查询（无交易功能）。用于投研分析、公司基本面调研、持仓/余额/行情查询。触发词：IBKR、分析公司、盈透、持仓、股价、行情、基本面、财报、投资建议、技术分析。
metadata: {"openclaw":{"requires":{"os":["darwin","linux"],"bins":["bash","python3"]}}}
---

# IBKR 只读查询技能

⚠️ **安全模式**：此技能只能查询数据，**无法执行任何交易操作**。

## 架构

通过 **IB Gateway** (桌面版) + **ib_insync** (socket API) 直连，替代了之前不稳定的 Client Portal Gateway HTTP 方案。

| 组件 | 说明 |
|------|------|
| IB Gateway | IBKR 官方桌面应用，常驻后台，支持 Auto Restart |
| ib_insync | Python socket API 客户端，内置断线重连 |
| keepalive.py | 健康检查脚本，断线时发 Telegram 通知 |

## 功能

| 功能 | 说明 |
|------|------|
| ✅ 查看持仓 | 显示所有股票持仓、成本、市值、盈亏 |
| ✅ 查看余额 | 显示现金余额、净资产 |
| ✅ 实时行情 | 查询任意股票的实时价格 |
| ✅ 深度基本面 | 查询公司市值、P/E市盈率、EPS、股息收益及行业分类 |
| ✅ 历史K线 | 获取过去 N 天/月/年的价格序列，用于趋势分析 |
| ✅ 技术分析 | SMA/EMA/RSI/MACD/布林带/支撑阻力/量能分析 + 综合评分(-100~+100) |
| ✅ 市场扫描 | 查询全市场涨幅榜、跌幅榜及异动榜（8种预设策略） |
| ✅ 组合分析 | 资产配置分布、持仓集中度、组合Beta、相关性矩阵 |
| ✅ 绩效追踪 | 基准对比(vs SPY)、盈亏归因、最大回撤分析 |
| ✅ 期权分析 | Greeks(Delta/Gamma/Theta/Vega)、到期日日历、组合级暴露 |
| ✅ 主动告警 | 价格异动、集中度超标、期权到期、目标价触达（Telegram推送） |
| ✅ 交易复盘 | 成交记录、胜率统计、盈亏比分析 |
| ✅ Watchlist | 自选股管理、目标买卖价、批量行情 |
| ✅ 数据导出 | 持仓CSV、资产配置CSV、综合投资报告 |
| ❌ 下单 | **不支持** |
| ❌ 修改订单 | **不支持** |
| ❌ 取消订单 | **不支持** |

## 🤖 AI 助理执业规范 (Agent Execution Protocol)

作为用户的专属量化与投资分析顾问，你必须遵循以下规范。

### 第一步：意图识别与模块路由

根据用户意图，调用对应的分析模块。**所有 Python 命令必须在 `~/trading/` 目录下，用 `source venv/bin/activate` 激活后执行**。若 `~/trading` 未部署，先执行 `bash {baseDir}/scripts/setup.sh ~/trading`。

| 用户意图关键词 | 调用模块 | 执行方式 |
|--------------|---------|---------|
| 持仓、余额、净值 | `ibkr_readonly` | `./run-readonly.sh` |
| 分析XX股票、走势、技术面、支撑阻力 | `technical_analysis` | `python -c "from technical_analysis import *; from ibkr_readonly import *; util.patchAsyncio(); c=IBKRReadOnlyClient(); c.connect(); print(format_technical_summary(analyze_symbol(c,'SYMBOL'))); c.disconnect()"` |
| 基本面、市值、PE、财报 | `ibkr_readonly` | 调用 `get_fundamentals('SYMBOL')` |
| 组合配置、集中度、Beta、相关性 | `portfolio_analytics` | `python -c "from portfolio_analytics import *; from ibkr_readonly import *; util.patchAsyncio(); c=IBKRReadOnlyClient(); c.connect(); ..."` |
| 对比基准、跑赢大盘、Alpha | `portfolio_analytics` | 调用 `get_benchmark_comparison(c)` |
| 盈亏归因、哪只贡献最大 | `portfolio_analytics` | 调用 `get_performance_attribution(c)` |
| 最大回撤 | `portfolio_analytics` | 调用 `get_max_drawdown(c)` |
| 期权、Greeks、到期 | `options_analytics` | `python -c "from options_analytics import *; ..."` |
| 交易记录、胜率、盈亏比 | `trade_review` | `python -c "from trade_review import *; ..."` |
| 涨跌榜、扫描、异动 | `scanner_enhanced` | `python -c "from scanner_enhanced import *; ..."` |
| 自选股、Watchlist、目标价 | `scanner_enhanced` | 调用 `add_to_watchlist()` / `get_watchlist_quotes()` |
| 导出报告、生成CSV | `export` | `./run-report.sh` |
| 新闻、为什么涨跌 | `ibkr_readonly` + web search | 调用 `get_company_news()` + 联网搜索 |

### 第二步：深度投研流程

#### 对于个股分析类请求（"分析 AAPL"、"NVDA 为什么涨"、"要不要买 TSLA"）

**必须执行四步法：**

1. **📊 数据锚定** — 调用 `get_fundamentals()` + `technical_analysis.analyze_symbol()` + `get_company_news()`
2. **🔍 全网检索** — 联网搜索最新事件、财报、竞品动态。不可联网时标注"外部检索不可用"
3. **🧠 逻辑推演** — 综合基本面 + 技术面 + 事件驱动，分析深层逻辑
4. **📄 研报输出** — 必须包含以下结构：

```
1. 📊 盘面与技术面速览
   - 技术评分: XX/100 (看多/看空)
   - 均线排列、RSI、MACD信号
   - 支撑位: $XX / 阻力位: $XX
2. 🏢 基本面与估值
   - P/E、EPS、市值、行业地位
3. 🌪️ 核心事件驱动 (web search)
4. 🧠 竞品与护城河分析
5. 💡 综合研判与投资视角
   ⚠️ 以上分析仅供参考，不构成投资建议
```

#### 对于组合分析类请求（"我的组合怎么样"、"风险分析"、"复盘"）

1. 调用 `portfolio_analytics` 获取配置/集中度/Beta/归因
2. 调用 `technical_analysis.analyze_portfolio()` 获取每只持仓的技术评分
3. 输出组合健康度报告（配置是否均衡、风险是否集中、技术面强弱分布）

#### 对于简单查询（"AAPL 现在多少钱"、"我的持仓"、"帮我扫描涨幅榜"）

直接调用对应模块，格式化输出即可，无需完整研报流程。

### 第三步：失败降级规则

- IB Gateway 未连接或脚本失败：明确故障原因 + "可执行下一步"
- 外部搜索不可用：输出本地数据分析，标注"外部信息覆盖不足"
- **禁止虚构数据**。拿不到的数据直接写"未获取到"
- 降级结构：`1. 已确认的数据` → `2. 未获取到的数据` → `3. 对结论的影响` → `4. 下一步操作`

### 始终遵守的原则

- **绝不返回枯燥数字**：必须有分析、有判断、有逻辑链
- **技术分析是标配**：任何涉及个股的请求，都应附带技术评分和关键指标
- **主动关联持仓**：分析的股票恰好是用户持仓时，主动展示盈亏
- **风险提示不可少**：研报结尾加"以上分析仅供参考，不构成投资建议"

## 前置条件

1. IBKR 账户（真实或模拟盘）
2. 手机安装 IBKR Key App（首次登录 IB Gateway 需要 2FA）
3. Debian / macOS 需要 Java 17+ 和 Python 3.9+
4. **IB Gateway** 桌面应用（从 IBKR 官网下载）

## 快速配置

### 1. 安装依赖

```bash
# Debian / macOS 一键安装运行环境
bash {baseDir}/scripts/setup.sh ~/trading
```

### 2. 安装 IB Gateway

从 IBKR 官网下载 **IB Gateway** (Stable channel)：
https://www.interactivebrokers.com/en/trading/ibgateway-stable.php

安装后启动，用你的只读子账户登录（需手机 2FA 确认）。

### 3. 配置 IB Gateway API Settings

在 IB Gateway 界面中：
- ✅ **Enable ActiveX and Socket Clients**
- ❌ **Read-Only API**（不要勾选，会阻止部分查询 API。安全性由账户层保障）
- 端口：**4001** (live)
- Trusted IPs：**127.0.0.1**
- ✅ **Auto Restart**（Settings → Lock and Exit → Auto restart，每周日自动重启）

### 4. 配置环境变量

`~/trading/.env`：
```bash
IB_HOST=127.0.0.1
IB_PORT=4001
IB_CLIENT_ID=1
```

### 5. 测试连接

```bash
cd ~/trading
./run-readonly.sh
```

## 使用方法

### 查看持仓和余额

```bash
cd ~/trading
./run-readonly.sh
```

### 在 OpenClaw 中使用

直接在 Telegram 问：
- "我的 IBKR 持仓有哪些？"
- "帮我查一下持仓盈亏"
- "帮我看看苹果 (AAPL) 最近的基本面，市值和市盈率怎么样？"
- "利用 IBKR 历史数据，分析一下 NVDA 最近 3 个月的走势"
- "帮我做一下 TSLA 的技术分析，支撑位和阻力位在哪？"
- "今天美股涨得最猛的 10 只股票是哪些？"
- "分析一下我的投资组合配置是否合理"
- "我的持仓集中度怎么样？有没有过于集中的风险？"
- "帮我对比下我的组合收益和 SPY 谁更好"
- "我有哪些期权快到期了？Greeks 是多少？"
- "帮我查查最近的交易胜率和盈亏比"
- "把 AAPL 加入我的自选股，目标买入价 170，卖出价 220"
- "帮我导出一份完整的投资分析报告"

## 健康检查

通过 keepalive.py 每 5 分钟检查 IB Gateway 状态，断线时发 Telegram 通知：

```bash
# Crontab
*/5 * * * * cd ~/trading && ./run-keepalive.sh >> ~/trading/keepalive.log 2>&1
```

IB Gateway 自带 Auto Restart，通常不需要手动干预。只有在以下情况才需要手动操作：
- IB Gateway 进程被杀
- Mac mini 重启后
- IBKR 维护期间

## 故障排查

| 问题 | 解决方案 |
|------|----------|
| 连接失败 | 检查 IB Gateway 是否启动并登录：看桌面是否有 IB Gateway 窗口 |
| 端口不通 | 检查 API Settings 中端口是否为 4001，是否勾选了 Socket Clients |
| 认证过期 | IB Gateway Auto Restart 会自动处理；如果失败，手动重启 IB Gateway 并登录 |
| 进程不在 | Mac 重启后需要手动启动 IB Gateway |

## 安全说明

此技能设计为**完全只读**：
- 源代码中不包含任何下单 API 调用
- `IBKRReadOnlyClient` 连接时使用 `readonly=True` 参数
- 只读子账户本身没有交易权限
- 即使有人要求下单，技能也无法执行
