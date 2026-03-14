#!/usr/bin/env python3
"""
期权分析模块
提供：期权 Greeks 查询、到期日日历、组合级 Greeks 汇总。
所有函数接收 IBKRReadOnlyClient 实例，纯只读操作。
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Dict


# ─── 数据类 ───────────────────────────────────────────────────

@dataclass
class OptionGreeks:
    """单个期权的 Greeks"""
    symbol: str
    underlying: str
    strike: float
    right: str              # C or P
    expiry: str             # YYYYMMDD
    days_to_expiry: int
    delta: float
    gamma: float
    theta: float
    vega: float
    implied_vol: float      # 隐含波动率
    market_value: float
    quantity: float


@dataclass
class ExpirationEntry:
    """到期日日历条目"""
    symbol: str
    expiry_date: str        # YYYYMMDD
    days_left: int
    right: str              # C or P
    strike: float
    quantity: float
    market_value: float
    urgency: str            # "🔴 紧急" / "🟡 临近" / "🟢 充裕"


@dataclass
class PortfolioGreeksSummary:
    """组合级 Greeks 汇总"""
    total_delta: float
    total_gamma: float
    total_theta: float      # 每天时间价值损耗
    total_vega: float
    net_delta_exposure: float   # Delta 等值股票暴露
    option_count: int
    net_direction: str      # "偏多" / "偏空" / "中性"


# ─── 分析函数 ─────────────────────────────────────────────────

def _parse_expiry(expiry_str: str) -> Optional[datetime]:
    """解析 YYYYMMDD 格式的到期日"""
    if not expiry_str:
        return None
    try:
        return datetime.strptime(expiry_str[:8], "%Y%m%d")
    except (ValueError, IndexError):
        return None


def _calc_days_to_expiry(expiry_str: str) -> int:
    """计算距到期日天数"""
    exp_date = _parse_expiry(expiry_str)
    if not exp_date:
        return -1
    delta = exp_date - datetime.now()
    return max(0, delta.days)


def _safe_float(val, default=0.0):
    """安全转换浮点数，处理 NaN 和 None"""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return default
    return float(val)


def get_option_greeks(client, position) -> Optional[OptionGreeks]:
    """
    获取单个期权持仓的 Greeks
    position: ibkr_readonly.Position (sec_type == 'OPT')
    """
    if position.sec_type != "OPT":
        return None

    days = _calc_days_to_expiry(position.expiry)

    # 构造期权 Contract
    from ib_insync import Option
    try:
        contract = Option(
            symbol=position.symbol.split()[0] if ' ' in position.symbol else position.symbol,
            lastTradeDateOrContractMonth=position.expiry,
            strike=position.strike,
            right=position.right,
            exchange='SMART'
        )
        qualified = client.ib.qualifyContracts(contract)
        if not qualified:
            # 如果无法 qualify，返回基础信息
            return OptionGreeks(
                symbol=position.symbol,
                underlying=position.symbol.split()[0] if ' ' in position.symbol else position.symbol,
                strike=position.strike,
                right=position.right,
                expiry=position.expiry,
                days_to_expiry=days,
                delta=0, gamma=0, theta=0, vega=0, implied_vol=0,
                market_value=position.market_value,
                quantity=position.quantity
            )
        contract = qualified[0]
    except Exception:
        return OptionGreeks(
            symbol=position.symbol,
            underlying=position.symbol.split()[0] if ' ' in position.symbol else position.symbol,
            strike=position.strike,
            right=position.right,
            expiry=position.expiry,
            days_to_expiry=days,
            delta=0, gamma=0, theta=0, vega=0, implied_vol=0,
            market_value=position.market_value,
            quantity=position.quantity
        )

    # 通过 ticker 获取 Greeks
    ticker = client.get_option_ticker(contract)
    delta = gamma = theta = vega = iv = 0.0

    if ticker and ticker.modelGreeks:
        greeks = ticker.modelGreeks
        delta = _safe_float(greeks.delta)
        gamma = _safe_float(greeks.gamma)
        theta = _safe_float(greeks.theta)
        vega = _safe_float(greeks.vega)
        iv = _safe_float(greeks.impliedVol)

    return OptionGreeks(
        symbol=position.symbol,
        underlying=position.symbol.split()[0] if ' ' in position.symbol else position.symbol,
        strike=position.strike,
        right=position.right,
        expiry=position.expiry,
        days_to_expiry=days,
        delta=round(delta, 4),
        gamma=round(gamma, 4),
        theta=round(theta, 4),
        vega=round(vega, 4),
        implied_vol=round(iv, 4),
        market_value=position.market_value,
        quantity=position.quantity
    )


def get_expiration_calendar(client) -> List[ExpirationEntry]:
    """
    获取所有期权持仓的到期日日历，按到期日排序
    """
    positions = client.get_positions()
    option_positions = [p for p in positions if p.sec_type == "OPT"]

    if not option_positions:
        return []

    entries = []
    for p in option_positions:
        days = _calc_days_to_expiry(p.expiry)

        if days < 0:
            urgency = "❓ 未知"
        elif days <= 7:
            urgency = "🔴 紧急"
        elif days <= 30:
            urgency = "🟡 临近"
        else:
            urgency = "🟢 充裕"

        entries.append(ExpirationEntry(
            symbol=p.symbol,
            expiry_date=p.expiry,
            days_left=days,
            right=p.right,
            strike=p.strike,
            quantity=p.quantity,
            market_value=p.market_value,
            urgency=urgency
        ))

    entries.sort(key=lambda x: x.days_left if x.days_left >= 0 else 99999)
    return entries


def get_portfolio_greeks_summary(client) -> Optional[PortfolioGreeksSummary]:
    """
    汇总组合级期权 Greeks
    """
    positions = client.get_positions()
    option_positions = [p for p in positions if p.sec_type == "OPT"]

    if not option_positions:
        return None

    total_delta = 0.0
    total_gamma = 0.0
    total_theta = 0.0
    total_vega = 0.0
    count = 0

    for p in option_positions:
        greeks = get_option_greeks(client, p)
        if greeks:
            # 乘以持仓数量和合约乘数 (通常 100)
            multiplier = abs(p.quantity) * 100
            sign = 1 if p.quantity > 0 else -1

            total_delta += greeks.delta * p.quantity * 100
            total_gamma += greeks.gamma * multiplier * sign
            total_theta += greeks.theta * multiplier * sign
            total_vega += greeks.vega * multiplier * sign
            count += 1

    # 判断方向
    if abs(total_delta) < 10:
        direction = "🔲 中性"
    elif total_delta > 0:
        direction = "📈 偏多"
    else:
        direction = "📉 偏空"

    return PortfolioGreeksSummary(
        total_delta=round(total_delta, 2),
        total_gamma=round(total_gamma, 4),
        total_theta=round(total_theta, 2),
        total_vega=round(total_vega, 2),
        net_delta_exposure=round(total_delta, 2),
        option_count=count,
        net_direction=direction
    )


# ─── 格式化输出 ───────────────────────────────────────────────

def format_option_greeks(greeks: OptionGreeks) -> str:
    right_name = "看涨" if greeks.right == "C" else "看跌"
    return (
        f"  {greeks.symbol} ({right_name} ${greeks.strike:.0f})\n"
        f"    到期: {greeks.expiry} ({greeks.days_to_expiry}天)\n"
        f"    Δ={greeks.delta:+.4f}  Γ={greeks.gamma:.4f}  "
        f"Θ={greeks.theta:.4f}  ν={greeks.vega:.4f}  IV={greeks.implied_vol:.2%}"
    )


def format_expiration_calendar(entries: List[ExpirationEntry]) -> str:
    if not entries:
        return "📅 到期日日历: 无期权持仓"

    lines = ["📅 期权到期日日历", "=" * 60]
    current_date = ""
    for e in entries:
        if e.expiry_date != current_date:
            current_date = e.expiry_date
            lines.append(f"\n  📆 {e.expiry_date} ({e.days_left}天后) {e.urgency}")
        right_name = "C" if e.right == "C" else "P"
        lines.append(
            f"     {e.symbol:20s}  {right_name} ${e.strike:<8.0f}  "
            f"x{e.quantity:>4.0f}  市值: ${e.market_value:>10,.2f}"
        )

    return "\n".join(lines)


def format_greeks_summary(summary: PortfolioGreeksSummary) -> str:
    return (
        f"📊 组合期权 Greeks 汇总 ({summary.option_count} 个期权)\n"
        f"{'=' * 50}\n"
        f"  方向判断: {summary.net_direction}\n"
        f"  总 Delta:  {summary.total_delta:+.2f} (等值约 {abs(summary.total_delta):.0f} 股暴露)\n"
        f"  总 Gamma:  {summary.total_gamma:+.4f}\n"
        f"  总 Theta:  {summary.total_theta:+.2f}/天 (每天时间价值{'损耗' if summary.total_theta < 0 else '收益'}: ${abs(summary.total_theta):.2f})\n"
        f"  总 Vega:   {summary.total_vega:+.2f}"
    )


# ─── 独立运行入口 ─────────────────────────────────────────────

def main():
    """独立运行：展示期权分析功能"""
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ibkr_readonly import IBKRReadOnlyClient, util

    util.patchAsyncio()
    client = IBKRReadOnlyClient()

    if not client.connect():
        print("❌ 无法连接 IB Gateway")
        return

    print("📊 期权分析报告")
    print("=" * 60)

    # 1. 到期日日历
    print("\n⏳ 正在获取到期日日历...")
    calendar = get_expiration_calendar(client)
    print(format_expiration_calendar(calendar))

    # 2. 各期权 Greeks
    positions = client.get_positions()
    opt_positions = [p for p in positions if p.sec_type == "OPT"]
    if opt_positions:
        print("\n📊 期权 Greeks 明细:")
        print("=" * 60)
        for p in opt_positions:
            greeks = get_option_greeks(client, p)
            if greeks:
                print(format_option_greeks(greeks))
                print()

    # 3. 组合级汇总
    print("⏳ 正在计算组合 Greeks 汇总...")
    summary = get_portfolio_greeks_summary(client)
    if summary:
        print(format_greeks_summary(summary))
    else:
        print("ℹ️ 无期权持仓，跳过 Greeks 汇总")

    client.disconnect()
    print("\n✅ 期权分析完成")


if __name__ == "__main__":
    main()
