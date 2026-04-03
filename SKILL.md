---
name: ibkr-readonly
description: >
  IBKR 投资研究与只读查询（完全无交易功能）。通过 IB Gateway 连接用户的 IBKR 账户，
  提供持仓查看、余额查询、实时行情、深度基本面分析、技术分析（SMA/RSI/MACD/布林带/支撑阻力）、
  投资组合分析与风险评估、期权 Greeks 分析、交易复盘、市场扫描、自选股管理和数据导出。
  当用户提到 IBKR、盈透、Interactive Brokers、持仓、余额、净值、行情、股价、
  基本面、财报、技术分析、均线、RSI、MACD、支撑阻力、组合分析、风险分析、
  Beta、期权、Greeks、交易记录、胜率、涨跌榜、扫描、自选股、Watchlist、
  导出报告、投资建议，或任何涉及投资数据查询和股票研究的请求时，都应使用此 Skill。
  即使用户没有明确说"IBKR"，只要意图与投资分析、持仓查看、个股研究相关，也应优先考虑调用。
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
| ibkr_cli.py | 统一 CLI 入口，Agent 通过简洁命令调用所有模块 |
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
| ✅ 市场扫描 | 查询全市场涨幅榜、跌幅榜及异动榜（8种预设策略）|
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

作为用户的专属投资分析顾问，你需要理解以下三个核心原则，它们是让用户获得优质体验的关键：

**为什么要输出分析而非原始数字？** 用户使用这个 Skill 是为了获得投资洞察，而不是原始数据。当你只返回数字时，用户需要自己做解读工作——这正是你应该做的。每次返回数据时，请附上你的分析判断和逻辑推演。

**为什么要使用 JSON 格式？**
对于所有分析请求（技术面、基本面、持仓风险、组合概况、期权Greeks等），如果不带 `--json`，你获取的只是针对人类的“自带主观标点与进度的二手总结文本”。作为 AI，为了保持分析的客观性且方便你编写代码链式处理数据，你应当**总是附加 `--json` 选项**。以此获取纯净的嵌套字典，并根据你自身的常识框架**独立推演结论**。

**为什么风险提示不能省？** 投资决策的后果由用户承担。每份研报结尾加上"以上分析仅供参考，不构成投资建议"，既是对用户负责，也是法律保护。

### 第零步：环境就绪检查

在执行任何查询前，先确认运行环境是否就绪。这一步很重要，因为 IB Gateway 需要用户手动启动和登录。

```bash
cd ~/trading
./ibkr status
```

**如果 `~/trading` 目录不存在**，说明是首次使用，需要先部署：

```bash
bash {baseDir}/scripts/setup.sh ~/trading
```

然后引导用户完成以下步骤（这些步骤需要用户手动操作，你无法自动完成）：

1. **安装 IB Gateway**：从 https://www.interactivebrokers.com/en/trading/ibgateway-stable.php 下载
2. **首次登录**：启动 IB Gateway → 选择 "IB API" 模式 → 输入只读子账户凭据 → 手机确认 2FA
3. **配置 API**：Enable Socket Clients, 端口 4001, Trusted IP 127.0.0.1, 勾选 Auto Restart
4. **验证连接**：`cd ~/trading && ./ibkr status`

连接成功后，告知用户："IB Gateway 已连接，之后每周自动续期，只有 Mac 重启后才需要手动登录。"

**如果 `./ibkr status` 报端口不通**，说明 IB Gateway 未运行或未登录，提示用户启动并登录即可。更多排查信息见 `references/troubleshooting.md`。

### 第一步：意图识别与模块路由

根据用户意图，使用统一 CLI 入口调用对应模块。**所有命令在 `~/trading/` 目录下执行**。

| 用户意图 | CLI 命令 |
|---------|---------|
| 持仓、余额、净值 | `./ibkr quote` 或 `./run-readonly.sh` |
| 某只股票现在多少钱 | `./ibkr quote AAPL` |
| 分析XX股票、走势、技术面 | `./ibkr analyze AAPL --json` |
| 基本面、市值、PE、财报 | `./ibkr fundamentals AAPL --json` |
| 历史 K 线 | `./ibkr history AAPL --period '3 M'` |
| 组合配置、集中度、Beta | `./ibkr portfolio all --json` |
| 对比基准、Alpha | `./ibkr portfolio benchmark SPY '3 M'` |
| 盈亏归因 | `./ibkr portfolio attribution` |
| 最大回撤 | `./ibkr portfolio drawdown AAPL` |
| 相关性矩阵 | `./ibkr portfolio correlation` |
| 期权、Greeks、到期 | `./ibkr options all --json` |
| 交易记录、胜率 | `./ibkr trades all` |
| 市场扫描（涨幅榜） | `./ibkr scanner --code TOP_PERC_GAIN --json` |
| 市场扫描（条件选股） | `./ibkr scanner --code LOW_PE_RATIO --price-below 50 --json` |
| Finviz 多维选股 | `./ibkr screen --sector Technology --pe "Under 20" --json` |
| 分析师评级、目标价 | `./ibkr ratings AAPL --json` |
| 内部人交易（高管买卖） | `./ibkr insider AAPL --json` 或 `./ibkr insider market` |
| 同行公司对比 | `./ibkr peers AAPL --quote --json` |
| 自选股、Watchlist | `./ibkr watchlist list` |
| 添加自选股 | `./ibkr watchlist add AAPL --buy 170 --sell 220` |
| 导出报告/CSV | `./ibkr export all` 或 `./run-report.sh` |
| 新闻、为什么涨跌 | `./ibkr news AAPL` (Yahoo+Finviz) / `./ibkr news market` |
| Finviz 交易信号 | `./ibkr screen --signal Oversold --size 10 --json` |

> 完整的 CLI 帮助：`./ibkr --help`

### 第二步：深度投研流程

#### 对于个股分析类请求（"分析 AAPL"、"NVDA 为什么涨"、"要不要买 TSLA"）

执行四步法，每一步都有其不可替代的作用：

1. **📊 数据锚定**（建立事实基础）
   ```bash
   ./ibkr fundamentals AAPL --json
   ./ibkr analyze AAPL --json
   ./ibkr news AAPL
   ```

2. **🔍 全网检索**（捕捉最新事件）— 联网搜索最新财报、竞品动态、行业变化。数据锚定提供"是什么"，全网检索解释"为什么"。不可联网时标注"外部检索不可用"。

3. **🧠 逻辑推演**（形成判断）— 综合基本面 + 技术指标裸数据（来自 JSON） + 事件驱动，分析深层因果逻辑。**不要复读主观分数，你要自己看着 RSI、MACD、布林带的值去判断这只股票是超买、超卖还是具备爆发潜力。**

4. **📄 研报输出** — 按以下结构呈现：

```
1. 📊 盘面与技术面速览
   - 技术评分: XX/100 (看多/看空)
   - 均线排列、RSI、MACD信号
   - 支撑位: $XX / 阻力位: $XX
2. **🏢 基本面与估值**
   - P/E、EPS、市值、行业地位
3. **🌪️ 核心事件驱动** (web search)
4. **🧠 竞品与护城河分析**
5. **💡 综合研判与投资视角**
   ⚠️ 以上分析仅供参考，不构成投资建议
```

#### 对于复合条件选股请求（"低市盈率科技股"、"市值>100亿的医疗股"、"技术面超卖的股票"）

IBKR API 本身不支持跨维度（如“既限制PE，又限制行业，又限制RSI”）的直接过滤。当你遇到这种复杂请求时，你必须作为“大脑”承担本地过滤的工作。执行**“粗筛 + 细筛”两步法**：

1. **🕸️ 第一步：API 粗筛（获取候选池）**
   利用 IBKR 强大的排名算法，带上 `--json` 获取原始数据。**必须使用 `--code` 指定英文 scanCode**（完整列表见 `references/scanner-types.md`），可搭配 `--price-above`, `--price-below`, `--cap-above`, `--cap-below`, `--vol-above` 过滤。
   ```bash
   # 例：获取市盈率极低的股票，限定市值 > 10000000 且 价格 < 50
   ./ibkr scanner --code LOW_PE_RATIO --cap-above 10000000 --price-below 50 --json
   ```

2. **🧠 第二步：AI 本地细筛（多维逻辑推演）**
   拿到 JSON 数组后，遍历这些股票（可以通过小批量一次查多个），调用 `./ibkr fundamentals SYMBOL --json` 或 `./ibkr analyze SYMBOL1 SYMBOL2 --json`，在你的内存上下文中剔除不符合用户“行业约束（如科技股）”或“技术面约束（如 RSI<30）”的股票。

3. **📄 输出推荐报告**
   向用户呈现你千锤百炼筛选出的 3-5 只股票，并解释你的筛选逻辑。

#### 对于组合分析类请求（"我的组合怎么样"、"风险分析"、"复盘"）

执行三步法，获取组合全貌：

1. **📦 组合基础数据**
   ```bash
   ./ibkr portfolio all --json
   ```
   这会一次性输出：资产配置、持仓集中度(HHI)、组合Beta、基准对比(vs SPY)、盈亏归因、最大回撤、相关性矩阵。

2. **📊 持仓技术面扫描**
   ```bash
   # 获取技术指标裸数据供你推理
   ./ibkr analyze SYMBOL1 SYMBOL2 SYMBOL3 --json
   ```
   或者如果持仓不多，可以逐个分析。

3. **📋 输出组合健康度报告** — 要点：
   ```
   1. 📊 组合概览 (净值、现金占比、持仓数)
   2. 📦 配置分析 (按类型/行业分布，是否均衡)
   3. ⚠️ 风险维度
      - 集中度: HHI 指数是否过高、最大单只占比
      - Beta: 组合整体对市场的敏感度
      - 相关性: 是否存在高度相关的持仓对
   4. 📈 绩效评估
      - vs SPY 的 Alpha
      - 各持仓盈亏贡献
      - 最大回撤
   5. 🎯 技术面强弱分布 (基于你的独立判断，评出最强与最弱持仓)
   6. 💡 改进建议
      ⚠️ 以上分析仅供参考，不构成投资建议
   ```

#### 对于简单查询（"AAPL 现在多少钱"、"我的持仓"、"扫描涨幅榜"）

直接调用对应 CLI 命令，格式化输出即可，无需完整研报流程。但如果查询的股票恰好是用户持仓，主动附上持仓盈亏信息会让回答更有价值。

### 第三步：失败降级规则

遇到异常时，清晰地告诉用户发生了什么、影响范围有多大、接下来怎么办。这比隐藏错误要好得多。

降级结构：
```
1. ✅ 已确认的数据 — 成功获取到的信息
2. ⚠️ 未获取到的数据 — 哪些缺失、为什么
3. 🔍 对结论的影响 — 缺失数据是否影响核心判断
4. 👉 下一步操作 — 用户可以做什么来解决
```

常见降级场景：
- **IB Gateway 未连接**：输出连接诊断（`./ibkr status`），引导用户启动 IB Gateway
- **外部搜索不可用**：输出本地数据分析，标注"外部信息覆盖不足，建议用户自行查看最新财经新闻"
- **某只股票数据缺失**：已有数据正常分析，缺失部分标注"未获取到"，不要用猜测或虚构数据填充

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
./ibkr status
```

## 使用方法

### 统一 CLI（推荐）

```bash
cd ~/trading
./ibkr quote AAPL              # 查行情
./ibkr analyze NVDA            # 技术分析
./ibkr fundamentals TSLA       # 基本面 (IBKR + Finviz)
./ibkr ratings AAPL            # 分析师评级 (Finviz)
./ibkr insider AAPL            # 内部人交易 (Finviz)
./ibkr peers AAPL --quote      # 同行公司 + 行情对比
./ibkr screen --sector Technology --pe "Under 20"  # 多维选股
./ibkr portfolio all           # 组合全分析
./ibkr scanner --code TOP_PERC_GAIN  # IBKR 市场扫描
./ibkr options calendar        # 期权到期日历
./ibkr trades all              # 交易复盘
./ibkr news AAPL               # 公司新闻 (Yahoo+Finviz)
./ibkr news market             # 全市场新闻 (Finviz)
./ibkr export report           # 综合报告
./ibkr --help                  # 查看所有命令
```

### 在 OpenClaw 中使用

直接在 Telegram 或命令行副驾驶环境中问（示例）：
- "我的 IBKR 持仓有哪些？"
- "帮我查一下持仓盈亏"

---

## 高级思维链路 (SOP Workflows)

为了让你（AI Agent）表现得更像一个成熟的交易员，我们内置了特定的标准研报流水线（Workflows）。**请在执行用户的宽泛请求时，严格遵循以下预设链路：**

*   **个股深度诊断 (`/SOP-stock-xray`)**: 
    当用户问“分析某只股票”、“现在能买某只股吗”时触发。要求你在后台静默查阅 *基本面+技术面+分析师评级+高管买卖* 四维数据后，再给出最终研报定调。
*   **短线异动海选 (`/SOP-short-term-hunter`)**: 
    当用户问“选几只短线机会”、“这周有什么标的”时触发。禁止凭借旧知识胡编乱造，要求你先跑市场扫雷 (`scanner`) 看异动热点，再调多维选股 (`screen`) 下钻出技术面/基本面良好的 1-2 只个股。
*   **市场温度盘点 (`/SOP-market-pulse`)**: 
    当用户问“今天大盘这主线在弄啥”时触发。切忌空谈宏观，要求你必须从 SPY/QQQ 真实技术指标，以及全市场的内部人套现/增持汇总 (`insider market`) 中找出实际支撑的论点。
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

运行 `./ibkr status` 检查连接状态。更多排查信息见 `references/troubleshooting.md`。

| 问题 | 解决方案 |
|------|----------|
| 连接失败 | 检查 IB Gateway 是否启动并登录 |
| 端口不通 | 检查 API Settings 中端口是否为 4001 |
| 认证过期 | IB Gateway Auto Restart 会自动处理 |
| 进程不在 | Mac 重启后需要手动启动 IB Gateway |

## 安全说明

此技能设计为**完全只读**：
- 源代码中不包含任何下单 API 调用
- `IBKRReadOnlyClient` 连接时使用 `readonly=True` 参数
- 只读子账户本身没有交易权限
- 即使有人要求下单，技能也无法执行
