#!/usr/bin/env python3
"""
增强扫描器 + Watchlist 管理模块
提供：更多扫描预设、扫描结果附带行情、Watchlist CRUD、批量行情查看。
所有函数接收 IBKRReadOnlyClient 实例，纯只读操作。
"""

import os
import json
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict

from ib_async import ScannerSubscription, TagValue


# ─── 配置 ─────────────────────────────────────────────────────

WATCHLIST_FILE = os.path.join(os.path.expanduser("~"), ".ibkr_watchlist.json")

# 扫描预设
SCAN_PRESETS: Dict[str, dict] = {
    "涨幅榜": {
        "scan_code": "TOP_PERC_GAIN",
        "description": "今日涨幅最大的股票"
    },
    "跌幅榜": {
        "scan_code": "TOP_PERC_LOSE",
        "description": "今日跌幅最大的股票"
    },
    "最活跃": {
        "scan_code": "MOST_ACTIVE",
        "description": "成交量最大的股票"
    },
    "成交异动": {
        "scan_code": "HOT_BY_VOLUME",
        "description": "成交量异动最大的股票"
    },
    "52周新高": {
        "scan_code": "HIGH_VS_52W_HL",
        "description": "接近或突破 52 周新高"
    },
    "高股息": {
        "scan_code": "HIGH_DIVIDEND_YIELD_IB",
        "description": "股息收益率最高的股票"
    },
    "低市盈率": {
        "scan_code": "LOW_PE_RATIO",
        "description": "市盈率最低的股票"
    },
    "高市值涨幅": {
        "scan_code": "TOP_PERC_GAIN",
        "description": "大盘股中涨幅最大的",
        "extra_filters": [TagValue("marketCapAbove", "10000000000")]  # > 100亿
    },

    # ─── 🧨 期权与波动率 ───
    "期权异动": {
        "scan_code": "HOT_BY_OPT_VOLUME",
        "description": "期权成交量异常飙升"
    },
    "最高波动率": {
        "scan_code": "HIGH_OPT_IMP_VOLAT",
        "description": "期权隐含波动率(IV)极高"
    },
    "最低波动率": {
        "scan_code": "LOW_OPT_IMP_VOLAT",
        "description": "期权隐含波动率(IV)极低"
    },
    "期权最活跃": {
        "scan_code": "OPT_VOLUME_MOST_ACTIVE",
        "description": "期权交易最活跃的标的"
    },
    
    # ─── ⚡ 盘面与高频特征 ───
    "成交笔数最多": {
        "scan_code": "TOP_TRADE_COUNT",
        "description": "当日总成交笔数最高"
    },
    "最高交易频率": {
        "scan_code": "TOP_TRADE_RATE",
        "description": "瞬时换手和交易频率极高"
    },
    "大幅高开": {
        "scan_code": "TOP_OPEN_PERC_GAIN",
        "description": "开盘跳空高开最大"
    },
    "大幅低开": {
        "scan_code": "TOP_OPEN_PERC_LOSE",
        "description": "开盘跳空低开最大"
    },
    "停牌熔断": {
        "scan_code": "HALTED",
        "description": "当日因剧烈波动被交易所停牌/熔断"
    },

    # ─── 📅 周期动量 ───
    "13周新高": {
        "scan_code": "HIGH_VS_13W_HL",
        "description": "接近或突破 13周（约一季度）新高"
    },
    "13周新低": {
        "scan_code": "LOW_VS_13W_HL",
        "description": "接近或跌破 13周（约一季度）新低"
    },
    "26周新高": {
        "scan_code": "HIGH_VS_26W_HL",
        "description": "接近或突破 26周（约半年）新高"
    },
    "26周新低": {
        "scan_code": "LOW_VS_26W_HL",
        "description": "接近或跌破 26周（约半年）新低"
    },
}


# ─── 数据类 ───────────────────────────────────────────────────

@dataclass
class ScanResult:
    """扫描结果"""
    rank: int
    symbol: str
    conid: int
    # 附带行情
    last_price: float = 0.0
    change_pct: float = 0.0
    volume: int = 0
    # 附加信息
    is_held: bool = False        # 是否已持有
    held_quantity: float = 0.0   # 持有数量


@dataclass
class WatchlistItem:
    """Watchlist 条目"""
    symbol: str
    target_buy: Optional[float] = None    # 目标买入价
    target_sell: Optional[float] = None   # 目标卖出价
    notes: str = ""
    added_date: str = ""
    # 行情（运行时填充）
    last_price: float = 0.0
    change_pct: float = 0.0
    is_held: bool = False


# ─── 扫描器 ───────────────────────────────────────────────────

def list_scan_presets() -> Dict[str, str]:
    """列出所有可用的扫描预设"""
    return {k: v["description"] for k, v in SCAN_PRESETS.items()}


def run_enhanced_scanner(
    client, 
    preset_name: Optional[str] = None, 
    scan_code: Optional[str] = None,
    size: int = 10,
    above_price: Optional[float] = None,
    below_price: Optional[float] = None,
    above_volume: Optional[int] = None,
    market_cap_above: Optional[float] = None,
    market_cap_below: Optional[float] = None
) -> List[ScanResult]:
    """
    增强扫描器：支持动态参数过滤 + 为每个结果附带实时行情 + 标注是否已持有
    """
    code = "TOP_PERC_GAIN"
    tag_values = []
    
    # 模式一：预设模式
    if preset_name:
        preset = SCAN_PRESETS.get(preset_name)
        if not preset:
            print(f"❌ 未知预设: {preset_name}")
            print(f"可用预设: {', '.join(SCAN_PRESETS.keys())}")
            return []
        code = preset["scan_code"]
        if "extra_filters" in preset:
            tag_values.extend(preset["extra_filters"])
    
    # 模式二：动态模式
    if scan_code:
        code = scan_code

    try:
        # 组装 ScannerSubscription 参数
        sub_kwargs = {
            'instrument': 'STK',
            'locationCode': 'STK.US.MAJOR',
            'scanCode': code,
            'numberOfRows': size
        }
        # 默认过滤：用户未指定时，排除微盘股和仙股（IBKR API 对无过滤的请求容易报错）
        if above_price is None and 'abovePrice' not in sub_kwargs:
            sub_kwargs['abovePrice'] = 1.0
        if market_cap_above is None and not any(
            tv.tag == 'marketCapAbove' for tv in tag_values
        ):
            sub_kwargs['marketCapAbove'] = 100000000  # 1亿美元

        if above_price is not None: sub_kwargs['abovePrice'] = above_price
        if below_price is not None: sub_kwargs['belowPrice'] = below_price
        if above_volume is not None: sub_kwargs['aboveVolume'] = above_volume
        if market_cap_above is not None: sub_kwargs['marketCapAbove'] = market_cap_above
        if market_cap_below is not None: sub_kwargs['marketCapBelow'] = market_cap_below

        sub = ScannerSubscription(**sub_kwargs)

        results = client.ib.reqScannerData(sub, scannerSubscriptionFilterOptions=tag_values)
    except Exception as e:
        print(f"❌ 扫描失败: {e}")
        return []

    # 获取当前持仓 set
    try:
        positions = client.get_positions()
        held_symbols = {p.symbol: p.quantity for p in positions}
    except Exception:
        held_symbols = {}

    # 批量获取行情（一次请求，替代逐个 get_quote）
    scan_symbols = [r.contractDetails.contract.symbol for r in results]
    try:
        quotes_map = client.get_quotes_batch(scan_symbols)
    except Exception:
        quotes_map = {}

    # 构建结果
    scan_results = []
    for r in results:
        symbol = r.contractDetails.contract.symbol
        conid = r.contractDetails.contract.conId

        quote = quotes_map.get(symbol)
        last_price = quote.last_price if quote else 0.0
        change_pct = quote.change_pct if quote else 0.0
        volume = quote.volume if quote else 0

        is_held = symbol in held_symbols
        held_qty = held_symbols.get(symbol, 0.0)

        scan_results.append(ScanResult(
            rank=r.rank + 1,
            symbol=symbol,
            conid=conid,
            last_price=last_price,
            change_pct=change_pct,
            volume=volume,
            is_held=is_held,
            held_quantity=held_qty
        ))

    return scan_results


# ─── Watchlist 管理 ───────────────────────────────────────────

def load_watchlist() -> dict:
    """加载 Watchlist"""
    if not os.path.exists(WATCHLIST_FILE):
        return {"items": [], "updated": ""}
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "items" not in data:
                data["items"] = []
            return data
    except (json.JSONDecodeError, IOError):
        return {"items": [], "updated": ""}


def save_watchlist(watchlist: dict):
    """保存 Watchlist"""
    watchlist["updated"] = datetime.now().isoformat()
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, indent=2, ensure_ascii=False)


def add_to_watchlist(symbol: str, target_buy: float = None, target_sell: float = None, notes: str = "") -> bool:
    """添加到 Watchlist"""
    wl = load_watchlist()

    # 检查是否已存在
    existing = [i for i in wl["items"] if i["symbol"].upper() == symbol.upper()]
    if existing:
        # 更新
        item = existing[0]
        if target_buy is not None:
            item["target_buy"] = target_buy
        if target_sell is not None:
            item["target_sell"] = target_sell
        if notes:
            item["notes"] = notes
        print(f"✅ 已更新 {symbol} 的 Watchlist 设置")
    else:
        wl["items"].append({
            "symbol": symbol.upper(),
            "target_buy": target_buy,
            "target_sell": target_sell,
            "notes": notes,
            "added_date": datetime.now().strftime("%Y-%m-%d")
        })
        print(f"✅ 已添加 {symbol} 到 Watchlist")

    save_watchlist(wl)
    return True


def remove_from_watchlist(symbol: str) -> bool:
    """从 Watchlist 移除"""
    wl = load_watchlist()
    original_len = len(wl["items"])
    wl["items"] = [i for i in wl["items"] if i["symbol"].upper() != symbol.upper()]

    if len(wl["items"]) < original_len:
        save_watchlist(wl)
        print(f"✅ 已从 Watchlist 移除 {symbol}")
        return True
    else:
        print(f"⚠️ {symbol} 不在 Watchlist 中")
        return False


def get_watchlist_quotes(client) -> List[WatchlistItem]:
    """获取 Watchlist 批量行情 + 标注是否已持有"""
    wl = load_watchlist()
    if not wl["items"]:
        return []

    # 获取当前持仓
    try:
        positions = client.get_positions()
        held_symbols = {p.symbol: True for p in positions}
    except Exception:
        held_symbols = {}

    # 批量获取行情
    all_symbols = [item["symbol"] for item in wl["items"]]
    try:
        quotes_map = client.get_quotes_batch(all_symbols)
    except Exception:
        quotes_map = {}

    results = []
    for item in wl["items"]:
        symbol = item["symbol"]
        wl_item = WatchlistItem(
            symbol=symbol,
            target_buy=item.get("target_buy"),
            target_sell=item.get("target_sell"),
            notes=item.get("notes", ""),
            added_date=item.get("added_date", ""),
            is_held=symbol in held_symbols
        )

        quote = quotes_map.get(symbol)
        if quote:
            wl_item.last_price = quote.last_price
            wl_item.change_pct = quote.change_pct

        results.append(wl_item)

    return results


# ─── 格式化输出 ───────────────────────────────────────────────

def to_json_scan_results(results: List[ScanResult]) -> str:
    """输出 JSON 格式的扫描结果供 AI 推理"""
    data = []
    for r in results:
        data.append(dataclasses.asdict(r))
    return json.dumps(data, ensure_ascii=False, indent=2)


def format_scan_results(results: List[ScanResult], preset_name: str) -> str:
    if not results:
        return f"📡 {preset_name}: 无结果"

    lines = [
        f"📡 市场扫描 — {preset_name}",
        "=" * 65,
        f"{'排名':>4s}  {'标的':8s}  {'当前价':>10s}  {'涨跌幅':>8s}  {'成交量':>12s}  {'持有':4s}"
    ]

    for r in results:
        held_mark = f"✅ {r.held_quantity:.0f}股" if r.is_held else ""
        change_emoji = "📈" if r.change_pct > 0 else "📉" if r.change_pct < 0 else "➖"
        vol_text = f"{r.volume:>12,}" if r.volume else "N/A"

        lines.append(
            f"  {r.rank:>2d}.  {r.symbol:8s}  ${r.last_price:>9,.2f}  "
            f"{change_emoji}{r.change_pct:>+6.2f}%  {vol_text}  {held_mark}"
        )

    return "\n".join(lines)


def format_watchlist(items: List[WatchlistItem]) -> str:
    if not items:
        return "📋 Watchlist: 空\n使用 add_to_watchlist('AAPL', target_buy=150, target_sell=200) 添加"

    lines = [
        "📋 我的 Watchlist",
        "=" * 70,
    ]

    for item in items:
        held_mark = "👜 已持有" if item.is_held else ""
        change_emoji = "📈" if item.change_pct > 0 else "📉" if item.change_pct < 0 else "➖"

        price_text = f"${item.last_price:,.2f}" if item.last_price else "N/A"
        change_text = f"{change_emoji}{item.change_pct:+.2f}%" if item.last_price else ""

        target_info = []
        if item.target_buy:
            distance = ((item.last_price - item.target_buy) / item.target_buy * 100) if item.last_price and item.target_buy else 0
            target_info.append(f"买入目标: ${item.target_buy:.2f} (差{distance:+.1f}%)")
        if item.target_sell:
            distance = ((item.last_price - item.target_sell) / item.target_sell * 100) if item.last_price and item.target_sell else 0
            target_info.append(f"卖出目标: ${item.target_sell:.2f} (差{distance:+.1f}%)")

        lines.append(f"\n  📌 {item.symbol} {held_mark}")
        lines.append(f"     当前: {price_text} {change_text}")
        if target_info:
            for t in target_info:
                lines.append(f"     🎯 {t}")
        if item.notes:
            lines.append(f"     📝 {item.notes}")

    return "\n".join(lines)


# ─── 独立运行入口 ─────────────────────────────────────────────

def main():
    """独立运行：演示增强扫描器和 Watchlist"""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ibkr_readonly import IBKRReadOnlyClient, util

    util.patchAsyncio()
    client = IBKRReadOnlyClient()

    if not client.connect():
        print("❌ 无法连接 IB Gateway")
        return

    print("📡 增强扫描器 & Watchlist")
    print("=" * 60)

    # 1. 列出可用预设
    print("\n📋 可用扫描预设:")
    for name, desc in list_scan_presets().items():
        print(f"  • {name}: {desc}")

    # 2. 运行涨幅榜扫描
    print("\n⏳ 正在扫描涨幅榜...")
    results = run_enhanced_scanner(client, "涨幅榜", 10)
    print(format_scan_results(results, "涨幅榜"))

    # 3. 运行跌幅榜
    print("\n⏳ 正在扫描跌幅榜...")
    results = run_enhanced_scanner(client, "跌幅榜", 10)
    print(format_scan_results(results, "跌幅榜"))

    # 4. Watchlist
    print("\n⏳ 正在加载 Watchlist...")
    wl_items = get_watchlist_quotes(client)
    print(format_watchlist(wl_items))

    client.disconnect()
    print("\n✅ 扫描完成")


if __name__ == "__main__":
    main()
