# 市场扫描策略参考

本项目的 `scanner_enhanced.py` 内置 8 种扫描预设，均通过 IBKR Scanner API 实现。

## 可用预设

| 预设名称 | scanCode | 说明 | 适用场景 |
|---------|----------|------|---------|
| 涨幅榜 | `TOP_PERC_GAIN` | 今日涨幅最大的股票 | 捕捉强势股、事件驱动 |
| 跌幅榜 | `TOP_PERC_LOSE` | 今日跌幅最大的股票 | 寻找超跌反弹机会 |
| 最活跃 | `MOST_ACTIVE` | 成交量最大的股票 | 关注市场焦点 |
| 成交异动 | `HOT_BY_VOLUME` | 成交量异动最大的股票 | 发现异常放量标的 |
| 52周新高 | `HIGH_VS_52W_HL` | 接近或突破 52 周新高 | 趋势突破策略 |
| 高股息 | `HIGH_DIVIDEND_YIELD_IB` | 股息收益率最高 | 收息策略、价值投资 |
| 低市盈率 | `LOW_PE_RATIO` | P/E 最低 | 价值投资筛选 |
| 高市值涨幅 | `TOP_PERC_GAIN` + 市值 > 100亿 | 大盘股涨幅榜 | 机构级标的筛选 |

## 通过 CLI 使用

```bash
# 列出所有预设
./ibkr scanner list

# 运行扫描（默认 top 10）
./ibkr scanner 涨幅榜
./ibkr scanner 跌幅榜 20
./ibkr scanner 52周新高 15
```

## 默认过滤条件

所有扫描预设默认附带以下过滤条件：
- `marketCapAbove = 100,000,000`（市值 > 1亿美元，排除微盘股）

"高市值涨幅" 额外要求 `marketCapAbove = 10,000,000,000`（市值 > 100亿）。

## IBKR 支持的其他 scanCode

以下 scanCode 可直接用于 `ibkr_readonly.py` 的 `run_scanner()` 方法：

| scanCode | 说明 |
|----------|------|
| `TOP_PERC_GAIN` | 涨幅最大 |
| `TOP_PERC_LOSE` | 跌幅最大 |
| `MOST_ACTIVE` | 成交量最大 |
| `HOT_BY_VOLUME` | 成交量异动 |
| `HIGH_VS_52W_HL` | 52周新高 |
| `LOW_VS_52W_HL` | 52周新低 |
| `HIGH_DIVIDEND_YIELD_IB` | 高股息 |
| `LOW_PE_RATIO` | 低市盈率 |
| `HIGH_PE_RATIO` | 高市盈率 |
| `TOP_OPEN_PERC_GAIN` | 开盘涨幅最大 |
| `TOP_OPEN_PERC_LOSE` | 开盘跌幅最大 |
| `HOT_BY_OPT_VOLUME` | 期权成交量异动 |
| `HIGH_OPT_IMP_VOLAT` | 高隐含波动率 |
| `LOW_OPT_IMP_VOLAT` | 低隐含波动率 |
| `TOP_TRADE_COUNT` | 成交笔数最多 |
| `TOP_TRADE_RATE` | 交易频率最高 |
| `HIGH_VS_13W_HL` | 13周新高 |
| `LOW_VS_13W_HL` | 13周新低 |
| `HIGH_VS_26W_HL` | 26周新高 |
| `LOW_VS_26W_HL` | 26周新低 |

> 完整列表可通过 `ib.reqScannerParameters()` 获取。
