#!/usr/bin/env python3
"""
VIX 恐慌指数仪表盘
提供：VIX 当前水平、历史百分位排名、恐慌/贪婪度量。
所有函数接收 IBKRReadOnlyClient 实例，纯只读操作。
"""

import json
import dataclasses
from dataclasses import dataclass, field
from typing import Optional, List


# ─── 数据类 ───────────────────────────────────────────────────

@dataclass
class VIXDashboard:
    """VIX 恐慌指数仪表盘"""
    current_vix: float
    prev_close: float
    change_pct: float               # 日涨跌幅
    # 百分位排名
    percentile_1y: float             # 过去 1 年百分位 (0-100)
    percentile_label: str            # "极低" / "低" / "正常" / "偏高" / "高" / "极端恐慌"
    # 区间统计
    vix_52w_high: float
    vix_52w_low: float
    vix_mean_1y: float
    vix_median_1y: float
    # 情绪指标
    fear_greed_signal: str           # 🟢 贪婪 / 🟡 中性 / 🔴 恐慌 / 🔴🔴 极端恐慌
    fear_greed_score: int            # 0(极端恐慌) ~ 100(极度贪婪)
    # 波动率期限结构
    vix_trend_5d: str                # "上升" / "下降" / "持平"
    key_observations: List[str] = field(default_factory=list)


# ─── 分析函数 ─────────────────────────────────────────────────

def analyze_vix(client) -> Optional[VIXDashboard]:
    """
    VIX 恐慌指数仪表盘分析
    """
    # 获取 VIX 1 年日线数据
    bars = client.get_historical_data("VIX", duration="1 Y", bar_size="1 day")
    if not bars or len(bars) < 20:
        return None

    closes = [b["close"] for b in bars]
    current = closes[-1]
    prev = closes[-2] if len(closes) >= 2 else current
    change_pct = ((current - prev) / prev * 100) if prev != 0 else 0

    # 百分位排名
    sorted_closes = sorted(closes)
    rank = sum(1 for c in sorted_closes if c <= current)
    percentile = (rank / len(sorted_closes)) * 100

    # 百分位标签
    if percentile >= 95:
        pct_label = "🔴🔴 极端恐慌"
    elif percentile >= 80:
        pct_label = "🔴 高位恐慌"
    elif percentile >= 65:
        pct_label = "🟡 偏高"
    elif percentile >= 35:
        pct_label = "⚪ 正常区间"
    elif percentile >= 15:
        pct_label = "🟢 偏低（乐观）"
    else:
        pct_label = "🟢🟢 极低（极度贪婪）"

    # 52 周高低
    vix_high = max(closes)
    vix_low = min(closes)
    vix_mean = sum(closes) / len(closes)
    sorted_for_median = sorted(closes)
    mid = len(sorted_for_median) // 2
    vix_median = sorted_for_median[mid] if len(sorted_for_median) % 2 else (sorted_for_median[mid - 1] + sorted_for_median[mid]) / 2

    # 恐慌/贪婪评分 (反转百分位: VIX 越高越恐慌 → 评分越低)
    fear_greed = max(0, min(100, int(100 - percentile)))

    if fear_greed <= 10:
        fg_signal = "🔴🔴 极端恐慌"
    elif fear_greed <= 25:
        fg_signal = "🔴 恐慌"
    elif fear_greed <= 45:
        fg_signal = "🟡 偏恐慌"
    elif fear_greed <= 55:
        fg_signal = "⚪ 中性"
    elif fear_greed <= 75:
        fg_signal = "🟡 偏贪婪"
    elif fear_greed <= 90:
        fg_signal = "🟢 贪婪"
    else:
        fg_signal = "🟢🟢 极度贪婪"

    # 5 日趋势
    recent_5 = closes[-5:] if len(closes) >= 5 else closes
    if len(recent_5) >= 2:
        trend_change = recent_5[-1] - recent_5[0]
        if trend_change > 1.0:
            trend_5d = "📈 上升"
        elif trend_change < -1.0:
            trend_5d = "📉 下降"
        else:
            trend_5d = "➡️ 持平"
    else:
        trend_5d = "N/A"

    # 关键观察
    observations = []
    if current >= 30:
        observations.append(f"VIX 高于 30 ({current:.1f})，市场处于恐慌状态，历史上常为超卖反弹区域")
    elif current >= 25:
        observations.append(f"VIX 在 25-30 区间 ({current:.1f})，市场波动显著升高，注意风险管理")
    elif current >= 20:
        observations.append(f"VIX 在 20-25 区间 ({current:.1f})，波动偏高但未到恐慌")
    elif current <= 13:
        observations.append(f"VIX 低于 13 ({current:.1f})，市场极度自满，警惕突发波动")
    elif current <= 16:
        observations.append(f"VIX 在 13-16 区间 ({current:.1f})，市场整体平静")

    if abs(change_pct) >= 10:
        observations.append(f"VIX 单日波动 {change_pct:+.1f}%，属异常剧烈变化")
    
    if percentile >= 90:
        observations.append("当前 VIX 处于近一年 90% 以上高位，历史上后续 30 天均值回归概率较高")
    elif percentile <= 10:
        observations.append("当前 VIX 处于近一年 10% 以下低位，市场可能过度自满")

    return VIXDashboard(
        current_vix=round(current, 2),
        prev_close=round(prev, 2),
        change_pct=round(change_pct, 2),
        percentile_1y=round(percentile, 1),
        percentile_label=pct_label,
        vix_52w_high=round(vix_high, 2),
        vix_52w_low=round(vix_low, 2),
        vix_mean_1y=round(vix_mean, 2),
        vix_median_1y=round(vix_median, 2),
        fear_greed_signal=fg_signal,
        fear_greed_score=fear_greed,
        vix_trend_5d=trend_5d,
        key_observations=observations
    )


# ─── 格式化输出 ───────────────────────────────────────────────

def format_vix_dashboard(v: VIXDashboard) -> str:
    """格式化 VIX 仪表盘"""
    if not v:
        return "⚠️ VIX 数据获取失败"

    # 构建视觉化条形图
    bar_pos = int(v.percentile_1y / 5)  # 0-20 的位置
    bar = "░" * bar_pos + "█" + "░" * (20 - bar_pos)

    lines = [
        f"😱 VIX 恐慌指数仪表盘",
        "=" * 55,
        f"  当前 VIX: {v.current_vix:.2f}  ({v.change_pct:+.1f}%)",
        f"  恐慌/贪婪: {v.fear_greed_signal}  评分: {v.fear_greed_score}/100",
        "",
        f"  📊 1年百分位: {v.percentile_1y:.0f}%  {v.percentile_label}",
        f"  贪婪 [{bar}] 恐慌",
        "",
        f"  📈 52周范围: {v.vix_52w_low:.1f} — {v.vix_52w_high:.1f}",
        f"  📊 1年均值: {v.vix_mean_1y:.1f}  |  中位数: {v.vix_median_1y:.1f}",
        f"  📉 5日趋势: {v.vix_trend_5d}",
    ]

    if v.key_observations:
        lines.append("")
        lines.append("  💡 关键观察:")
        for obs in v.key_observations:
            lines.append(f"     • {obs}")

    return "\n".join(lines)


def to_json_vix(dashboard: VIXDashboard) -> str:
    """JSON 输出"""
    return json.dumps(dataclasses.asdict(dashboard), ensure_ascii=False, indent=2)


# ─── 独立运行入口 ─────────────────────────────────────────────

def main():
    """独立运行：展示 VIX 仪表盘"""
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ibkr_readonly import IBKRReadOnlyClient

    client = IBKRReadOnlyClient()
    if not client.connect():
        print("❌ 无法连接 IB Gateway")
        return

    dashboard = analyze_vix(client)
    if dashboard:
        print(format_vix_dashboard(dashboard))
    else:
        print("⚠️ 无法获取 VIX 数据")

    client.disconnect()


if __name__ == "__main__":
    main()
