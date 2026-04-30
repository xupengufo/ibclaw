#!/usr/bin/env python3
"""
持仓日报生成器
聚合：持仓变动、技术面信号变化、财报事件、风险指标变动，生成每日投资简报。
所有函数接收 IBKRReadOnlyClient 实例，纯只读操作。
"""

import json
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict


# ─── 数据类 ───────────────────────────────────────────────────

@dataclass
class PositionBrief:
    """单只持仓简报"""
    symbol: str
    quantity: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    day_change_pct: float     # 当日涨跌幅
    tech_score: int           # 技术评分
    tech_signal: str          # 技术信号
    rsi: float
    alert: str                # 预警信息 (如有)


@dataclass
class DailyReport:
    """每日投资简报"""
    report_date: str
    report_time: str
    # 组合概况
    total_nav: float
    total_invested: float
    cash_value: float
    cash_pct: float
    total_pnl: float
    total_pnl_pct: float
    # 持仓明细
    positions: List[PositionBrief]
    # 统计
    gainers_count: int
    losers_count: int
    best_performer: str
    worst_performer: str
    # 预警
    alerts: List[str]
    # 市场环境
    spy_change_pct: float
    vix_level: float
    vix_signal: str
    # 建议
    action_items: List[str] = field(default_factory=list)


# ─── 核心函数 ─────────────────────────────────────────────────

def generate_daily_report(client) -> Optional[DailyReport]:
    """
    生成持仓日报
    """
    now = datetime.now()
    positions = client.get_positions()
    if not positions:
        return None

    stock_positions = [p for p in positions if p.sec_type == "STK"]

    # 组合概况
    total_invested = sum(abs(p.market_value) for p in positions)
    try:
        account_summary = client.get_account_summary()
        total_nav = float(account_summary.get("NetLiquidation", total_invested))
        cash_value = float(account_summary.get("TotalCashValue", 0))
    except Exception:
        total_nav = total_invested
        cash_value = 0

    cash_pct = (cash_value / total_nav * 100) if total_nav > 0 else 0
    total_pnl = sum(p.unrealized_pnl for p in positions if hasattr(p, "unrealized_pnl"))
    total_pnl_pct = (total_pnl / (total_invested - total_pnl) * 100) if total_invested > total_pnl else 0

    # 技术面批量分析
    from technical_analysis import analyze_symbols_batch
    symbols = [p.symbol for p in stock_positions]

    tech_batch = {}
    if symbols:
        try:
            tech_batch = analyze_symbols_batch(client, symbols, period="3 M", bar_size="1 day")
        except Exception:
            pass

    # 当日涨跌幅 (从 1D 历史数据推算)
    day_changes = {}
    for p in stock_positions:
        try:
            bars = client.get_historical_data(p.symbol, duration="5 D", bar_size="1 day")
            if bars and len(bars) >= 2:
                prev = bars[-2]["close"]
                curr = bars[-1]["close"]
                day_changes[p.symbol] = ((curr - prev) / prev * 100) if prev > 0 else 0
            elif bars:
                day_changes[p.symbol] = 0
        except Exception:
            day_changes[p.symbol] = 0

    # 构建持仓简报
    pos_briefs = []
    alerts = []
    for p in stock_positions:
        tech = tech_batch.get(p.symbol)
        tech_score = tech.score if tech else 0
        tech_signal = tech.overall_signal if tech else "N/A"
        rsi = tech.rsi.rsi_14 if tech else 50
        day_pct = day_changes.get(p.symbol, 0)
        pnl = getattr(p, "unrealized_pnl", 0)
        pnl_pct = 0
        if p.avg_cost and p.avg_cost > 0:
            pnl_pct = (p.market_value / p.quantity - p.avg_cost) / p.avg_cost * 100 if p.quantity != 0 else 0

        # 预警
        alert = ""
        if rsi >= 75:
            alert = "⚠️ RSI超买"
            alerts.append(f"{p.symbol}: RSI={rsi:.0f} 超买区域")
        elif rsi <= 25:
            alert = "💡 RSI超卖"
            alerts.append(f"{p.symbol}: RSI={rsi:.0f} 超卖区域")

        if pnl_pct <= -15:
            alert = "🔴 深度浮亏"
            alerts.append(f"{p.symbol}: 浮亏 {pnl_pct:.1f}%，需评估是否止损")
        elif pnl_pct >= 50:
            alert += " 📈 大幅盈利"
            alerts.append(f"{p.symbol}: 盈利 {pnl_pct:.1f}%，考虑部分止盈")

        if abs(day_pct) >= 5:
            alerts.append(f"{p.symbol}: 单日波动 {day_pct:+.1f}%，关注是否有异常事件")

        if tech_score <= -50:
            alerts.append(f"{p.symbol}: 技术面评分 {tech_score:+d}，多重看空信号")

        pos_briefs.append(PositionBrief(
            symbol=p.symbol,
            quantity=p.quantity,
            market_value=round(p.market_value, 2),
            unrealized_pnl=round(pnl, 2),
            unrealized_pnl_pct=round(pnl_pct, 2),
            day_change_pct=round(day_pct, 2),
            tech_score=tech_score,
            tech_signal=tech_signal,
            rsi=round(rsi, 1),
            alert=alert.strip()
        ))

    # 排序: 按当日涨跌排列
    pos_briefs.sort(key=lambda x: x.day_change_pct, reverse=True)

    gainers = [p for p in pos_briefs if p.day_change_pct > 0]
    losers = [p for p in pos_briefs if p.day_change_pct < 0]
    best = pos_briefs[0].symbol if pos_briefs else "N/A"
    worst = pos_briefs[-1].symbol if pos_briefs else "N/A"

    # 市场环境
    spy_change = 0
    vix_level = 0
    vix_signal = "N/A"
    try:
        spy_bars = client.get_historical_data("SPY", duration="5 D", bar_size="1 day")
        if spy_bars and len(spy_bars) >= 2:
            spy_change = (spy_bars[-1]["close"] - spy_bars[-2]["close"]) / spy_bars[-2]["close"] * 100
    except Exception:
        pass

    try:
        from vix_dashboard import analyze_vix
        vix_data = analyze_vix(client)
        if vix_data:
            vix_level = vix_data.current_vix
            vix_signal = vix_data.fear_greed_signal
    except Exception:
        pass

    # 行动建议
    action_items = []
    if len(alerts) == 0:
        action_items.append("✅ 组合状态健康，无需紧急操作")
    else:
        action_items.append(f"⚠️ 共有 {len(alerts)} 条预警需要关注")

    if cash_pct < 5:
        action_items.append("💰 现金比例过低，考虑适当减仓")
    if vix_level >= 25:
        action_items.append("😱 VIX 偏高，市场波动加剧，注意风险管理")

    # 财报预警
    try:
        from earnings_calendar import get_portfolio_earnings
        events = get_portfolio_earnings(client)
        upcoming = [e for e in events if e.get("days_until", 99) <= 7]
        if upcoming:
            for e in upcoming:
                action_items.append(f"📅 {e.get('symbol', '?')} 将于 {e.get('days_until', '?')} 天后发财报，注意波动风险")
    except Exception:
        pass

    return DailyReport(
        report_date=now.strftime("%Y-%m-%d"),
        report_time=now.strftime("%H:%M:%S"),
        total_nav=round(total_nav, 2),
        total_invested=round(total_invested, 2),
        cash_value=round(cash_value, 2),
        cash_pct=round(cash_pct, 2),
        total_pnl=round(total_pnl, 2),
        total_pnl_pct=round(total_pnl_pct, 2),
        positions=pos_briefs,
        gainers_count=len(gainers),
        losers_count=len(losers),
        best_performer=best,
        worst_performer=worst,
        alerts=alerts,
        spy_change_pct=round(spy_change, 2),
        vix_level=round(vix_level, 2),
        vix_signal=vix_signal,
        action_items=action_items
    )


# ─── 格式化输出 ───────────────────────────────────────────────

def format_daily_report(r: DailyReport) -> str:
    if not r:
        return "⚠️ 无法生成日报"

    pnl_emoji = "📈" if r.total_pnl >= 0 else "📉"
    spy_emoji = "📈" if r.spy_change_pct >= 0 else "📉"

    lines = [
        f"📋 投资日报  {r.report_date}  {r.report_time}",
        "=" * 60,
        "",
        f"  💼 组合概览:",
        f"     净值: ${r.total_nav:,.0f}  |  现金: ${r.cash_value:,.0f} ({r.cash_pct:.1f}%)",
        f"     {pnl_emoji} 浮盈: ${r.total_pnl:,.0f} ({r.total_pnl_pct:+.2f}%)",
        f"     上涨: {r.gainers_count}  |  下跌: {r.losers_count}  |  最强: {r.best_performer}  |  最弱: {r.worst_performer}",
        "",
        f"  🌍 市场环境:",
        f"     {spy_emoji} SPY: {r.spy_change_pct:+.2f}%  |  VIX: {r.vix_level:.1f}  {r.vix_signal}",
        "",
    ]

    # 持仓明细
    lines.append(f"  📊 持仓明细 ({len(r.positions)}):")
    lines.append(f"  {'标的':>6s} {'数量':>6s} {'市值':>10s} {'浮盈%':>7s} {'日涨幅':>7s} {'评分':>5s} {'RSI':>5s} 预警")
    lines.append("  " + "─" * 58)

    for p in r.positions:
        pnl_str = f"{p.unrealized_pnl_pct:+.1f}%"
        day_str = f"{p.day_change_pct:+.1f}%"
        lines.append(f"  {p.symbol:>6s} {p.quantity:>6.0f} ${p.market_value:>9,.0f} {pnl_str:>7s} {day_str:>7s} "
                    f"{p.tech_score:>+5d} {p.rsi:>5.0f} {p.alert}")

    if r.alerts:
        lines.append("")
        lines.append(f"  🚨 预警 ({len(r.alerts)}):")
        for a in r.alerts:
            lines.append(f"     • {a}")

    if r.action_items:
        lines.append("")
        lines.append("  📝 行动建议:")
        for item in r.action_items:
            lines.append(f"     {item}")

    return "\n".join(lines)


def to_json_daily_report(r: DailyReport) -> str:
    return json.dumps(dataclasses.asdict(r), ensure_ascii=False, indent=2)


# ─── 独立运行入口 ─────────────────────────────────────────────

def main():
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ibkr_readonly import IBKRReadOnlyClient

    client = IBKRReadOnlyClient()
    if not client.connect():
        print("❌ 无法连接 IB Gateway")
        return

    report = generate_daily_report(client)
    if report:
        print(format_daily_report(report))
    else:
        print("⚠️ 无持仓数据")

    client.disconnect()


if __name__ == "__main__":
    main()
