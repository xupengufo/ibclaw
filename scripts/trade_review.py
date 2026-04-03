#!/usr/bin/env python3
"""
历史交易复盘模块
提供：近期成交记录、交易统计（胜率、盈亏比等）。
所有函数接收 IBKRReadOnlyClient 实例，纯只读操作。

⚠️ 注意：ib_async 的 executions()/fills() 通常仅返回当天或最近 7 天的数据。
更长时间的历史需要 IBKR Flex Query（不在当前范围内）。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict
from collections import defaultdict


# ─── 数据类 ───────────────────────────────────────────────────

@dataclass
class TradeRecord:
    """单笔成交记录"""
    symbol: str
    side: str               # BOT (买入) / SLD (卖出)
    quantity: float
    avg_price: float
    time: str               # 成交时间
    commission: float
    realized_pnl: float     # 已实现盈亏
    sec_type: str            # STK, OPT, etc.
    exchange: str


@dataclass
class TradeStatistics:
    """交易统计"""
    total_trades: int
    total_symbols: int
    buy_trades: int
    sell_trades: int
    # 按 symbol 分组的统计
    winning_symbols: int
    losing_symbols: int
    win_rate_pct: float
    # 盈亏
    total_realized_pnl: float
    total_commission: float
    net_pnl: float
    avg_profit_per_win: float
    avg_loss_per_loss: float
    profit_factor: float     # 总盈利 / 总亏损
    largest_win: float
    largest_loss: float
    # 交易频率
    avg_trades_per_day: float
    trading_days: int


# ─── 分析函数 ─────────────────────────────────────────────────

def get_trade_history(client) -> List[TradeRecord]:
    """
    获取近期成交记录
    通过 ib.fills() 获取，通常仅当天/近 7 天数据
    """
    fills = client.get_fills()
    if not fills:
        return []

    records = []
    for fill in fills:
        execution = fill.execution
        contract = fill.contract
        commission_report = fill.commissionReport

        commission = 0.0
        realized_pnl = 0.0
        if commission_report:
            commission = commission_report.commission or 0.0
            realized_pnl = commission_report.realizedPNL or 0.0
            # 过滤无效的超大数字 (IB 用 1.7976931348623157e+308 表示 N/A)
            if realized_pnl > 1e300:
                realized_pnl = 0.0
            if commission > 1e300:
                commission = 0.0

        records.append(TradeRecord(
            symbol=contract.localSymbol or contract.symbol,
            side=execution.side,
            quantity=execution.shares,
            avg_price=execution.avgPrice,
            time=execution.time.strftime("%Y-%m-%d %H:%M:%S") if hasattr(execution.time, 'strftime') else str(execution.time),
            commission=round(commission, 4),
            realized_pnl=round(realized_pnl, 2),
            sec_type=contract.secType or "STK",
            exchange=execution.exchange
        ))

    # 按时间降序
    records.sort(key=lambda x: x.time, reverse=True)
    return records


def get_trade_statistics(client) -> Optional[TradeStatistics]:
    """
    统计交易数据：胜率、盈亏比等
    基于 fills 数据分析
    """
    records = get_trade_history(client)
    if not records:
        return None

    total = len(records)
    buy_trades = sum(1 for r in records if r.side == "BOT")
    sell_trades = sum(1 for r in records if r.side == "SLD")

    # 按 symbol 分组统计盈亏
    symbol_pnl: Dict[str, float] = defaultdict(float)
    for r in records:
        symbol_pnl[r.symbol] += r.realized_pnl

    total_symbols = len(symbol_pnl)
    winning = {k: v for k, v in symbol_pnl.items() if v > 0}
    losing = {k: v for k, v in symbol_pnl.items() if v < 0}

    winning_count = len(winning)
    losing_count = len(losing)
    total_with_pnl = winning_count + losing_count
    win_rate = (winning_count / total_with_pnl * 100) if total_with_pnl > 0 else 0

    # 盈亏统计
    total_pnl = sum(r.realized_pnl for r in records)
    total_commission = sum(r.commission for r in records)
    net_pnl = total_pnl - total_commission

    total_wins = sum(v for v in winning.values())
    total_losses = abs(sum(v for v in losing.values()))

    avg_profit = total_wins / winning_count if winning_count > 0 else 0
    avg_loss = total_losses / losing_count if losing_count > 0 else 0
    profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')

    largest_win = max(symbol_pnl.values()) if symbol_pnl else 0
    largest_loss = min(symbol_pnl.values()) if symbol_pnl else 0

    # 交易天数
    dates = set()
    for r in records:
        try:
            dates.add(r.time[:10])
        except (IndexError, TypeError):
            pass
    trading_days = max(1, len(dates))
    avg_per_day = total / trading_days

    return TradeStatistics(
        total_trades=total,
        total_symbols=total_symbols,
        buy_trades=buy_trades,
        sell_trades=sell_trades,
        winning_symbols=winning_count,
        losing_symbols=losing_count,
        win_rate_pct=round(win_rate, 1),
        total_realized_pnl=round(total_pnl, 2),
        total_commission=round(total_commission, 2),
        net_pnl=round(net_pnl, 2),
        avg_profit_per_win=round(avg_profit, 2),
        avg_loss_per_loss=round(avg_loss, 2),
        profit_factor=round(profit_factor, 2),
        largest_win=round(largest_win, 2),
        largest_loss=round(largest_loss, 2),
        avg_trades_per_day=round(avg_per_day, 1),
        trading_days=trading_days
    )


# ─── 格式化输出 ───────────────────────────────────────────────

def format_trade_history(records: List[TradeRecord], limit: int = 20) -> str:
    if not records:
        return "📋 近期成交记录: 无数据\n(ib_async fills 通常仅包含当天/近 7 天的成交)"

    lines = [
        "📋 近期成交记录",
        "=" * 70,
        f"{'时间':20s} {'方向':4s} {'标的':12s} {'数量':>6s} {'均价':>10s} {'佣金':>8s} {'已实现盈亏':>12s}"
    ]

    for r in records[:limit]:
        side_emoji = "🟢" if r.side == "BOT" else "🔴"
        side_text = "买入" if r.side == "BOT" else "卖出"
        pnl_text = f"${r.realized_pnl:>+,.2f}" if r.realized_pnl != 0 else "-"
        lines.append(
            f"{r.time:20s} {side_emoji}{side_text:2s} {r.symbol:12s} "
            f"{r.quantity:>6.0f} ${r.avg_price:>9,.2f} ${r.commission:>7,.2f} {pnl_text:>12s}"
        )

    if len(records) > limit:
        lines.append(f"\n  ...共 {len(records)} 笔，仅展示前 {limit} 笔")

    return "\n".join(lines)


def format_trade_statistics(stats: TradeStatistics) -> str:
    if not stats:
        return "📊 交易统计: 无数据"

    pf_text = f"{stats.profit_factor:.2f}" if stats.profit_factor != float('inf') else "∞"
    net_emoji = "📈" if stats.net_pnl >= 0 else "📉"

    return (
        f"📊 交易统计概览\n"
        f"{'=' * 50}\n"
        f"  交易天数: {stats.trading_days}天  |  总成交: {stats.total_trades}笔  |  日均: {stats.avg_trades_per_day:.1f}笔\n"
        f"  买入: {stats.buy_trades}笔  |  卖出: {stats.sell_trades}笔\n"
        f"  涉及标的: {stats.total_symbols}个\n"
        f"\n  {'─' * 40}\n"
        f"  🎯 胜率: {stats.win_rate_pct:.1f}% ({stats.winning_symbols}盈 / {stats.losing_symbols}亏)\n"
        f"  {net_emoji} 已实现盈亏: ${stats.total_realized_pnl:+,.2f}\n"
        f"  💸 总佣金: ${stats.total_commission:,.2f}\n"
        f"  💰 净盈亏: ${stats.net_pnl:+,.2f}\n"
        f"\n  {'─' * 40}\n"
        f"  平均盈利: ${stats.avg_profit_per_win:+,.2f}/笔\n"
        f"  平均亏损: ${stats.avg_loss_per_loss:,.2f}/笔\n"
        f"  盈亏比 (Profit Factor): {pf_text}\n"
        f"  最大单笔盈利: ${stats.largest_win:+,.2f}\n"
        f"  最大单笔亏损: ${stats.largest_loss:+,.2f}"
    )


def to_json_trades(results: dict) -> str:
    import json
    import dataclasses
    
    out = {}
    if "history" in results:
        out["history"] = [dataclasses.asdict(r) for r in results["history"]]
    if "statistics" in results:
        stats = results["statistics"]
        out["statistics"] = dataclasses.asdict(stats) if stats else None
        
    return json.dumps(out, ensure_ascii=False, indent=2, default=str)


# ─── 独立运行入口 ─────────────────────────────────────────────

def main():
    """独立运行：展示交易复盘功能"""
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ibkr_readonly import IBKRReadOnlyClient, util

    util.patchAsyncio()
    client = IBKRReadOnlyClient()

    if not client.connect():
        print("❌ 无法连接 IB Gateway")
        return

    print("🔍 交易复盘报告")
    print("=" * 60)
    print()

    # 1. 成交记录
    print("⏳ 正在获取近期成交记录...")
    history = get_trade_history(client)
    print(format_trade_history(history))
    print()

    # 2. 交易统计
    print("⏳ 正在统计交易数据...")
    stats = get_trade_statistics(client)
    print(format_trade_statistics(stats))

    client.disconnect()
    print("\n✅ 交易复盘完成")


if __name__ == "__main__":
    main()
