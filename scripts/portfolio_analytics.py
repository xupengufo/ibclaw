#!/usr/bin/env python3
"""
投资组合分析 + 绩效追踪模块
提供：资产配置分布、持仓集中度、组合 Beta、相关性矩阵、基准对比、盈亏归因、最大回撤。
所有函数接收 IBKRReadOnlyClient 实例，纯只读操作。
"""

import math
import statistics
import json
import dataclasses
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple


# ─── 数据类 ───────────────────────────────────────────────────

@dataclass
class AllocationItem:
    """资产配置条目"""
    label: str          # 分类标签（如行业名或资产类型）
    market_value: float
    weight_pct: float   # 占总资产百分比
    count: int          # 持仓数量


@dataclass
class ConcentrationReport:
    """持仓集中度报告"""
    top_holdings: List[dict]   # [{symbol, weight_pct, market_value}]
    hhi_index: float           # 赫芬达尔指数 (0-10000)
    max_single_pct: float      # 最大单只占比
    warnings: List[str]        # 风险警告


@dataclass
class BenchmarkComparison:
    """基准对比"""
    portfolio_return_pct: float
    benchmark_return_pct: float
    alpha_pct: float            # 超额收益
    benchmark_symbol: str
    period: str


@dataclass
class PerformanceAttribution:
    """盈亏归因"""
    symbol: str
    unrealized_pnl: float
    contribution_pct: float     # 对组合总盈亏的贡献占比
    weight_pct: float           # 持仓权重


@dataclass
class DrawdownInfo:
    """最大回撤信息"""
    max_drawdown_pct: float
    peak_date: str
    trough_date: str
    peak_value: float
    trough_value: float
    symbol_or_label: str


# ─── 分析函数 ─────────────────────────────────────────────────

def get_portfolio_allocation(client) -> Dict[str, List[AllocationItem]]:
    """
    获取资产配置分布，按两个维度分组：
    1. 按资产类型 (STK, OPT, FUT, etc.)
    2. 按行业/板块（仅股票类）
    返回: {"by_type": [...], "by_sector": [...]}
    """
    positions = client.get_positions()
    if not positions:
        return {"by_type": [], "by_sector": []}

    total_value = sum(abs(p.market_value) for p in positions)
    if total_value == 0:
        return {"by_type": [], "by_sector": []}

    # --- 按资产类型 ---
    type_groups: Dict[str, dict] = {}
    for p in positions:
        key = p.sec_type or "OTHER"
        if key not in type_groups:
            type_groups[key] = {"value": 0.0, "count": 0}
        type_groups[key]["value"] += abs(p.market_value)
        type_groups[key]["count"] += 1

    by_type = sorted([
        AllocationItem(
            label=k,
            market_value=v["value"],
            weight_pct=round(v["value"] / total_value * 100, 2),
            count=v["count"]
        )
        for k, v in type_groups.items()
    ], key=lambda x: x.weight_pct, reverse=True)

    # --- 按行业/板块（仅股票） ---
    stock_positions = [p for p in positions if p.sec_type == "STK"]
    stock_total = sum(abs(p.market_value) for p in stock_positions)

    sector_groups: Dict[str, dict] = {}
    for p in stock_positions:
        # 尝试获取基本面中的 sector 信息
        try:
            fund = client.get_fundamentals(p.symbol)
            sector = fund.sector or fund.industry or "未知"
        except Exception:
            sector = "未知"
        if sector not in sector_groups:
            sector_groups[sector] = {"value": 0.0, "count": 0}
        sector_groups[sector]["value"] += abs(p.market_value)
        sector_groups[sector]["count"] += 1

    by_sector = sorted([
        AllocationItem(
            label=k,
            market_value=v["value"],
            weight_pct=round(v["value"] / stock_total * 100, 2) if stock_total else 0,
            count=v["count"]
        )
        for k, v in sector_groups.items()
    ], key=lambda x: x.weight_pct, reverse=True)

    return {"by_type": by_type, "by_sector": by_sector}


def get_concentration_risk(client) -> ConcentrationReport:
    """
    分析持仓集中度风险
    - HHI 指数：< 1500 分散, 1500-2500 中等集中, > 2500 高度集中
    - 单只持仓占比 > 25% 触发警告
    """
    positions = client.get_positions()
    if not positions:
        return ConcentrationReport([], 0, 0, ["无持仓数据"])

    total_value = sum(abs(p.market_value) for p in positions)
    if total_value == 0:
        return ConcentrationReport([], 0, 0, ["总市值为零"])

    # 计算权重
    holdings = []
    for p in positions:
        weight = abs(p.market_value) / total_value * 100
        holdings.append({
            "symbol": p.symbol,
            "weight_pct": round(weight, 2),
            "market_value": p.market_value
        })

    holdings.sort(key=lambda x: x["weight_pct"], reverse=True)

    # HHI 指数
    weights = [h["weight_pct"] for h in holdings]
    hhi = sum(w ** 2 for w in weights)
    max_single = holdings[0]["weight_pct"] if holdings else 0

    # 风险警告
    warnings = []
    if hhi > 2500:
        warnings.append(f"⚠️ 组合高度集中 (HHI={hhi:.0f})，建议分散投资")
    elif hhi > 1500:
        warnings.append(f"⚡ 组合中等集中 (HHI={hhi:.0f})")

    for h in holdings:
        if h["weight_pct"] > 25:
            warnings.append(f"⚠️ {h['symbol']} 占比 {h['weight_pct']:.1f}%，超过 25% 阈值")

    if len(positions) < 5:
        warnings.append(f"📊 仅持有 {len(positions)} 个标的，分散度不足")

    return ConcentrationReport(
        top_holdings=holdings[:10],
        hhi_index=round(hhi, 2),
        max_single_pct=max_single,
        warnings=warnings
    )


def _calc_daily_returns(bars: List[dict]) -> List[float]:
    """从 K 线数据计算日收益率"""
    returns = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1]["close"]
        curr_close = bars[i]["close"]
        if prev_close and prev_close != 0:
            returns.append((curr_close - prev_close) / prev_close)
    return returns


def get_portfolio_beta(client, benchmark: str = "SPY", period: str = "6 M") -> Optional[dict]:
    """
    计算组合 Beta（相对基准）
    Beta = Cov(Rp, Rm) / Var(Rm)
    """
    positions = client.get_positions()
    stock_positions = [p for p in positions if p.sec_type == "STK"]
    if not stock_positions:
        return None

    total_value = sum(abs(p.market_value) for p in stock_positions)
    if total_value == 0:
        return None

    # 获取基准历史数据
    benchmark_bars = client.get_historical_data(benchmark, duration=period, bar_size="1 day")
    if len(benchmark_bars) < 20:
        return None
    bench_returns = _calc_daily_returns(benchmark_bars)

    # 加权 Beta
    portfolio_beta = 0.0
    processed = []

    for p in stock_positions:
        weight = abs(p.market_value) / total_value
        try:
            bars = client.get_historical_data(p.symbol, duration=period, bar_size="1 day")
            if len(bars) < 20:
                continue
            stock_returns = _calc_daily_returns(bars)

            # 对齐长度
            min_len = min(len(stock_returns), len(bench_returns))
            sr = stock_returns[-min_len:]
            br = bench_returns[-min_len:]

            # 计算 Beta
            mean_s = statistics.mean(sr)
            mean_b = statistics.mean(br)
            cov = sum((s - mean_s) * (b - mean_b) for s, b in zip(sr, br)) / (min_len - 1)
            var_b = statistics.variance(br)
            beta = cov / var_b if var_b != 0 else 1.0

            portfolio_beta += weight * beta
            processed.append({"symbol": p.symbol, "beta": round(beta, 3), "weight": round(weight * 100, 2)})
        except Exception:
            continue

    return {
        "portfolio_beta": round(portfolio_beta, 3),
        "benchmark": benchmark,
        "period": period,
        "holdings_beta": processed
    }


def get_correlation_matrix(client, period: str = "3 M") -> Optional[dict]:
    """
    计算持仓间的 Pearson 相关性矩阵（仅股票类）
    """
    positions = client.get_positions()
    stock_positions = [p for p in positions if p.sec_type == "STK"]

    if len(stock_positions) < 2:
        return None

    # 获取每只股票的日收益率
    symbols = []
    returns_map = {}

    for p in stock_positions[:15]:  # 限制数量避免过多 API 调用
        try:
            bars = client.get_historical_data(p.symbol, duration=period, bar_size="1 day")
            if len(bars) >= 20:
                returns_map[p.symbol] = _calc_daily_returns(bars)
                symbols.append(p.symbol)
        except Exception:
            continue

    if len(symbols) < 2:
        return None

    # 计算相关性矩阵
    matrix = {}
    for i, sym_a in enumerate(symbols):
        matrix[sym_a] = {}
        for j, sym_b in enumerate(symbols):
            if i == j:
                matrix[sym_a][sym_b] = 1.0
                continue

            ra = returns_map[sym_a]
            rb = returns_map[sym_b]
            min_len = min(len(ra), len(rb))
            ra_aligned = ra[-min_len:]
            rb_aligned = rb[-min_len:]

            try:
                corr = statistics.correlation(ra_aligned, rb_aligned)
                matrix[sym_a][sym_b] = round(corr, 3)
            except Exception:
                matrix[sym_a][sym_b] = None

    # 找出高度相关的持仓对
    high_corr_pairs = []
    for i, sym_a in enumerate(symbols):
        for j, sym_b in enumerate(symbols):
            if j <= i:
                continue
            corr_val = matrix[sym_a].get(sym_b)
            if corr_val is not None and abs(corr_val) >= 0.7:
                high_corr_pairs.append({
                    "pair": f"{sym_a} - {sym_b}",
                    "correlation": corr_val,
                    "warning": "高度正相关" if corr_val > 0 else "高度负相关"
                })

    return {
        "symbols": symbols,
        "matrix": matrix,
        "high_correlation_pairs": high_corr_pairs
    }


def get_benchmark_comparison(client, benchmark: str = "SPY", period: str = "3 M") -> Optional[BenchmarkComparison]:
    """
    对比组合加权收益率 vs 基准同期收益率
    """
    positions = client.get_positions()
    stock_positions = [p for p in positions if p.sec_type == "STK"]
    if not stock_positions:
        return None

    total_value = sum(abs(p.market_value) for p in stock_positions)
    if total_value == 0:
        return None

    # 基准收益
    bench_bars = client.get_historical_data(benchmark, duration=period, bar_size="1 day")
    if len(bench_bars) < 5:
        return None
    bench_return = (bench_bars[-1]["close"] - bench_bars[0]["close"]) / bench_bars[0]["close"] * 100

    # 组合加权收益
    portfolio_return = 0.0
    for p in stock_positions:
        weight = abs(p.market_value) / total_value
        try:
            bars = client.get_historical_data(p.symbol, duration=period, bar_size="1 day")
            if len(bars) >= 5:
                stock_return = (bars[-1]["close"] - bars[0]["close"]) / bars[0]["close"] * 100
                portfolio_return += weight * stock_return
        except Exception:
            continue

    return BenchmarkComparison(
        portfolio_return_pct=round(portfolio_return, 2),
        benchmark_return_pct=round(bench_return, 2),
        alpha_pct=round(portfolio_return - bench_return, 2),
        benchmark_symbol=benchmark,
        period=period
    )


def get_performance_attribution(client) -> List[PerformanceAttribution]:
    """
    盈亏归因：按持仓拆解各自对组合盈亏的贡献
    """
    positions = client.get_positions()
    if not positions:
        return []

    total_pnl = sum(p.unrealized_pnl for p in positions)
    total_value = sum(abs(p.market_value) for p in positions)

    result = []
    for p in positions:
        contribution = (p.unrealized_pnl / total_pnl * 100) if total_pnl != 0 else 0
        weight = abs(p.market_value) / total_value * 100 if total_value else 0
        result.append(PerformanceAttribution(
            symbol=p.symbol,
            unrealized_pnl=p.unrealized_pnl,
            contribution_pct=round(contribution, 2),
            weight_pct=round(weight, 2)
        ))

    result.sort(key=lambda x: abs(x.contribution_pct), reverse=True)
    return result


def get_max_drawdown(client, symbol: str = None, period: str = "1 Y") -> Optional[DrawdownInfo]:
    """
    计算最大回撤
    - 如果指定 symbol，计算该股票的最大回撤
    - 如果不指定，使用 SPY 作为市场基准
    """
    target = symbol or "SPY"
    bars = client.get_historical_data(target, duration=period, bar_size="1 day")
    if not bars or len(bars) < 5:
        return None

    peak = bars[0]["close"]
    peak_date = bars[0]["date"]
    max_dd = 0.0
    dd_peak_date = peak_date
    dd_trough_date = bars[0]["date"]
    dd_peak_val = peak
    dd_trough_val = peak

    for bar in bars:
        price = bar["close"]
        if price > peak:
            peak = price
            peak_date = bar["date"]
        drawdown = (peak - price) / peak * 100
        if drawdown > max_dd:
            max_dd = drawdown
            dd_peak_date = peak_date
            dd_trough_date = bar["date"]
            dd_peak_val = peak
            dd_trough_val = price

    return DrawdownInfo(
        max_drawdown_pct=round(max_dd, 2),
        peak_date=dd_peak_date,
        trough_date=dd_trough_date,
        peak_value=dd_peak_val,
        trough_value=dd_trough_val,
        symbol_or_label=target
    )


# ─── 格式化输出 ───────────────────────────────────────────────

def to_json_portfolio(data) -> str:
    """统一输出 JSON，供 AI 进行精准数字推理"""
    def default_encoder(obj):
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        return str(obj)
    
    return json.dumps(data, default=default_encoder, ensure_ascii=False, indent=2)

def format_allocation(alloc: Dict[str, List[AllocationItem]]) -> str:
    lines = []
    lines.append("📊 资产配置分布")
    lines.append("=" * 50)

    lines.append("\n📦 按资产类型:")
    for item in alloc.get("by_type", []):
        bar = "█" * int(item.weight_pct / 5) + "░" * max(0, 20 - int(item.weight_pct / 5))
        lines.append(f"  {item.label:6s} {bar} {item.weight_pct:6.1f}% ({item.count}只)")

    if alloc.get("by_sector"):
        lines.append("\n🏭 按行业板块 (仅股票):")
        for item in alloc["by_sector"]:
            bar = "█" * int(item.weight_pct / 5) + "░" * max(0, 20 - int(item.weight_pct / 5))
            lines.append(f"  {item.label[:12]:12s} {bar} {item.weight_pct:6.1f}%")

    return "\n".join(lines)


def format_concentration(report: ConcentrationReport) -> str:
    lines = []
    lines.append("🎯 持仓集中度分析")
    lines.append("=" * 50)
    lines.append(f"HHI 指数: {report.hhi_index:.0f}  (< 1500 分散 | 1500-2500 中等 | > 2500 集中)")
    lines.append(f"最大单只占比: {report.max_single_pct:.1f}%")
    lines.append("")

    if report.warnings:
        for w in report.warnings:
            lines.append(f"  {w}")
        lines.append("")

    lines.append("🔝 前十大持仓:")
    for i, h in enumerate(report.top_holdings[:10], 1):
        bar = "█" * int(h["weight_pct"] / 3)
        lines.append(f"  {i:2d}. {h['symbol']:8s} {bar} {h['weight_pct']:6.1f}%  (${h['market_value']:,.0f})")

    return "\n".join(lines)


def format_benchmark(comp: BenchmarkComparison) -> str:
    alpha_emoji = "🏆" if comp.alpha_pct > 0 else "📉"
    return (
        f"📈 基准对比 (vs {comp.benchmark_symbol}, {comp.period})\n"
        f"{'=' * 50}\n"
        f"  组合收益: {comp.portfolio_return_pct:+.2f}%\n"
        f"  基准收益: {comp.benchmark_return_pct:+.2f}%\n"
        f"  {alpha_emoji} Alpha: {comp.alpha_pct:+.2f}%"
    )


def format_attribution(attrs: List[PerformanceAttribution]) -> str:
    lines = ["🧩 盈亏归因分析", "=" * 50]
    for a in attrs:
        emoji = "📈" if a.unrealized_pnl >= 0 else "📉"
        sign = "+" if a.unrealized_pnl >= 0 else ""
        lines.append(
            f"  {emoji} {a.symbol:8s}  盈亏: {sign}${a.unrealized_pnl:,.0f}  "
            f"贡献: {a.contribution_pct:+.1f}%  权重: {a.weight_pct:.1f}%"
        )
    return "\n".join(lines)


def format_drawdown(dd: DrawdownInfo) -> str:
    return (
        f"📉 最大回撤 ({dd.symbol_or_label})\n"
        f"{'=' * 50}\n"
        f"  最大回撤: -{dd.max_drawdown_pct:.2f}%\n"
        f"  峰值: ${dd.peak_value:,.2f} ({dd.peak_date})\n"
        f"  谷底: ${dd.trough_value:,.2f} ({dd.trough_date})"
    )


# ─── 独立运行入口 ─────────────────────────────────────────────

def main():
    """独立运行：展示所有组合分析功能"""
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ibkr_readonly import IBKRReadOnlyClient

    client = IBKRReadOnlyClient()

    if not client.connect():
        print("❌ 无法连接 IB Gateway")
        return

    print("🏦 投资组合分析报告")
    print("=" * 60)
    print()

    # 1. 资产配置
    print("⏳ 正在分析资产配置...")
    alloc = get_portfolio_allocation(client)
    print(format_allocation(alloc))
    print()

    # 2. 持仓集中度
    print("⏳ 正在分析持仓集中度...")
    conc = get_concentration_risk(client)
    print(format_concentration(conc))
    print()

    # 3. 盈亏归因
    print("⏳ 正在分析盈亏归因...")
    attrs = get_performance_attribution(client)
    print(format_attribution(attrs))
    print()

    # 4. 基准对比
    print("⏳ 正在对比基准 (SPY, 3M)...")
    comp = get_benchmark_comparison(client, "SPY", "3 M")
    if comp:
        print(format_benchmark(comp))
    else:
        print("⚠️ 无法计算基准对比")
    print()

    # 5. 组合 Beta
    print("⏳ 正在计算组合 Beta...")
    beta = get_portfolio_beta(client, "SPY", "6 M")
    if beta:
        print(f"📊 组合 Beta: {beta['portfolio_beta']} (vs {beta['benchmark']}, {beta['period']})")
        for h in beta["holdings_beta"]:
            print(f"   {h['symbol']:8s} β={h['beta']:+.3f}  权重={h['weight']:.1f}%")
    print()

    # 6. 最大回撤
    print("⏳ 正在计算 SPY 最大回撤...")
    dd = get_max_drawdown(client, "SPY", "1 Y")
    if dd:
        print(format_drawdown(dd))
    print()

    # 7. 相关性矩阵
    print("⏳ 正在计算相关性矩阵...")
    corr = get_correlation_matrix(client, "3 M")
    if corr:
        print("📊 高相关性持仓对:")
        for pair in corr.get("high_correlation_pairs", []):
            print(f"   {pair['pair']}: {pair['correlation']:+.3f} ({pair['warning']})")
        if not corr.get("high_correlation_pairs"):
            print("   ✅ 未发现高度相关的持仓对")

    client.disconnect()
    print("\n✅ 组合分析完成")


if __name__ == "__main__":
    main()
