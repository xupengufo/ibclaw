#!/usr/bin/env python3
"""
板块轮动监控模块
跟踪 11 个 SPDR 板块 ETF 的动量排名与相对强度 (RS)。
所有函数接收 IBKRReadOnlyClient 实例，纯只读操作。
"""

import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict


# ─── 板块 ETF 定义 ───────────────────────────────────────────

SECTOR_ETFS = {
    "XLK": "科技 (Technology)",
    "XLF": "金融 (Financials)",
    "XLE": "能源 (Energy)",
    "XLV": "医疗 (Health Care)",
    "XLY": "可选消费 (Cons. Discretionary)",
    "XLP": "必需消费 (Cons. Staples)",
    "XLI": "工业 (Industrials)",
    "XLB": "材料 (Materials)",
    "XLRE": "房地产 (Real Estate)",
    "XLU": "公用事业 (Utilities)",
    "XLC": "通信 (Communication)",
}

BENCHMARK = "SPY"


# ─── 数据类 ───────────────────────────────────────────────────

@dataclass
class SectorPerformance:
    """单个板块的表现"""
    symbol: str
    name: str
    period_return_pct: float    # 区间涨跌幅
    rs_vs_spy: float            # 相对强度 (sector return - SPY return)
    current_price: float = 0.0
    rank: int = 0               # 动量排名 (1 = 最强)
    momentum_signal: str = ""   # "领涨" / "跟涨" / "滞涨" / "领跌"


@dataclass
class SectorRotationReport:
    """板块轮动报告"""
    period: str
    benchmark_return_pct: float
    sectors: List[SectorPerformance]
    leading_sectors: List[str]  # "资金流入"板块
    lagging_sectors: List[str]  # "资金流出"板块
    rotation_signal: str        # "进攻型轮动" / "防御型轮动" / "均衡"


# ─── 核心计算 ─────────────────────────────────────────────────

def _calc_period_return(bars: List[dict]) -> float:
    """计算区间收益率"""
    if not bars or len(bars) < 2:
        return 0.0
    first = bars[0]["close"]
    last = bars[-1]["close"]
    return round((last - first) / first * 100, 2)


def get_sector_rotation(client, period: str = "1 M") -> Optional[SectorRotationReport]:
    """
    获取板块轮动报告。

    Args:
        client: IBKRReadOnlyClient
        period: 回看周期 ("1 W", "1 M", "3 M", "6 M", "1 Y")

    Returns:
        SectorRotationReport 或 None
    """
    # 1. 获取基准收益率
    spy_bars = client.get_historical_data(BENCHMARK, duration=period, bar_size="1 day")
    if not spy_bars or len(spy_bars) < 5:
        print("⚠️ 无法获取 SPY 基准数据")
        return None

    spy_return = _calc_period_return(spy_bars)
    spy_price = spy_bars[-1]["close"]

    # 2. 获取各板块收益率
    sectors = []
    for symbol, name in SECTOR_ETFS.items():
        try:
            bars = client.get_historical_data(symbol, duration=period, bar_size="1 day")
            if not bars or len(bars) < 5:
                continue

            sector_return = _calc_period_return(bars)
            rs = round(sector_return - spy_return, 2)
            current_price = bars[-1]["close"]

            sectors.append(SectorPerformance(
                symbol=symbol,
                name=name,
                period_return_pct=sector_return,
                rs_vs_spy=rs,
                current_price=current_price,
            ))
        except Exception as e:
            print(f"⚠️ {symbol} 数据获取失败: {e}")

    if not sectors:
        return None

    # 3. 按收益率排序并编号
    sectors.sort(key=lambda s: s.period_return_pct, reverse=True)
    for i, s in enumerate(sectors):
        s.rank = i + 1
        # 动量信号分类
        if s.rs_vs_spy > 3:
            s.momentum_signal = "🟢 领涨"
        elif s.rs_vs_spy > 0:
            s.momentum_signal = "🔵 跟涨"
        elif s.rs_vs_spy > -3:
            s.momentum_signal = "🟡 滞涨"
        else:
            s.momentum_signal = "🔴 领跌"

    # 4. 判断轮动类型
    leading = [s.symbol for s in sectors if s.rs_vs_spy > 2]
    lagging = [s.symbol for s in sectors if s.rs_vs_spy < -2]

    # 进攻型板块：XLK, XLY, XLC, XLF, XLE
    # 防御型板块：XLU, XLP, XLV, XLRE
    offensive = {"XLK", "XLY", "XLC", "XLF", "XLE"}
    defensive = {"XLU", "XLP", "XLV", "XLRE"}

    top_3 = {s.symbol for s in sectors[:3]}
    offensive_leading = len(top_3 & offensive)
    defensive_leading = len(top_3 & defensive)

    if offensive_leading >= 2:
        rotation_signal = "⚡ 进攻型轮动 (Risk-On)"
    elif defensive_leading >= 2:
        rotation_signal = "🛡️ 防御型轮动 (Risk-Off)"
    else:
        rotation_signal = "⚖️ 均衡轮动"

    return SectorRotationReport(
        period=period,
        benchmark_return_pct=spy_return,
        sectors=sectors,
        leading_sectors=leading,
        lagging_sectors=lagging,
        rotation_signal=rotation_signal,
    )


# ─── 格式化输出 ───────────────────────────────────────────────

def to_json_sectors(report: SectorRotationReport) -> str:
    """JSON 输出"""
    import dataclasses
    data = dataclasses.asdict(report)
    return json.dumps(data, ensure_ascii=False, indent=2)


def format_sector_rotation(report: SectorRotationReport) -> str:
    """格式化板块轮动报告"""
    if not report:
        return "🌍 板块轮动: 数据不足"

    spy_emoji = "📈" if report.benchmark_return_pct >= 0 else "📉"

    lines = [
        f"🌍 板块轮动监控 ({report.period})",
        "=" * 65,
        f"  {spy_emoji} SPY 基准: {report.benchmark_return_pct:+.2f}%",
        f"  🎯 轮动信号: {report.rotation_signal}",
        "",
        f"  {'排名':4s} {'板块':6s} {'名称':24s} {'涨跌幅':>8s} {'RS':>8s} {'信号':10s}",
    ]

    for s in report.sectors:
        lines.append(
            f"  {s.rank:3d}.  {s.symbol:6s} {s.name:24s} "
            f"{s.period_return_pct:>+7.2f}% {s.rs_vs_spy:>+7.2f}  {s.momentum_signal}"
        )

    # 资金流向总结
    lines.append("")
    if report.leading_sectors:
        lines.append(f"  💰 资金流入: {', '.join(report.leading_sectors)}")
    if report.lagging_sectors:
        lines.append(f"  💸 资金流出: {', '.join(report.lagging_sectors)}")

    return "\n".join(lines)


# ─── 独立运行入口 ─────────────────────────────────────────────

def main():
    """独立运行：测试板块轮动"""
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ibkr_readonly import IBKRReadOnlyClient

    client = IBKRReadOnlyClient()
    if not client.connect():
        print("❌ 无法连接 IB Gateway")
        return

    print("🌍 板块轮动监控")
    print("=" * 60)

    for period in ["1 M", "3 M"]:
        report = get_sector_rotation(client, period)
        if report:
            print(format_sector_rotation(report))
            print()

    client.disconnect()
    print("✅ 分析完成")


if __name__ == "__main__":
    main()
