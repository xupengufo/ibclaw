#!/usr/bin/env python3
"""
IBKR Read-Only Client - ib_insync 版本
通过 IB Gateway (socket API) 查询持仓、余额、实时行情、基本面、历史K线等。
安全特性：此脚本不包含任何下单、修改订单、取消订单的功能。

依赖：ib_insync (pip install ib_insync)
连接：IB Gateway 端口 4001 (live) 或 4002 (paper)
"""

import os
import math
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict

from ib_insync import *


def load_local_env():
    """加载脚本同目录的 .env（仅填充未设置的环境变量）"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value


load_local_env()

# Configuration
IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", "4001"))
IB_CLIENT_ID = int(os.getenv("IB_CLIENT_ID", "1"))


@dataclass
class Position:
    symbol: str
    conid: int
    quantity: float
    avg_cost: float
    market_value: float
    unrealized_pnl: float
    pnl_percent: float


@dataclass
class Quote:
    conid: int
    symbol: str
    last_price: float
    bid: float
    ask: float
    volume: int
    change: float
    change_pct: float


@dataclass
class FundamentalData:
    conid: int
    symbol: str
    company_name: str
    industry: str
    category: str
    market_cap: str
    pe_ratio: str
    eps: str
    dividend_yield: str
    high_52w: str
    low_52w: str
    avg_volume: str


class IBKRReadOnlyClient:
    """
    IBKR 只读客户端 - ib_insync 版
    通过 IB Gateway socket API 直连，比 Client Portal HTTP 更稳定。
    ⚠️ 安全说明：此类不包含任何下单、修改、取消订单的方法。
    """

    def __init__(self, host: str = IB_HOST, port: int = IB_PORT, client_id: int = IB_CLIENT_ID):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()
        self._setup_reconnect()

    def _setup_reconnect(self):
        """设置断线自动重连"""
        def on_disconnect():
            print(f"[{datetime.now():%H:%M:%S}] ⚠️ IB Gateway 断线，5秒后重连...")
            time.sleep(5)
            try:
                self.ib.connect(self.host, self.port, clientId=self.client_id, readonly=True)
                self.ib.reqMarketDataType(3)
                print(f"[{datetime.now():%H:%M:%S}] ✅ 重连成功")
            except Exception as e:
                print(f"[{datetime.now():%H:%M:%S}] ❌ 重连失败: {e}")

        self.ib.disconnectedEvent += on_disconnect

    def connect(self) -> bool:
        """连接 IB Gateway"""
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id, readonly=True)
            # 使用延迟行情（免费），避免 "not subscribed" 错误
            self.ib.reqMarketDataType(3)
            return True
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return False

    def disconnect(self):
        """断开连接"""
        if self.ib.isConnected():
            # 移除重连 handler 避免断开后自动重连
            self.ib.disconnectedEvent.clear()
            self.ib.disconnect()

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.ib.isConnected()

    def get_accounts(self) -> List[str]:
        """获取账户列表"""
        return self.ib.managedAccounts()

    def get_balance(self) -> dict:
        """获取账户余额/总结"""
        summary = self.ib.accountSummary()
        result = {}
        for item in summary:
            try:
                result[item.tag] = {"amount": float(item.value), "currency": item.currency}
            except (ValueError, TypeError):
                result[item.tag] = {"amount": item.value, "currency": item.currency}
        return result

    def get_positions(self) -> List[Position]:
        """获取当前持仓（使用 portfolio() 获取服务端计算的市值和盈亏，无需行情订阅）"""
        portfolio_items = self.ib.portfolio()
        positions = []
        for p in portfolio_items:
            contract = p.contract
            quantity = p.position
            avg_cost = p.averageCost
            mkt_value = p.marketValue
            unrealized_pnl = p.unrealizedPNL

            cost_basis = avg_cost * quantity if quantity else 0
            pnl_pct = (unrealized_pnl / abs(cost_basis) * 100) if cost_basis else 0

            positions.append(Position(
                symbol=contract.localSymbol or contract.symbol,
                conid=contract.conId,
                quantity=quantity,
                avg_cost=avg_cost,
                market_value=mkt_value,
                unrealized_pnl=unrealized_pnl,
                pnl_percent=pnl_pct
            ))
        return positions

    def search_symbol(self, symbol: str) -> Optional[Contract]:
        """搜索股票代码，返回 qualified Contract"""
        contract = Stock(symbol, 'SMART', 'USD')
        try:
            qualified = self.ib.qualifyContracts(contract)
            if qualified:
                return qualified[0]
        except Exception:
            pass
        return None

    def get_quote(self, symbol: str) -> Optional[Quote]:
        """获取实时行情快照"""
        contract = self.search_symbol(symbol)
        if not contract:
            return None

        def safe(val, default=0):
            """处理 NaN 和 None"""
            import math
            if val is None or (isinstance(val, float) and math.isnan(val)):
                return default
            return val

        try:
            [ticker] = self.ib.reqTickers(contract)
            last = safe(ticker.last) or safe(ticker.close)
            bid = safe(ticker.bid)
            ask = safe(ticker.ask)
            volume = safe(ticker.volume)
            close = safe(ticker.close)
            change = (last - close) if last and close else 0
            change_pct = (change / close * 100) if close else 0

            return Quote(
                conid=contract.conId,
                symbol=symbol,
                last_price=last or 0,
                bid=bid,
                ask=ask,
                volume=int(volume),
                change=round(change, 2),
                change_pct=round(change_pct, 2)
            )
        except Exception as e:
            print(f"❌ 获取行情失败: {e}")
            return None

    def get_fundamentals(self, symbol: str) -> Optional[FundamentalData]:
        """获取个股基本面指标"""
        contract = self.search_symbol(symbol)
        if not contract:
            return None

        company_name = contract.description if hasattr(contract, 'description') else ""
        industry = ""
        category = ""
        market_cap = "N/A"
        pe_ratio = "N/A"
        eps = "N/A"
        dividend_yield = "N/A"
        high_52w = "N/A"
        low_52w = "N/A"
        avg_volume = "N/A"

        # 尝试获取 fundamental data XML
        try:
            xml_data = self.ib.reqFundamentalData(contract, 'ReportSnapshot')
            if xml_data:
                root = ET.fromstring(xml_data)
                # 解析公司信息
                co_info = root.find('.//CoIDs')
                if co_info is not None:
                    name_el = root.find('.//CoGeneralInfo/CoName')
                    if name_el is not None:
                        company_name = name_el.text

                # 解析行业
                ind_el = root.find('.//Industry')
                if ind_el is not None:
                    industry = ind_el.get('type', '')
                    category = ind_el.text or ''

                # 解析财务指标
                for ratio in root.findall('.//Ratio'):
                    field_name = ratio.get('FieldName', '')
                    value = ratio.text or 'N/A'
                    if field_name == 'MKTCAP':
                        market_cap = value
                    elif field_name == 'PEEXCLXOR':
                        pe_ratio = value
                    elif field_name == 'TTMEPSXCLX':
                        eps = value
                    elif field_name == 'YIELD':
                        dividend_yield = value
                    elif field_name == 'NHIG':
                        high_52w = value
                    elif field_name == 'NLOW':
                        low_52w = value
                    elif field_name == 'APTS10DAVG' or field_name == 'VOL10DAVG':
                        avg_volume = value
        except Exception:
            # fundamentalData 可能不可用（需要额外订阅）
            pass

        # 如果 fundamental data 不可用，用 ticker 数据补充
        try:
            [ticker] = self.ib.reqTickers(contract)
            if high_52w == "N/A" and hasattr(ticker, 'high') and ticker.high:
                high_52w = str(ticker.high)
            if low_52w == "N/A" and hasattr(ticker, 'low') and ticker.low:
                low_52w = str(ticker.low)
        except Exception:
            pass

        return FundamentalData(
            conid=contract.conId,
            symbol=symbol,
            company_name=company_name,
            industry=industry,
            category=category,
            market_cap=market_cap,
            pe_ratio=pe_ratio,
            eps=eps,
            dividend_yield=dividend_yield,
            high_52w=high_52w,
            low_52w=low_52w,
            avg_volume=avg_volume
        )

    def get_historical_data(self, symbol: str, duration: str = "3 M", bar_size: str = "1 day") -> List[dict]:
        """
        获取历史 K 线数据
        duration: "1 D", "1 W", "1 M", "3 M", "6 M", "1 Y", "5 Y"
        bar_size: "1 min", "5 mins", "1 hour", "1 day", "1 week", "1 month"
        """
        contract = self.search_symbol(symbol)
        if not contract:
            return []

        try:
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow='TRADES',
                useRTH=True
            )
            return [
                {
                    "date": str(bar.date),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume
                }
                for bar in bars
            ]
        except Exception as e:
            print(f"❌ 获取历史数据失败: {e}")
            return []

    def run_scanner(self, scan_type: str = "TOP_PERC_GAIN", size: int = 10) -> List[dict]:
        """
        全市场智能扫描
        scan_type: TOP_PERC_GAIN, TOP_PERC_LOSE, MOST_ACTIVE, HIGH_VS_13W_HL
        """
        try:
            sub = ScannerSubscription(
                instrument='STK',
                locationCode='STK.US.MAJOR',
                scanCode=scan_type,
                numberOfRows=size
            )
            # 过滤微盘股
            tag_values = [
                TagValue('marketCapAbove', '100000000')
            ]
            results = self.ib.reqScannerData(sub, scannerSubscriptionFilterOptions=tag_values)
            return [
                {
                    "rank": r.rank,
                    "symbol": r.contractDetails.contract.symbol,
                    "conid": r.contractDetails.contract.conId,
                    "distance": r.distance,
                    "benchmark": r.benchmark,
                    "projection": r.projection
                }
                for r in results
            ]
        except Exception as e:
            print(f"❌ 扫描失败: {e}")
            return []

    def get_company_news(self, symbol: str, limit: int = 5) -> List[dict]:
        """
        获取公司最新新闻 (Yahoo Finance RSS)
        IBKR News API 需要额外订阅，暂用免费源。
        """
        import requests
        try:
            url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                root = ET.fromstring(r.text)
                news = []
                for item in root.findall(".//item")[:limit]:
                    title = item.find("title").text if item.find("title") is not None else ""
                    pubDate = item.find("pubDate").text if item.find("pubDate") is not None else ""
                    link = item.find("link").text if item.find("link") is not None else ""
                    news.append({"title": title, "date": pubDate, "link": link})
                return news
        except Exception:
            pass
        return []


def format_currency(value: float) -> str:
    if value >= 0:
        return f"${value:,.2f}"
    else:
        return f"-${abs(value):,.2f}"


def format_pnl(value: float, pct: float) -> str:
    sign = "📈" if value >= 0 else "📉"
    color_value = f"+{format_currency(value)}" if value >= 0 else format_currency(value)
    return f"{sign} {color_value} ({pct:+.2f}%)"


def main():
    """主函数 - 展示账户信息"""
    print("🏦 IBKR 投研辅助与只读查询工具 (ib_insync)")
    print("=" * 50)
    print("⚠️  安全模式：仅查询，无法执行任何交易操作")
    print("=" * 50)
    print()

    client = IBKRReadOnlyClient()

    if not client.connect():
        print("❌ 无法连接 IB Gateway。请确保：")
        print("   1. IB Gateway 已启动并登录")
        print("   2. API Settings 中已启用 Socket Clients")
        print(f"   3. 端口 {IB_PORT} 正确 (live=4001, paper=4002)")
        return

    print(f"✅ 已连接 IB Gateway ({client.host}:{client.port})")

    # 账户信息
    accounts = client.get_accounts()
    if accounts:
        print(f"📊 账户: {', '.join(accounts)}")

    balance = client.get_balance()
    cash = balance.get("TotalCashValue", {}).get("amount", 0)
    net_liq = balance.get("NetLiquidation", {}).get("amount", 0)
    print(f"💵 现金余额: {format_currency(cash)}")
    print(f"💰 净资产: {format_currency(net_liq)}")
    print("-" * 50)

    # 持仓
    print("📈 当前持仓:")
    positions = client.get_positions()
    if not positions:
        print("   (无持仓)")
    else:
        for p in positions:
            pnl = format_pnl(p.unrealized_pnl, p.pnl_percent)
            print(f"   {p.symbol}: {p.quantity}股 @ {format_currency(p.avg_cost)} → 市值{format_currency(p.market_value)} {pnl}")
    print("-" * 50)

    # 行情测试
    print("🔍 测试获取 AAPL 行情...")
    quote = client.get_quote("AAPL")
    if quote:
        print(f"🍎 AAPL: ${quote.last_price:.2f} ({quote.change_pct:+.2f}%) | Bid: ${quote.bid:.2f} Ask: ${quote.ask:.2f}")
    else:
        print("❌ 获取行情失败")

    print("-" * 50)
    print("📰 测试获取 LMND 最新新闻...")
    news = client.get_company_news("LMND")
    if news:
        for idx, item in enumerate(news):
            print(f"  {idx+1}. [{item['date']}] {item['title']}")
    else:
        print("无最新新闻或获取失败。")

    client.disconnect()
    print("\n✅ 查询完成")


if __name__ == "__main__":
    util.patchAsyncio()
    main()
