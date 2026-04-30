#!/usr/bin/env python3
"""
风险预算计算器
基于当前组合状态（Beta、集中度、现金比例、波动率），评估剩余可承受风险额度。
所有函数接收 IBKRReadOnlyClient 实例，纯只读操作。
"""

import json
import math
import dataclasses
from dataclasses import dataclass, field
from typing import Optional, List, Dict


# ─── 数据类 ───────────────────────────────────────────────────

@dataclass
class RiskBudgetReport:
    """风险预算报告"""
    # 组合概况
    total_nav: float                # 总净值
    cash_value: float               # 现金余额
    cash_pct: float                 # 现金比例
    invested_value: float           # 已投资金额
    position_count: int             # 持仓数量
    # 风险指标
    portfolio_beta: float           # 组合 Beta
    portfolio_volatility_pct: float # 组合年化波动率(估算)
    hhi_index: float                # 集中度
    max_single_pct: float           # 最大单只占比
    # 风险预算
    max_total_risk_pct: float       # 最大总风险容忍度 (%)
    used_risk_pct: float            # 已使用风险额度 (%)
    remaining_risk_pct: float       # 剩余风险额度 (%)
    remaining_risk_value: float     # 剩余可承受风险金额 ($)
    # 仓位建议
    suggested_max_position: float   # 建议单笔最大头寸 ($)
    suggested_max_position_pct: float # 建议单笔最大占比 (%)
    suggested_max_stocks: int       # 建议最大持仓数
    # 风险等级
    risk_level: str                 # 🟢 安全 / 🟡 适中 / 🔴 高风险 / 🔴🔴 超限
    risk_score: int                 # 0-100，越高越危险
    observations: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


# ─── 核心函数 ─────────────────────────────────────────────────

def calc_risk_budget(client, max_risk_tolerance: float = 20.0) -> Optional[RiskBudgetReport]:
    """
    计算风险预算
    max_risk_tolerance: 用户可接受的最大总亏损百分比 (默认 20%)
    """
    from portfolio_analytics import _calc_daily_returns

    positions = client.get_positions()
    if not positions:
        return None

    # ── 组合概况 ──
    stock_positions = [p for p in positions if p.sec_type == "STK"]
    total_invested = sum(abs(p.market_value) for p in positions)

    # 尝试获取账户总净值（含现金）
    try:
        account_summary = client.get_account_summary()
        total_nav = account_summary.get("NetLiquidation", total_invested)
        cash_value = account_summary.get("TotalCashValue", 0)
        if isinstance(total_nav, str):
            total_nav = float(total_nav)
        if isinstance(cash_value, str):
            cash_value = float(cash_value)
    except Exception:
        total_nav = total_invested
        cash_value = 0

    if total_nav <= 0:
        total_nav = total_invested if total_invested > 0 else 1

    cash_pct = (cash_value / total_nav * 100) if total_nav > 0 else 0
    position_count = len(positions)

    # ── 集中度 ──
    weights = [abs(p.market_value) / total_invested * 100 for p in positions] if total_invested > 0 else []
    hhi = sum(w ** 2 for w in weights) if weights else 0
    max_single = max(weights) if weights else 0

    # ── 组合 Beta (简化版) ──
    portfolio_beta = 1.0
    if stock_positions:
        stock_total = sum(abs(p.market_value) for p in stock_positions)
        # 尝试用 Finviz 获取 Beta
        try:
            from finviz_data import get_finviz_fundamentals_batch
            syms = [p.symbol for p in stock_positions]
            fv_batch = get_finviz_fundamentals_batch(syms, max_workers=5)
            weighted_beta = 0.0
            for p in stock_positions:
                w = abs(p.market_value) / stock_total if stock_total > 0 else 0
                beta_str = fv_batch.get(p.symbol, {}).get("Beta", "1.0")
                try:
                    b = float(beta_str)
                except (ValueError, TypeError):
                    b = 1.0
                weighted_beta += w * b
            portfolio_beta = weighted_beta
        except Exception:
            portfolio_beta = 1.0

    # ── 组合波动率估算 ──
    # 简化：用 Beta * 市场年化波动率 (~16%) 估算
    market_vol = 16.0
    portfolio_vol = abs(portfolio_beta) * market_vol

    # ── 风险预算计算 ──
    # 已使用风险 = 综合评估
    risk_factors = []

    # Factor 1: 仓位暴露 (已投资比例)
    invested_pct = (total_invested / total_nav * 100) if total_nav > 0 else 100
    exposure_risk = min(invested_pct, 100)
    risk_factors.append(("仓位暴露", exposure_risk))

    # Factor 2: Beta 风险
    beta_risk = min(abs(portfolio_beta) * 50, 100)  # Beta=2 → 100%
    risk_factors.append(("Beta风险", beta_risk))

    # Factor 3: 集中度风险
    if hhi > 3000:
        conc_risk = 90
    elif hhi > 2000:
        conc_risk = 70
    elif hhi > 1500:
        conc_risk = 50
    elif hhi > 1000:
        conc_risk = 30
    else:
        conc_risk = 10
    risk_factors.append(("集中度", conc_risk))

    # Factor 4: 现金缓冲
    if cash_pct >= 30:
        cash_risk = 10
    elif cash_pct >= 20:
        cash_risk = 25
    elif cash_pct >= 10:
        cash_risk = 45
    elif cash_pct >= 5:
        cash_risk = 65
    else:
        cash_risk = 85
    risk_factors.append(("现金不足", cash_risk))

    # 综合风险评分 (加权平均)
    risk_score = int(
        exposure_risk * 0.30 +
        beta_risk * 0.25 +
        conc_risk * 0.25 +
        cash_risk * 0.20
    )
    risk_score = max(0, min(100, risk_score))

    # 已使用风险额度
    used_risk = risk_score / 100 * max_risk_tolerance
    remaining_risk = max(0, max_risk_tolerance - used_risk)
    remaining_value = total_nav * remaining_risk / 100

    # ── 仓位建议 ──
    # 凯利公式简化：单笔头寸 ≤ 总资产的 1/N (N=目标持仓数)
    if position_count <= 3:
        suggested_pct = 10  # 持仓太少，控制单笔 10%
        suggested_max_stocks = 10
    elif position_count <= 8:
        suggested_pct = 8
        suggested_max_stocks = 15
    elif position_count <= 15:
        suggested_pct = 5
        suggested_max_stocks = 20
    else:
        suggested_pct = 3
        suggested_max_stocks = 25

    suggested_max = total_nav * suggested_pct / 100

    # ── 风险等级 ──
    if risk_score <= 30:
        risk_level = "🟢 安全"
    elif risk_score <= 50:
        risk_level = "🟡 适中"
    elif risk_score <= 75:
        risk_level = "🔴 高风险"
    else:
        risk_level = "🔴🔴 超限"

    # ── 建议 ──
    observations = []
    recommendations = []

    if cash_pct < 5:
        observations.append(f"现金比例仅 {cash_pct:.1f}%，几乎满仓")
        recommendations.append("建议保留至少 10% 现金作为安全缓冲")
    elif cash_pct < 10:
        observations.append(f"现金比例 {cash_pct:.1f}%，偏低")
        recommendations.append("考虑适当减仓，提高现金比例至 15-20%")

    if portfolio_beta > 1.3:
        observations.append(f"组合 Beta={portfolio_beta:.2f}，属高弹性组合")
        recommendations.append("如果不看好后市，考虑降低高 Beta 个股仓位")
    elif portfolio_beta < 0.7:
        observations.append(f"组合 Beta={portfolio_beta:.2f}，防御性较强")

    if max_single > 25:
        observations.append(f"最大单只占比 {max_single:.1f}%，集中度过高")
        recommendations.append(f"建议分散投资，单只占比控制在 {suggested_pct}% 以内")

    if hhi > 2500:
        observations.append(f"HHI={hhi:.0f}，高度集中")
    elif hhi > 1500:
        observations.append(f"HHI={hhi:.0f}，中等集中")

    if remaining_risk <= 0:
        recommendations.append("⚠️ 风险预算已耗尽，不建议新增仓位")
    elif remaining_risk < 5:
        recommendations.append(f"剩余风险额度仅 {remaining_risk:.1f}%，仅可小规模试探")
    else:
        recommendations.append(f"剩余可用风险额度 {remaining_risk:.1f}%（约 ${remaining_value:,.0f}），可适度布局")

    return RiskBudgetReport(
        total_nav=round(total_nav, 2),
        cash_value=round(cash_value, 2),
        cash_pct=round(cash_pct, 2),
        invested_value=round(total_invested, 2),
        position_count=position_count,
        portfolio_beta=round(portfolio_beta, 3),
        portfolio_volatility_pct=round(portfolio_vol, 2),
        hhi_index=round(hhi, 2),
        max_single_pct=round(max_single, 2),
        max_total_risk_pct=max_risk_tolerance,
        used_risk_pct=round(used_risk, 2),
        remaining_risk_pct=round(remaining_risk, 2),
        remaining_risk_value=round(remaining_value, 2),
        suggested_max_position=round(suggested_max, 2),
        suggested_max_position_pct=suggested_pct,
        suggested_max_stocks=suggested_max_stocks,
        risk_level=risk_level,
        risk_score=risk_score,
        observations=observations,
        recommendations=recommendations
    )


# ─── 格式化输出 ───────────────────────────────────────────────

def format_risk_budget(r: RiskBudgetReport) -> str:
    if not r:
        return "⚠️ 无法计算风险预算"

    # 风险仪表盘
    bar_pos = int(r.risk_score / 5)
    bar = "█" * bar_pos + "░" * (20 - bar_pos)

    lines = [
        f"🎛️ 风险预算计算器",
        "=" * 55,
        f"  {r.risk_level}  风险评分: {r.risk_score}/100",
        f"  安全 [{bar}] 超限",
        "",
        f"  📊 组合概况:",
        f"     总净值: ${r.total_nav:,.0f}  |  已投资: ${r.invested_value:,.0f}",
        f"     现金: ${r.cash_value:,.0f} ({r.cash_pct:.1f}%)  |  持仓数: {r.position_count}",
        "",
        f"  📈 风险指标:",
        f"     Beta: {r.portfolio_beta:.2f}  |  年化波动率(估): {r.portfolio_volatility_pct:.1f}%",
        f"     HHI: {r.hhi_index:.0f}  |  最大单只: {r.max_single_pct:.1f}%",
        "",
        f"  🎯 风险预算:",
        f"     总风险容忍度: {r.max_total_risk_pct:.0f}%",
        f"     已使用: {r.used_risk_pct:.1f}%  |  剩余: {r.remaining_risk_pct:.1f}%",
        f"     剩余可承受金额: ${r.remaining_risk_value:,.0f}",
        "",
        f"  💡 仓位建议:",
        f"     建议单笔最大: ${r.suggested_max_position:,.0f} ({r.suggested_max_position_pct}%)",
        f"     建议最大持仓数: {r.suggested_max_stocks}",
    ]

    if r.observations:
        lines.append("")
        lines.append("  📋 风险观察:")
        for obs in r.observations:
            lines.append(f"     • {obs}")

    if r.recommendations:
        lines.append("")
        lines.append("  ✅ 建议:")
        for rec in r.recommendations:
            lines.append(f"     • {rec}")

    return "\n".join(lines)


def to_json_risk_budget(r: RiskBudgetReport) -> str:
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

    report = calc_risk_budget(client)
    if report:
        print(format_risk_budget(report))
    else:
        print("⚠️ 无持仓数据")

    client.disconnect()


if __name__ == "__main__":
    main()
