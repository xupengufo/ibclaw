#!/usr/bin/env python3
"""
智能止盈止损建议器
基于 ATR 波动、支撑阻力、持仓盈亏状态，给出个性化的止盈止损价位建议。
所有函数接收 IBKRReadOnlyClient 实例，纯只读操作。
"""

import json
import dataclasses
from dataclasses import dataclass, field
from typing import Optional, List


# ─── 数据类 ───────────────────────────────────────────────────

@dataclass
class ExitLevel:
    """单个止损/止盈价位"""
    price: float
    label: str           # "ATR 2x止损" / "支撑位止损" / "目标价止盈" 等
    method: str          # "atr" / "support" / "trailing" / "target"
    distance_pct: float  # 距当前价的百分比 (负=止损, 正=止盈)
    rationale: str       # 设定原因


@dataclass
class ExitAdvice:
    """止盈止损综合建议"""
    symbol: str
    current_price: float
    # 持仓信息 (如果是持仓股)
    avg_cost: Optional[float]
    unrealized_pnl_pct: Optional[float]
    quantity: Optional[float]
    # 止损建议
    stop_losses: List[ExitLevel]
    # 止盈建议
    take_profits: List[ExitLevel]
    # 综合建议
    recommended_stop: Optional[ExitLevel]
    recommended_target: Optional[ExitLevel]
    risk_reward_ratio: Optional[float]
    observations: List[str] = field(default_factory=list)


# ─── 核心函数 ─────────────────────────────────────────────────

def calc_exit_levels(client, symbol: str) -> Optional[ExitAdvice]:
    """
    计算止盈止损建议
    综合 ATR、支撑阻力、持仓盈亏三个维度
    """
    from technical_analysis import calc_atr, calc_support_resistance, calc_moving_averages

    bars = client.get_historical_data(symbol, duration="6 M", bar_size="1 day")
    if not bars or len(bars) < 30:
        return None

    current = bars[-1]["close"]
    closes = [b["close"] for b in bars]

    # ── ATR 止损 ──
    atr_data = calc_atr(bars)
    atr = atr_data.atr_14

    stop_losses = []
    take_profits = []
    observations = []

    if atr > 0:
        # 保守止损: 2x ATR
        atr_stop_2x = current - 2 * atr
        stop_losses.append(ExitLevel(
            price=round(atr_stop_2x, 2),
            label="ATR 2x 保守止损",
            method="atr",
            distance_pct=round((atr_stop_2x - current) / current * 100, 2),
            rationale=f"基于 14 日 ATR({atr:.2f})的 2 倍距离，允许正常波动空间"
        ))

        # 激进止损: 1.5x ATR
        atr_stop_1_5x = current - 1.5 * atr
        stop_losses.append(ExitLevel(
            price=round(atr_stop_1_5x, 2),
            label="ATR 1.5x 激进止损",
            method="atr",
            distance_pct=round((atr_stop_1_5x - current) / current * 100, 2),
            rationale=f"ATR 1.5 倍，较紧的止损，适合短线交易"
        ))

        # 宽松止损: 3x ATR
        atr_stop_3x = current - 3 * atr
        stop_losses.append(ExitLevel(
            price=round(atr_stop_3x, 2),
            label="ATR 3x 宽松止损",
            method="atr",
            distance_pct=round((atr_stop_3x - current) / current * 100, 2),
            rationale=f"ATR 3 倍，宽松空间，适合趋势交易"
        ))

    # ── 支撑位止损 ──
    sr = calc_support_resistance(bars)
    for i, sup in enumerate(sr.support_levels[:3]):
        # 略低于支撑位
        stop_price = round(sup * 0.99, 2)
        stop_losses.append(ExitLevel(
            price=stop_price,
            label=f"支撑位 S{i+1} 下方",
            method="support",
            distance_pct=round((stop_price - current) / current * 100, 2),
            rationale=f"支撑位 ${sup:.2f} 下方 1%，跌破即确认破位"
        ))

    # ── 均线止损 ──
    ma = calc_moving_averages(closes)
    if ma.sma_20 and ma.sma_20 < current:
        stop_losses.append(ExitLevel(
            price=round(ma.sma_20, 2),
            label="20 日均线止损",
            method="support",
            distance_pct=round((ma.sma_20 - current) / current * 100, 2),
            rationale="跌破 20 日均线通常标志短期趋势转弱"
        ))
    if ma.sma_50 and ma.sma_50 < current:
        stop_losses.append(ExitLevel(
            price=round(ma.sma_50, 2),
            label="50 日均线止损",
            method="support",
            distance_pct=round((ma.sma_50 - current) / current * 100, 2),
            rationale="跌破 50 日均线通常标志中期趋势转弱"
        ))

    # ── 阻力位止盈 ──
    for i, res in enumerate(sr.resistance_levels[:3]):
        take_profits.append(ExitLevel(
            price=round(res, 2),
            label=f"阻力位 R{i+1}",
            method="target",
            distance_pct=round((res - current) / current * 100, 2),
            rationale=f"阻力位 ${res:.2f}，获利了结参考"
        ))

    # ── ATR 止盈 ──
    if atr > 0:
        for mult, label in [(3, "保守"), (5, "中等"), (8, "激进")]:
            target = current + mult * atr
            take_profits.append(ExitLevel(
                price=round(target, 2),
                label=f"ATR {mult}x {label}目标",
                method="atr",
                distance_pct=round((target - current) / current * 100, 2),
                rationale=f"基于 ATR 的 {mult} 倍上行空间"
            ))

    # ── 持仓信息 ──
    avg_cost = None
    pnl_pct = None
    qty = None

    positions = client.get_positions()
    held = [p for p in positions if p.symbol == symbol and p.sec_type == "STK"]
    if held:
        pos = held[0]
        avg_cost = pos.avg_cost
        qty = pos.quantity
        if avg_cost and avg_cost > 0:
            pnl_pct = (current - avg_cost) / avg_cost * 100

            if pnl_pct > 20:
                # 移动止盈: 锁住至少一半利润
                trailing_stop = avg_cost + (current - avg_cost) * 0.5
                stop_losses.insert(0, ExitLevel(
                    price=round(trailing_stop, 2),
                    label="移动止盈 (锁 50% 利润)",
                    method="trailing",
                    distance_pct=round((trailing_stop - current) / current * 100, 2),
                    rationale=f"已盈利 {pnl_pct:.1f}%，锁住至少一半利润"
                ))
                observations.append(f"📈 已盈利 {pnl_pct:.1f}%，建议设移动止盈保护利润")

            elif pnl_pct < -10:
                observations.append(f"📉 已浮亏 {pnl_pct:.1f}%，评估是否仍然持有的逻辑依据")

            # 保本止损
            if pnl_pct > 5:
                stop_losses.insert(0, ExitLevel(
                    price=round(avg_cost * 1.01, 2),
                    label="保本止损 (成本+1%)",
                    method="trailing",
                    distance_pct=round((avg_cost * 1.01 - current) / current * 100, 2),
                    rationale=f"成本价 ${avg_cost:.2f} 上方 1%，确保不亏损出场"
                ))

    # 排序
    stop_losses.sort(key=lambda x: x.price, reverse=True)  # 最近的止损排前
    take_profits.sort(key=lambda x: x.price)  # 最近的止盈排前

    # 推荐止损/止盈
    recommended_stop = stop_losses[0] if stop_losses else None
    recommended_target = take_profits[0] if take_profits else None

    # 盈亏比
    rr = None
    if recommended_stop and recommended_target:
        risk = current - recommended_stop.price
        reward = recommended_target.price - current
        if risk > 0:
            rr = round(reward / risk, 2)

    if rr:
        if rr >= 3:
            observations.append(f"✅ 盈亏比 {rr}:1，风险回报优秀")
        elif rr >= 2:
            observations.append(f"✅ 盈亏比 {rr}:1，可接受")
        elif rr >= 1:
            observations.append(f"⚠️ 盈亏比 {rr}:1，偏低，考虑等更好入场点")
        else:
            observations.append(f"🔴 盈亏比 {rr}:1，不利，不建议在当前价位建仓")

    return ExitAdvice(
        symbol=symbol,
        current_price=round(current, 2),
        avg_cost=round(avg_cost, 2) if avg_cost else None,
        unrealized_pnl_pct=round(pnl_pct, 2) if pnl_pct is not None else None,
        quantity=qty,
        stop_losses=stop_losses,
        take_profits=take_profits,
        recommended_stop=recommended_stop,
        recommended_target=recommended_target,
        risk_reward_ratio=rr,
        observations=observations
    )


# ─── 格式化输出 ───────────────────────────────────────────────

def format_exit_advice(advice: ExitAdvice) -> str:
    """格式化止盈止损建议"""
    if not advice:
        return "⚠️ 无法生成止盈止损建议"

    lines = [
        f"🎯 {advice.symbol} 止盈止损建议  |  当前价: ${advice.current_price:,.2f}",
        "=" * 60,
    ]

    if advice.avg_cost:
        pnl_emoji = "📈" if (advice.unrealized_pnl_pct or 0) >= 0 else "📉"
        lines.append(f"  {pnl_emoji} 持仓成本: ${advice.avg_cost:.2f}  "
                     f"浮盈: {advice.unrealized_pnl_pct:+.1f}%  "
                     f"数量: {advice.quantity:.0f}")
        lines.append("")

    # 推荐
    if advice.recommended_stop or advice.recommended_target:
        lines.append("  ⭐ 推荐方案:")
        if advice.recommended_stop:
            lines.append(f"     止损: ${advice.recommended_stop.price:.2f} "
                        f"({advice.recommended_stop.distance_pct:+.1f}%)  "
                        f"— {advice.recommended_stop.label}")
        if advice.recommended_target:
            lines.append(f"     止盈: ${advice.recommended_target.price:.2f} "
                        f"({advice.recommended_target.distance_pct:+.1f}%)  "
                        f"— {advice.recommended_target.label}")
        if advice.risk_reward_ratio:
            lines.append(f"     盈亏比: {advice.risk_reward_ratio}:1")
        lines.append("")

    # 止损方案
    lines.append("  🛑 止损参考价位:")
    for sl in advice.stop_losses[:5]:
        lines.append(f"     ${sl.price:>9.2f}  ({sl.distance_pct:+5.1f}%)  {sl.label}")
    lines.append("")

    # 止盈方案
    lines.append("  🎯 止盈参考价位:")
    for tp in advice.take_profits[:5]:
        lines.append(f"     ${tp.price:>9.2f}  ({tp.distance_pct:+5.1f}%)  {tp.label}")

    if advice.observations:
        lines.append("")
        lines.append("  💡 建议:")
        for obs in advice.observations:
            lines.append(f"     {obs}")

    return "\n".join(lines)


def to_json_exit(advice: ExitAdvice) -> str:
    """JSON 输出"""
    return json.dumps(dataclasses.asdict(advice), ensure_ascii=False, indent=2)


# ─── 独立运行入口 ─────────────────────────────────────────────

def main():
    """独立运行：测试止盈止损"""
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ibkr_readonly import IBKRReadOnlyClient

    client = IBKRReadOnlyClient()
    if not client.connect():
        print("❌ 无法连接 IB Gateway")
        return

    for symbol in ["AAPL", "NVDA"]:
        advice = calc_exit_levels(client, symbol)
        if advice:
            print(format_exit_advice(advice))
        else:
            print(f"⚠️ {symbol}: 数据不足")
        print()

    client.disconnect()


if __name__ == "__main__":
    main()
