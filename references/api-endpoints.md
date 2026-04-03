# ib_async API 参考（只读操作）

> 此文档仅包含本项目使用的只读 API。下单/修改/取消订单的 API 被刻意排除。

## 连接管理

```python
from ib_async import *

ib = IB()
ib.connect(host='127.0.0.1', port=4001, clientId=1, readonly=True)
ib.disconnect()
ib.isConnected()  # -> bool

# 延迟行情（免费，无需订阅）
ib.reqMarketDataType(3)  # 3 = 延迟, 1 = 实时

# 断线重连
ib.disconnectedEvent += callback_function
```

## 账户数据

```python
# 账户列表
accounts = ib.managedAccounts()  # -> ['U1234567']

# 账户摘要
summary = ib.accountSummary()  # -> [AccountValue(tag, value, currency, account)]
# 常用 tag: TotalCashValue, NetLiquidation, BuyingPower, UnrealizedPnL

# 持仓 (含服务端计算的市值/盈亏，无需行情订阅)
portfolio = ib.portfolio()  # -> [PortfolioItem]
# PortfolioItem 字段: contract, position, marketPrice, marketValue, averageCost,
#                      unrealizedPNL, realizedPNL, account
```

## 合约查询

```python
# 股票
contract = Stock('AAPL', 'SMART', 'USD')
qualified = ib.qualifyContracts(contract)  # -> [Contract]

# 期权
contract = Option('AAPL', '20260320', 180, 'C', 'SMART')
qualified = ib.qualifyContracts(contract)
```

## 行情数据

```python
# 快照行情
tickers = ib.reqTickers(contract)  # -> [Ticker]
# Ticker 字段: last, bid, ask, volume, close, high, low

# 期权 Greeks (需要 genericTickList='106')
ticker = ib.reqMktData(contract, genericTickList='106', snapshot=False)
ib.sleep(2)  # 等待数据
# ticker.modelGreeks -> OptionComputation(delta, gamma, theta, vega, impliedVol, ...)
ib.cancelMktData(contract)
```

## 历史数据

```python
bars = ib.reqHistoricalData(
    contract,
    endDateTime='',           # '' = 当前时间
    durationStr='3 M',        # '1 D', '1 W', '1 M', '3 M', '6 M', '1 Y', '5 Y'
    barSizeSetting='1 day',   # '1 min', '5 mins', '1 hour', '1 day', '1 week', '1 month'
    whatToShow='TRADES',      # 'TRADES', 'MIDPOINT', 'BID', 'ASK'
    useRTH=True               # True = 仅正常交易时段
)
# bars -> [BarData(date, open, high, low, close, volume)]
```

## 基本面数据

```python
# 需要额外数据订阅，否则可能返回空
xml_data = ib.reqFundamentalData(contract, 'ReportSnapshot')
# 返回 XML 字符串，需要解析
# 常用 Ratio FieldName:
#   MKTCAP       - 市值
#   PEEXCLXOR    - P/E 市盈率
#   TTMEPSXCLX   - EPS
#   YIELD        - 股息收益率
#   NHIG / NLOW  - 52周最高/最低
```

## 市场扫描

```python
sub = ScannerSubscription(
    instrument='STK',
    locationCode='STK.US.MAJOR',
    scanCode='TOP_PERC_GAIN',     # 详见 references/scanner-types.md
    numberOfRows=10
)
tag_values = [TagValue('marketCapAbove', '100000000')]  # 过滤市值 > 1亿
results = ib.reqScannerData(sub, scannerSubscriptionFilterOptions=tag_values)
# results -> [ScanData(rank, contractDetails, distance, benchmark, projection)]
```

## 成交记录

```python
# 近期成交（通常仅当天/近 7 天）
fills = ib.fills()  # -> [Fill(contract, execution, commissionReport, time)]
# execution -> Execution(side, shares, avgPrice, time, ...)
# commissionReport -> CommissionReport(commission, realizedPNL, ...)

# 按条件过滤
filt = ExecutionFilter(clientId=1)
trades = ib.reqExecutions(filt)
```

## 明确排除的 API

以下 API **不**在本项目的使用范围内：

- `ib.placeOrder()` — 下单
- `ib.cancelOrder()` — 取消订单
- `ib.reqGlobalCancel()` — 全局取消
- 任何修改账户状态的操作
