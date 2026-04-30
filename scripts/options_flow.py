#!/usr/bin/env python3
"""
期权异常活动扫描模块
检测：异常高成交量期权合约、Put/Call 比率异动、大额扫单信号。
所有函数接收 IBKRReadOnlyClient 实例，纯只读操作。
"""

import json
import dataclasses
from dataclasses import dataclass, field
from typing import Optional, List, Dict


# ─── 数据类 ───────────────────────────────────────────────────

@dataclass
class UnusualOption:
    """单条异常期权活动"""
    symbol: str
    expiry: str
    strike: float
    opt_type: str            # "C" / "P"
    volume: int
    open_interest: int
    vol_oi_ratio: float      # 成交量 / 未平仓量
    implied_vol: float
    delta: float
    last_price: float
    signal: str              # "📈 看涨大单" / "📉 看跌大单" / "⚠️ 异常活跃"
    score: int               # 异常度评分 0-100


@dataclass
class OptionsFlowReport:
    """期权异常活动报告"""
    symbol: str
    current_price: float
    total_call_volume: int
    total_put_volume: int
    put_call_ratio: float
    pc_ratio_signal: str     # "极端看跌" / "偏看跌" / "中性" / "偏看涨" / "极端看涨"
    unusual_activities: List[UnusualOption]
    observations: List[str] = field(default_factory=list)


# ─── 核心函数 ─────────────────────────────────────────────────

def scan_unusual_options(client, symbol: str, min_vol_oi_ratio: float = 2.0) -> Optional[OptionsFlowReport]:
    """
    扫描指定股票的异常期权活动
    min_vol_oi_ratio: 最低成交量/未平仓量比 (高比率 = 异常活跃)
    """
    current_price = 0
    try:
        bars = client.get_historical_data(symbol, duration="5 D", bar_size="1 day")
        if bars:
            current_price = bars[-1]["close"]
    except Exception:
        pass

    if current_price <= 0:
        return None

    # 获取多个到期日的期权链
    chain_data = client.get_option_chain_data(symbol)
    if not chain_data:
        return None

    chain_inner = chain_data.get("chain", {})
    calls = chain_inner.get("calls", [])
    puts = chain_inner.get("puts", [])

    total_call_vol = 0
    total_put_vol = 0
    unusual = []

    for opt_list, opt_type in [(calls, "C"), (puts, "P")]:
        for opt in opt_list:
            vol = opt.get("volume", 0)
            oi = opt.get("openInterest", 0)

            if opt_type == "C":
                total_call_vol += vol
            else:
                total_put_vol += vol

            # 异常检测: 成交量/OI 比率
            if oi > 0 and vol > 0:
                vol_oi = vol / oi
            elif vol > 100 and oi == 0:
                vol_oi = vol  # 全新合约大量成交
            else:
                continue

            if vol_oi < min_vol_oi_ratio and vol < 500:
                continue

            iv = opt.get("impliedVol", 0)
            delta = opt.get("delta", 0)
            strike = opt.get("strike", 0)
            expiry = opt.get("expiry", "")
            last = opt.get("lastPrice", 0)

            # 分类信号
            if opt_type == "C" and vol_oi >= 5:
                signal = "📈 看涨大单"
            elif opt_type == "P" and vol_oi >= 5:
                signal = "📉 看跌大单"
            elif vol_oi >= 3:
                signal = "⚠️ 异常活跃"
            else:
                signal = "📊 偏活跃"

            # 异常度评分 (基于 vol/oi 和绝对成交量)
            score = min(100, int(vol_oi * 10 + min(vol / 100, 50)))

            unusual.append(UnusualOption(
                symbol=symbol,
                expiry=expiry,
                strike=strike,
                opt_type=opt_type,
                volume=vol,
                open_interest=oi,
                vol_oi_ratio=round(vol_oi, 2),
                implied_vol=round(iv * 100 if iv < 5 else iv, 2),
                delta=round(delta, 3),
                last_price=round(last, 2),
                signal=signal,
                score=score
            ))

    # 排序: 异常度最高在前
    unusual.sort(key=lambda x: x.score, reverse=True)
    unusual = unusual[:20]  # 限制条数

    # P/C Ratio
    total_vol = total_call_vol + total_put_vol
    if total_call_vol > 0:
        pc_ratio = total_put_vol / total_call_vol
    else:
        pc_ratio = 0

    if pc_ratio >= 1.5:
        pc_signal = "🔴 极端看跌"
    elif pc_ratio >= 1.0:
        pc_signal = "🟡 偏看跌"
    elif pc_ratio >= 0.7:
        pc_signal = "⚪ 中性"
    elif pc_ratio >= 0.4:
        pc_signal = "🟡 偏看涨"
    else:
        pc_signal = "🟢 极端看涨"

    # 观察
    observations = []
    if pc_ratio >= 1.5:
        observations.append(f"Put/Call Ratio={pc_ratio:.2f}，看跌情绪浓重，可能是对冲需求或看跌押注")
    elif pc_ratio <= 0.4:
        observations.append(f"Put/Call Ratio={pc_ratio:.2f}，看涨情绪极度乐观，警惕过度自满")

    call_unusual = [u for u in unusual if u.opt_type == "C" and u.score >= 50]
    put_unusual = [u for u in unusual if u.opt_type == "P" and u.score >= 50]

    if len(call_unusual) > len(put_unusual) * 2:
        observations.append(f"看涨异常活动显著多于看跌（{len(call_unusual)} vs {len(put_unusual)}），机构可能在布局上行")
    elif len(put_unusual) > len(call_unusual) * 2:
        observations.append(f"看跌异常活动显著多于看涨（{len(put_unusual)} vs {len(call_unusual)}），注意下行风险或对冲需求")

    # 大额合约提示
    for u in unusual[:3]:
        if u.score >= 70:
            type_cn = "看涨" if u.opt_type == "C" else "看跌"
            observations.append(f"🔥 高度异常: {u.expiry} ${u.strike} {type_cn}，"
                              f"成交量/OI={u.vol_oi_ratio:.1f}x，成交={u.volume:,}")

    return OptionsFlowReport(
        symbol=symbol,
        current_price=round(current_price, 2),
        total_call_volume=total_call_vol,
        total_put_volume=total_put_vol,
        put_call_ratio=round(pc_ratio, 3),
        pc_ratio_signal=pc_signal,
        unusual_activities=unusual,
        observations=observations
    )


# ─── 格式化输出 ───────────────────────────────────────────────

def format_unusual_options(report: OptionsFlowReport) -> str:
    if not report:
        return "⚠️ 期权异常活动扫描失败"

    lines = [
        f"🔍 {report.symbol} 期权异常活动扫描  |  股价: ${report.current_price:,.2f}",
        "=" * 70,
        f"  📊 Call 成交量: {report.total_call_volume:,}  |  Put 成交量: {report.total_put_volume:,}",
        f"  📊 Put/Call Ratio: {report.put_call_ratio:.3f}  {report.pc_ratio_signal}",
        "",
    ]

    if report.unusual_activities:
        lines.append(f"  ⚡ 异常活动 Top {min(len(report.unusual_activities), 15)}:")
        lines.append(f"  {'到期':<10s} {'行权价':>8s} {'类型':>4s} {'成交量':>8s} {'OI':>8s} {'Vol/OI':>7s} {'IV%':>6s} {'评分':>4s} 信号")
        lines.append("  " + "─" * 68)

        for u in report.unusual_activities[:15]:
            t = "Call" if u.opt_type == "C" else "Put"
            lines.append(f"  {u.expiry:<10s} ${u.strike:>7.1f} {t:>4s} {u.volume:>8,} {u.open_interest:>8,} "
                        f"{u.vol_oi_ratio:>6.1f}x {u.implied_vol:>5.1f}% {u.score:>4d}  {u.signal}")
    else:
        lines.append("  ✅ 未检测到显著异常活动")

    if report.observations:
        lines.append("")
        lines.append("  💡 分析:")
        for obs in report.observations:
            lines.append(f"     {obs}")

    return "\n".join(lines)


def to_json_unusual_options(report: OptionsFlowReport) -> str:
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

    for sym in ["AAPL", "NVDA"]:
        report = scan_unusual_options(client, sym)
        if report:
            print(format_unusual_options(report))
        else:
            print(f"⚠️ {sym}: 无法获取期权数据")
        print()

    client.disconnect()


if __name__ == "__main__":
    main()
