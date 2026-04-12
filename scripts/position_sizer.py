#!/usr/bin/env python3
"""
仓位计算器模块
基于账户净值、ATR 止损距离和风险比例，计算建议仓位大小。
所有函数接收 IBKRReadOnlyClient 实例，纯只读操作。

核心公式:
  建议股数 = (账户净值 × 单笔风险比例) / (ATR × ATR倍数)
  止损价 = 当前价 - (ATR × ATR倍数)
"""

import json
import dataclasses
from dataclasses import dataclass
from typing import Optional


# ─── 数据类 ───────────────────────────────────────────────────

@dataclass
class PositionSizeResult:
    """仓位计算结果"""
    symbol: str
    current_price: float
    # 账户信息
    account_nav: float          # 账户净资产
    # 风险参数
    risk_pct: float             # 单笔风险比例 (e.g. 2.0 = 2%)
    risk_amount: float          # 单笔最大可亏金额
    atr_multiplier: float       # ATR 倍数 (止损距离)
    # ATR 数据
    atr_14: float               # 14日 ATR
    stop_distance: float        # 止损距离 = ATR × 倍数
    stop_price: float           # 建议止损价
    # 计算结果
    suggested_shares: int       # 建议股数
    position_value: float       # 建议仓位金额
    position_pct: float         # 占总资产比例
    # 判断
    sizing_grade: str           # "保守" / "适中" / "激进"
    warnings: list              # 风险警告


# ─── 核心计算 ─────────────────────────────────────────────────

def calc_position_size(
    client,
    symbol: str,
    risk_pct: float = 2.0,
    atr_multiplier: float = 2.0,
    period: str = "3 M"
) -> Optional[PositionSizeResult]:
    """
    计算建议仓位大小

    Args:
        client: IBKRReadOnlyClient 实例
        symbol: 股票代码
        risk_pct: 单笔最大亏损占账户比例 (%, 默认 2%)
        atr_multiplier: ATR 倍数作为止损距离 (默认 2x)
        period: 历史数据周期用于计算 ATR

    Returns:
        PositionSizeResult 或 None
    """
    from technical_analysis import calc_atr

    # 1. 获取账户净值
    balance = client.get_balance()
    nav = balance.get("NetLiquidation", {}).get("amount", 0)
    if not isinstance(nav, (int, float)) or nav <= 0:
        print("⚠️ 无法获取账户净资产")
        return None

    # 2. 获取历史数据并计算 ATR
    bars = client.get_historical_data(symbol, duration=period, bar_size="1 day")
    if not bars or len(bars) < 20:
        print(f"⚠️ {symbol}: 历史数据不足，无法计算 ATR")
        return None

    atr_data = calc_atr(bars)
    if atr_data.atr_14 <= 0:
        print(f"⚠️ {symbol}: ATR 计算结果为 0")
        return None

    current_price = bars[-1]["close"]
    atr = atr_data.atr_14

    # 3. 核心计算
    risk_amount = nav * (risk_pct / 100)
    stop_distance = atr * atr_multiplier
    stop_price = round(current_price - stop_distance, 2)

    if stop_distance <= 0:
        return None

    suggested_shares = int(risk_amount / stop_distance)
    position_value = round(suggested_shares * current_price, 2)
    position_pct = round(position_value / nav * 100, 2)

    # 4. 仓位分级判断
    warnings = []
    if position_pct > 25:
        sizing_grade = "🔴 激进"
        warnings.append(f"单只仓位占比 {position_pct:.1f}% 超过 25%，集中度风险偏高")
    elif position_pct > 15:
        sizing_grade = "🟡 适中"
    else:
        sizing_grade = "🟢 保守"

    if position_value > nav * 0.5:
        warnings.append("建议仓位超过总资产 50%，请考虑降低风险比例")

    if current_price > 500 and suggested_shares < 10:
        warnings.append(f"股价较高 (${current_price:,.0f})，最小调仓粒度较粗")

    # 检查已有持仓
    try:
        positions = client.get_positions()
        for p in positions:
            if p.symbol == symbol and p.sec_type == "STK":
                warnings.append(f"⚠️ 已持有 {p.symbol}: {p.quantity:.0f}股，市值 ${p.market_value:,.0f}")
                break
    except Exception:
        pass

    return PositionSizeResult(
        symbol=symbol,
        current_price=current_price,
        account_nav=round(nav, 2),
        risk_pct=risk_pct,
        risk_amount=round(risk_amount, 2),
        atr_multiplier=atr_multiplier,
        atr_14=round(atr, 4),
        stop_distance=round(stop_distance, 2),
        stop_price=stop_price,
        suggested_shares=suggested_shares,
        position_value=position_value,
        position_pct=position_pct,
        sizing_grade=sizing_grade,
        warnings=warnings
    )


# ─── 格式化输出 ───────────────────────────────────────────────

def to_json_sizer(result: PositionSizeResult) -> str:
    """JSON 输出"""
    return json.dumps(dataclasses.asdict(result), ensure_ascii=False, indent=2)


def format_position_size(result: PositionSizeResult) -> str:
    """格式化仓位建议"""
    if not result:
        return "⚠️ 无法计算仓位"

    lines = [
        f"🧮 {result.symbol} 仓位计算器",
        "=" * 55,
        "",
        f"  📊 当前价: ${result.current_price:,.2f}",
        f"  💰 账户净值: ${result.account_nav:,.0f}",
        "",
        f"  ─── 风险参数 ───",
        f"  单笔风险: {result.risk_pct:.1f}% = ${result.risk_amount:,.0f}",
        f"  ATR(14): ${result.atr_14:,.2f}  ×{result.atr_multiplier:.1f} = 止损距离 ${result.stop_distance:,.2f}",
        f"  建议止损: ${result.stop_price:,.2f}",
        "",
        f"  ─── 建议仓位 ───",
        f"  📦 建议股数: {result.suggested_shares} 股",
        f"  💵 仓位金额: ${result.position_value:,.0f}",
        f"  📐 占总资产: {result.position_pct:.1f}%  {result.sizing_grade}",
    ]

    if result.warnings:
        lines.append("")
        lines.append("  ─── 风险提示 ───")
        for w in result.warnings:
            lines.append(f"  ⚠️ {w}")

    return "\n".join(lines)


# ─── 独立运行入口 ─────────────────────────────────────────────

def main():
    """独立运行：测试仓位计算"""
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ibkr_readonly import IBKRReadOnlyClient

    client = IBKRReadOnlyClient()
    if not client.connect():
        print("❌ 无法连接 IB Gateway")
        return

    print("🧮 仓位计算器测试")
    print("=" * 60)

    result = calc_position_size(client, "AAPL", risk_pct=2.0, atr_multiplier=2.0)
    if result:
        print(format_position_size(result))
    else:
        print("❌ 计算失败")

    client.disconnect()
    print("\n✅ 测试完成")


if __name__ == "__main__":
    main()
