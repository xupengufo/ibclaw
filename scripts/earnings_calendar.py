#!/usr/bin/env python3
"""
财报日历模块
提供：个股及组合级财报日期查询、财报事件风险评估。
数据源：Finviz fundamentals（Earnings Date 字段）。
所有函数接收 IBKRReadOnlyClient 实例（仅用于获取持仓），纯只读操作。
"""

import json
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict


# ─── 数据类 ───────────────────────────────────────────────────

@dataclass
class EarningsEvent:
    """单只股票的财报事件"""
    symbol: str
    earnings_date: str          # 如 "Jan 30 AMC" (After Market Close)
    days_until: int             # 距今天数 (-1 表示日期无法解析)
    timing: str                 # "BMO" (Before Market Open) / "AMC" / "Unknown"
    urgency: str                # "🔴 本周" / "🟡 两周内" / "🟢 较远" / "❓ 未知"
    is_held: bool = False       # 是否为持仓股票
    held_quantity: float = 0.0
    market_value: float = 0.0


# ─── 核心函数 ─────────────────────────────────────────────────

def _parse_earnings_date(raw: str) -> tuple:
    """
    解析 Finviz 的 Earnings Date 字段。
    格式示例: "Jan 30 AMC", "Feb 05 BMO", "Apr 23", "-"
    返回 (days_until, timing)
    """
    if not raw or raw == "-":
        return -1, "Unknown"

    raw = raw.strip()
    timing = "Unknown"

    # 提取 AMC/BMO 标记
    if "AMC" in raw:
        timing = "AMC"
        raw = raw.replace("AMC", "").strip()
    elif "BMO" in raw:
        timing = "BMO"
        raw = raw.replace("BMO", "").strip()

    # 尝试解析日期
    now = datetime.now()
    for year in [now.year, now.year + 1]:
        for fmt in ["%b %d", "%m/%d/%Y", "%Y-%m-%d"]:
            try:
                parsed = datetime.strptime(raw, fmt)
                parsed = parsed.replace(year=year)
                # 如果解析出的日期已经过了 30 天以上，可能是明年的
                delta = (parsed - now).days
                if delta < -30 and year == now.year:
                    continue
                return delta, timing
            except ValueError:
                continue

    return -1, timing


def _classify_urgency(days: int) -> str:
    """根据距财报天数分类紧急程度"""
    if days < 0:
        return "❓ 未知"
    elif days <= 7:
        return "🔴 本周"
    elif days <= 14:
        return "🟡 两周内"
    else:
        return "🟢 较远"


def get_earnings_date(symbol: str) -> Optional[EarningsEvent]:
    """
    获取单只股票的财报日期，数据源为 Finviz。
    """
    try:
        from finviz_data import get_finviz_fundamentals
        data = get_finviz_fundamentals(symbol)
        if not data:
            return None

        raw_date = data.get("Earnings Date", data.get("Earnings", ""))
        if not raw_date or raw_date == "-":
            return EarningsEvent(
                symbol=symbol, earnings_date="N/A",
                days_until=-1, timing="Unknown", urgency="❓ 未知"
            )

        days, timing = _parse_earnings_date(raw_date)
        urgency = _classify_urgency(days)

        return EarningsEvent(
            symbol=symbol,
            earnings_date=raw_date.strip(),
            days_until=days,
            timing=timing,
            urgency=urgency
        )
    except Exception as e:
        print(f"⚠️ 获取 {symbol} 财报日期失败: {e}")
        return None


def get_portfolio_earnings(client) -> List[EarningsEvent]:
    """
    获取所有持仓的财报日历，按距财报日期排序。
    """
    positions = client.get_positions()
    stock_positions = [p for p in positions if p.sec_type == "STK"]

    if not stock_positions:
        return []

    events = []
    for p in stock_positions:
        event = get_earnings_date(p.symbol)
        if event:
            event.is_held = True
            event.held_quantity = p.quantity
            event.market_value = p.market_value
            events.append(event)

    # 按距财报天数排序（未知日期放最后）
    events.sort(key=lambda e: e.days_until if e.days_until >= 0 else 99999)
    return events


def get_earnings_risk_summary(events: List[EarningsEvent]) -> Dict:
    """
    汇总财报风险：多少持仓在近期有财报
    """
    within_week = [e for e in events if 0 <= e.days_until <= 7]
    within_two_weeks = [e for e in events if 0 <= e.days_until <= 14]
    total_at_risk_value = sum(abs(e.market_value) for e in within_two_weeks)

    return {
        "total_holdings": len(events),
        "earnings_within_7d": len(within_week),
        "earnings_within_14d": len(within_two_weeks),
        "at_risk_market_value": round(total_at_risk_value, 2),
        "risk_symbols_7d": [e.symbol for e in within_week],
        "risk_symbols_14d": [e.symbol for e in within_two_weeks],
    }


# ─── 格式化输出 ───────────────────────────────────────────────

def to_json_earnings(data) -> str:
    """统一 JSON 输出"""
    def default_encoder(obj):
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        return str(obj)
    return json.dumps(data, default=default_encoder, ensure_ascii=False, indent=2)


def format_earnings_single(event: EarningsEvent) -> str:
    """格式化单只股票的财报信息"""
    if not event:
        return "⚠️ 无法获取财报日期"

    timing_map = {"AMC": "盘后", "BMO": "盘前", "Unknown": "时间未定"}
    timing_text = timing_map.get(event.timing, event.timing)

    days_text = f"{event.days_until}天后" if event.days_until >= 0 else "日期未知"

    return (
        f"📅 {event.symbol} 财报日期\n"
        f"  日期: {event.earnings_date}\n"
        f"  距今: {days_text}  {event.urgency}\n"
        f"  时段: {timing_text}"
    )


def format_portfolio_earnings(events: List[EarningsEvent]) -> str:
    """格式化组合财报日历"""
    if not events:
        return "📅 持仓财报日历: 无股票持仓"

    risk = get_earnings_risk_summary(events)

    lines = [
        "📅 持仓财报日历",
        "=" * 60,
    ]

    if risk["earnings_within_7d"] > 0:
        lines.append(f"  🔴 本周有 {risk['earnings_within_7d']} 只持仓发布财报！")
    if risk["earnings_within_14d"] > 0:
        lines.append(f"  ⚠️ 两周内共 {risk['earnings_within_14d']} 只，涉及市值 ${risk['at_risk_market_value']:,.0f}")
    lines.append("")

    lines.append(f"{'标的':8s} {'财报日期':16s} {'距今':8s} {'时段':6s} {'紧急度':10s} {'持仓市值':>12s}")

    for e in events:
        timing_short = {"AMC": "盘后", "BMO": "盘前", "Unknown": "待定"}.get(e.timing, "?")
        days_text = f"{e.days_until}天" if e.days_until >= 0 else "未知"
        lines.append(
            f"  {e.symbol:8s} {e.earnings_date:16s} {days_text:8s} "
            f"{timing_short:6s} {e.urgency:10s} ${e.market_value:>11,.0f}"
        )

    return "\n".join(lines)


# ─── 独立运行入口 ─────────────────────────────────────────────

def main():
    """独立运行：测试财报日历"""
    print("🧪 财报日历模块测试")
    print("=" * 60)

    print("\n1. 测试个股财报日期...")
    for symbol in ["AAPL", "NVDA", "TSLA"]:
        event = get_earnings_date(symbol)
        if event:
            print(format_earnings_single(event))
            print()

    print("✅ 测试完成")


if __name__ == "__main__":
    main()
