# 市场扫描策略参考 (Dynamic Scanner API)

本文档为 AI Agent 调用 `./ibkr scanner` 时的参数组合指引。**统一使用 `--code` 指定英文 scanCode**，不要使用中文预设名（存在 shell 编码兼容性问题）。

## 1. 动态命令行接口

```bash
# 语法
./ibkr scanner --code <SCAN_CODE> [--size N] [--price-above X] [--price-below Y] [--cap-above Z] [--cap-below W] [--vol-above V] [--json]

# 示例：获取 20 只股价低于 $50 且市值大于 10亿 的最低 P/E 股票（机器可读格式）
./ibkr scanner --code LOW_PE_RATIO --price-below 50 --cap-above 1000000000 --size 20 --json
```

## 2. 核心排名指标 (`--code`)

这是 API 的必须条件。IBKR 基于此指标对全市场美股进行排序。不能同时使用两个 `--code`。

| scanCode (提取码) | 说明 | Agent 适用场景 |
|------------------|------|---------------|
| `TOP_PERC_GAIN` | 今日涨幅最大 | 捕捉强势股、事件驱动 |
| `TOP_PERC_LOSE` | 今日跌幅最大 | 寻找超跌反弹机会、避雷 |
| `MOST_ACTIVE` | 成交量最大 | 关注市场绝对焦点、流动性极好 |
| `HOT_BY_VOLUME` | 成交量异动倍数最大 | 发现机构异常建仓/出逃标的 |
| `HIGH_DIVIDEND_YIELD_IB` | 股息收益率最高 | 价值股、分红收息策略 |
| `LOW_PE_RATIO` | P/E 最低 | 深度价值投资筛选 |

**🧨 期权异动与波动率驱动**
| `HOT_BY_OPT_VOLUME` | 期权成交量异常飙升 | 游资/机构建仓、末日轮博弈预警 |
| `HIGH_OPT_IMP_VOLAT` | 最高隐含波动率(IV) | 卖方策略(Sell)、逼空(Gamma Squeeze)侯选 |
| `LOW_OPT_IMP_VOLAT` | 最低隐含波动率(IV) | 寻找长线横盘、可能将变盘突破的标的 |
| `OPT_VOLUME_MOST_ACTIVE` | 期权最活跃 | 期权流动性极好的核心大白马 |

**⚡ 微观盘面与高频交易特征**
| `TOP_TRADE_COUNT` | 成交笔数最多 | 散户交投极度狂热、单笔微小的筹码博弈 |
| `TOP_TRADE_RATE` | 最高交易频率 | 瞬时换手极快、多空血拼焦点 |
| `TOP_OPEN_PERC_GAIN` | 开盘跳空高开最大 | 寻找动量延续、缺口回补 (Gap Fill) |
| `TOP_OPEN_PERC_LOSE` | 开盘跳空低开最大 | 寻找恐慌抛售错杀标的 |
| `HALTED` | 停牌 / 熔断 | 当日发生剧烈波动被交易所熔断停牌 |

**📅 周期与动量跟踪**
| `HIGH_VS_52W_HL` | 接近或突破 52周(1年)新高 | 经典动量策略 (Momentum)、右侧交易 |
| `LOW_VS_52W_HL` | 接近或跌破 52周(1年)新低 | 寻找潜在底部 |
| `HIGH_VS_13W_HL` | 接近 13周(一季度)新高 | 跟着财报季节奏做中线波段 |
| `LOW_VS_13W_HL` | 接近 13周(一季度)新低 | 短期业绩不及预期导致超跌 |
| `HIGH_VS_26W_HL` | 接近 26周(半年)新高 | 中期走势强劲标的 |
| `LOW_VS_26W_HL` | 接近 26周(半年)新低 | 中期空头趋势深陷标的 |

> ⚠️ **统一使用 `--code` 英文参数**。中文预设名（如 `./ibkr scanner 涨幅榜`）在部分终端/shell 环境下存在编码兼容性问题，已不再推荐。完整 scanCode 列表可通过 API 的 `ib.reqScannerParameters()` 获取。

## 3. 数值过滤参数 (Dynamic Filters)

在确定了 `--code` 排名后，可以使用以下参数对候选池进行约束。**注意：所有的金额/市值单位均为纯数字（美元）。**

| 参数名 | 描述 | 使用建议 |
|--------|------|---------|
| `--price-above` | 股价下限 | 建议设为 `5` 排除仙股避险 |
| `--price-below` | 股价上限 | 用于搜寻低价股 |
| `--cap-above` | 市值下限 | 建议设为 `1000000000` (10亿) 排除微盘股，或 `10000000000` 寻找大白马 |
| `--cap-below` | 市值上限 | 用于寻找小盘股 (Small-cap) |
| `--vol-above` | 成交量下限 | 确保标的具有足够流动性 |
| `--size` | 输出数量上限 | 默认 10，最多获取前 N 只 |

## 4. 多维条件选股

IBKR API 本身不支持诸如"只看科技股"或者"只看 RSI超卖"的服务器端筛选。有两种方案：

### 方案 A：Finviz 多维选股（推荐）

直接使用 `./ibkr screen`，Finviz 服务端支持行业+估值+技术面+信号的任意组合过滤：

```bash
./ibkr screen --sector Technology --pe "Under 20" --signal Oversold --json
./ibkr screen --signal "Top Gainers" --size 10 --json
./ibkr screen list  # 查看所有可用信号和过滤维度
```

### 方案 B：IBKR 粗筛 + AI 细筛

当需要 IBKR 特有的排名算法（如成交异动、期权异动）时：
1. **API 粗筛**：使用 `./ibkr scanner --code` + `--cap / --price` 拿回基础列表（务必加上 `--json`）。
2. **AI 细筛**：遍历这些标的，调用 `./ibkr fundamentals` 或 `./ibkr analyze` 过滤。

## 5. IBKR Scanner vs Finviz Screener 选用策略

| 场景 | 推荐工具 | 原因 |
|------|---------|------|
| 涨幅/跌幅/成交量排名 | IBKR `scanner --code` | IBKR 实时排名算法 |
| 期权异动、波动率排名 | IBKR `scanner --code` | Finviz 无此数据 |
| 新高/新低（13周/26周/52周） | IBKR `scanner --code` | IBKR 精确计算 |
| 行业 + PE + RSI 组合 | Finviz `screen` | IBKR 不支持多维过滤 |
| 分析师升降级信号 | Finviz `screen --signal Upgrades` | IBKR 无此信号 |
| 内部人买入/卖出信号 | Finviz `screen --signal "Recent Insider Buying"` | IBKR 无此信号 |
| 技术形态（双顶/头肩...） | Finviz `screen --signal "Double Bottom"` | IBKR 无形态识别 |
