#!/usr/bin/env python3
"""
股票对比分析模块
提供：多只股票横向对比（估值、技术面、盈利能力、动量）。
所有函数接收 IBKRReadOnlyClient 实例，纯只读操作。
"""

import json
import dataclasses
from dataclasses import dataclass, field
from typing import List, Dict, Optional


# ─── 数据类 ───────────────────────────────────────────────────

@dataclass
class StockProfile:
    """单只股票对比概要"""
    symbol: str
    company: str
    sector: str
    industry: str
    market_cap: str
    price: float
    # 估值
    pe: str
    forward_pe: str
    peg: str
    ps: str
    pb: str
    # 盈利
    roe: str
    profit_margin: str
    eps_growth_next5y: str
    # 技术
    tech_score: int           # -100 ~ +100
    tech_signal: str
    rsi: float
    sma20_dist: str           # e.g. "3.5%"
    sma50_dist: str
    sma200_dist: str
    beta: str
    atr_pct: float
    # 动量
    perf_week: str
    perf_month: str
    perf_quarter: str
    perf_ytd: str
    # 分析师
    target_price: str
    recom: str                # 1(买)-5(卖)


@dataclass
class ComparisonReport:
    """对比分析报告"""
    profiles: List[StockProfile]
    winner_valuation: str     # 估值最优
    winner_growth: str        # 成长最优
    winner_technical: str     # 技术面最优
    winner_momentum: str      # 动量最优
    overall_winner: str       # 综合优胜
    observations: List[str] = field(default_factory=list)


# ─── 核心函数 ─────────────────────────────────────────────────

def compare_stocks(client, symbols: List[str]) -> Optional[ComparisonReport]:
    """
    对多只股票进行横向对比分析
    """
    if len(symbols) < 2:
        return None

    from finviz_data import get_finviz_fundamentals_batch
    from technical_analysis import analyze_symbols_batch

    # 并发获取 Finviz 基本面
    finviz_batch = get_finviz_fundamentals_batch(symbols, max_workers=5)

    # 并发获取技术面
    tech_batch = analyze_symbols_batch(client, symbols, period="1 Y", bar_size="1 day")

    profiles = []
    for sym in symbols:
        fv = finviz_batch.get(sym, {})
        tech = tech_batch.get(sym)

        tech_score = tech.score if tech else 0
        tech_signal = tech.overall_signal if tech else "N/A"
        rsi_val = tech.rsi.rsi_14 if tech else 0
        atr_pct = tech.atr.atr_pct if tech else 0
        price = tech.current_price if tech else 0

        profiles.append(StockProfile(
            symbol=sym,
            company=fv.get("Company", "N/A"),
            sector=fv.get("Sector", "N/A"),
            industry=fv.get("Industry", "N/A"),
            market_cap=fv.get("Market Cap", "N/A"),
            price=price,
            pe=fv.get("P/E", "-"),
            forward_pe=fv.get("Forward P/E", "-"),
            peg=fv.get("PEG", "-"),
            ps=fv.get("P/S", "-"),
            pb=fv.get("P/B", "-"),
            roe=fv.get("ROE", "-"),
            profit_margin=fv.get("Profit Margin", "-"),
            eps_growth_next5y=fv.get("EPS next 5Y", "-"),
            tech_score=tech_score,
            tech_signal=tech_signal,
            rsi=rsi_val,
            sma20_dist=fv.get("SMA20", "-"),
            sma50_dist=fv.get("SMA50", "-"),
            sma200_dist=fv.get("SMA200", "-"),
            beta=fv.get("Beta", "-"),
            atr_pct=atr_pct,
            perf_week=fv.get("Perf Week", "-"),
            perf_month=fv.get("Perf Month", "-"),
            perf_quarter=fv.get("Perf Quarter", "-"),
            perf_ytd=fv.get("Perf YTD", "-"),
            target_price=fv.get("Target Price", "-"),
            recom=fv.get("Recom", "-"),
        ))

    # ── 各维度评优 ──
    def _safe_float(s, default=9999):
        """尝试将字符串转为 float，支持百分号"""
        if not s or s == "-":
            return default
        try:
            return float(str(s).replace("%", "").replace(",", ""))
        except (ValueError, TypeError):
            return default

    # 估值：PEG 越低越好（排除无效值）
    valid_peg = [(p.symbol, _safe_float(p.peg)) for p in profiles if _safe_float(p.peg) > 0]
    winner_val = min(valid_peg, key=lambda x: x[1])[0] if valid_peg else profiles[0].symbol

    # 成长：EPS 5Y 增速越高越好
    valid_growth = [(p.symbol, _safe_float(p.eps_growth_next5y, -9999)) for p in profiles]
    winner_growth = max(valid_growth, key=lambda x: x[1])[0]

    # 技术面：评分最高
    winner_tech = max(profiles, key=lambda p: p.tech_score).symbol

    # 动量：月涨幅最优
    valid_mom = [(p.symbol, _safe_float(p.perf_month, -9999)) for p in profiles]
    winner_mom = max(valid_mom, key=lambda x: x[1])[0]

    # 综合：各维度计分
    score_board = {sym: 0 for sym in symbols}
    for winner in [winner_val, winner_growth, winner_tech, winner_mom]:
        score_board[winner] = score_board.get(winner, 0) + 1
    overall = max(score_board, key=score_board.get)

    # 观察
    observations = []
    # 估值差异
    pe_vals = [(p.symbol, _safe_float(p.pe)) for p in profiles if _safe_float(p.pe) > 0]
    if len(pe_vals) >= 2:
        pe_vals.sort(key=lambda x: x[1])
        observations.append(f"估值: {pe_vals[0][0]}(PE={pe_vals[0][1]:.1f}) 估值最低, "
                          f"{pe_vals[-1][0]}(PE={pe_vals[-1][1]:.1f}) 估值最高")

    # 技术面差异
    tech_sorted = sorted(profiles, key=lambda p: p.tech_score, reverse=True)
    observations.append(f"技术面: {tech_sorted[0].symbol}({tech_sorted[0].tech_signal}, {tech_sorted[0].tech_score:+d}) 最强, "
                       f"{tech_sorted[-1].symbol}({tech_sorted[-1].tech_signal}, {tech_sorted[-1].tech_score:+d}) 最弱")

    # RSI 极端值
    for p in profiles:
        if p.rsi >= 70:
            observations.append(f"⚠️ {p.symbol} RSI={p.rsi:.0f} 超买")
        elif p.rsi <= 30:
            observations.append(f"💡 {p.symbol} RSI={p.rsi:.0f} 超卖")

    return ComparisonReport(
        profiles=profiles,
        winner_valuation=winner_val,
        winner_growth=winner_growth,
        winner_technical=winner_tech,
        winner_momentum=winner_mom,
        overall_winner=overall,
        observations=observations
    )


# ─── 格式化输出 ───────────────────────────────────────────────

def format_comparison(report: ComparisonReport) -> str:
    """格式化对比报告"""
    if not report or not report.profiles:
        return "⚠️ 对比数据不足"

    syms = [p.symbol for p in report.profiles]
    col_w = max(10, max(len(s) for s in syms) + 2)

    lines = [
        f"⚔️ 股票对比分析: {' vs '.join(syms)}",
        "=" * (20 + col_w * len(syms)),
    ]

    # 表头
    header = f"  {'指标':<16s}"
    for p in report.profiles:
        header += f" {p.symbol:>{col_w}s}"
    lines.append(header)
    lines.append("  " + "─" * (16 + col_w * len(report.profiles)))

    # 基础信息
    _row = lambda label, getter: f"  {label:<16s}" + "".join(f" {str(getter(p)):>{col_w}s}" for p in report.profiles)

    lines.append(_row("公司", lambda p: p.company[:col_w]))
    lines.append(_row("行业", lambda p: p.industry[:col_w]))
    lines.append(_row("市值", lambda p: p.market_cap))
    lines.append(_row("价格", lambda p: f"${p.price:,.2f}"))
    lines.append("")

    # 估值
    lines.append("  📊 估值")
    lines.append(_row("  P/E", lambda p: p.pe))
    lines.append(_row("  Forward P/E", lambda p: p.forward_pe))
    lines.append(_row("  PEG", lambda p: p.peg))
    lines.append(_row("  P/S", lambda p: p.ps))
    lines.append(_row("  P/B", lambda p: p.pb))
    lines.append("")

    # 盈利
    lines.append("  💰 盈利能力")
    lines.append(_row("  ROE", lambda p: p.roe))
    lines.append(_row("  净利率", lambda p: p.profit_margin))
    lines.append(_row("  EPS 5Y增速", lambda p: p.eps_growth_next5y))
    lines.append("")

    # 技术面
    lines.append("  📈 技术面")
    lines.append(_row("  技术评分", lambda p: f"{p.tech_score:+d}"))
    lines.append(_row("  信号", lambda p: p.tech_signal))
    lines.append(_row("  RSI(14)", lambda p: f"{p.rsi:.1f}"))
    lines.append(_row("  SMA20偏离", lambda p: p.sma20_dist))
    lines.append(_row("  SMA50偏离", lambda p: p.sma50_dist))
    lines.append(_row("  Beta", lambda p: p.beta))
    lines.append("")

    # 动量
    lines.append("  🚀 动量")
    lines.append(_row("  周涨幅", lambda p: p.perf_week))
    lines.append(_row("  月涨幅", lambda p: p.perf_month))
    lines.append(_row("  季涨幅", lambda p: p.perf_quarter))
    lines.append(_row("  YTD", lambda p: p.perf_ytd))
    lines.append("")

    # 分析师
    lines.append("  ⭐ 分析师")
    lines.append(_row("  目标价", lambda p: p.target_price))
    lines.append(_row("  推荐(1买5卖)", lambda p: p.recom))
    lines.append("")

    # 胜出者
    lines.append("  🏆 各维度优胜者:")
    lines.append(f"     估值最优: {report.winner_valuation}")
    lines.append(f"     成长最优: {report.winner_growth}")
    lines.append(f"     技术最强: {report.winner_technical}")
    lines.append(f"     动量最强: {report.winner_momentum}")
    lines.append(f"     ⭐ 综合优胜: {report.overall_winner}")

    if report.observations:
        lines.append("")
        lines.append("  💡 关键观察:")
        for obs in report.observations:
            lines.append(f"     {obs}")

    return "\n".join(lines)


def to_json_comparison(report: ComparisonReport) -> str:
    """JSON 输出"""
    return json.dumps(dataclasses.asdict(report), ensure_ascii=False, indent=2)


# ─── 独立运行入口 ─────────────────────────────────────────────

def main():
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ibkr_readonly import IBKRReadOnlyClient

    client = IBKRReadOnlyClient()
    if not client.connect():
        print("❌ 无法连接 IB Gateway")
        return

    report = compare_stocks(client, ["AAPL", "MSFT", "NVDA"])
    if report:
        print(format_comparison(report))
    else:
        print("⚠️ 对比分析失败")

    client.disconnect()


if __name__ == "__main__":
    main()
