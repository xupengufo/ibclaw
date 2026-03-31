#!/usr/bin/env python3
"""
技术分析指标模块
提供：SMA、EMA、RSI、MACD、布林带、支撑/阻力位、成交量分析、综合技术评估。
所有函数基于 IBKRReadOnlyClient 获取的历史 K 线数据，纯只读操作。
"""

import math
import json
import dataclasses
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple


# ─── 数据类 ───────────────────────────────────────────────────

@dataclass
class MovingAverages:
    """均线系统"""
    sma_5: Optional[float] = None
    sma_10: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_120: Optional[float] = None   # 半年线
    sma_250: Optional[float] = None   # 年线
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None
    trend: str = ""                    # "多头排列" / "空头排列" / "缠绕"


@dataclass
class RSIData:
    """RSI 指标"""
    rsi_14: float = 0.0
    signal: str = ""     # "超买" / "超卖" / "中性"
    divergence: str = "" # "顶背离" / "底背离" / ""


@dataclass
class MACDData:
    """MACD 指标"""
    macd_line: float = 0.0     # DIF
    signal_line: float = 0.0   # DEA
    histogram: float = 0.0     # MACD 柱
    cross_signal: str = ""     # "金叉" / "死叉" / ""


@dataclass
class BollingerBands:
    """布林带"""
    upper: float = 0.0
    middle: float = 0.0
    lower: float = 0.0
    bandwidth_pct: float = 0.0    # 带宽百分比
    position: str = ""            # "上轨之上" / "上轨附近" / "中轨附近" / "下轨附近" / "下轨之下"


@dataclass
class SupportResistance:
    """支撑与阻力"""
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)
    current_price: float = 0.0


@dataclass
class VolumeAnalysis:
    """成交量分析"""
    current_volume: int = 0
    avg_volume_10d: float = 0.0
    avg_volume_20d: float = 0.0
    volume_ratio: float = 0.0       # 量比 (当日 / 10日均量)
    volume_trend: str = ""           # "放量" / "缩量" / "持平"


@dataclass
class TechnicalSummary:
    """综合技术分析"""
    symbol: str
    current_price: float
    ma: MovingAverages
    rsi: RSIData
    macd: MACDData
    bollinger: BollingerBands
    support_resistance: SupportResistance
    volume: VolumeAnalysis
    overall_signal: str = ""    # "强烈看多" / "看多" / "中性" / "看空" / "强烈看空"
    score: int = 0              # -100 ~ +100 综合评分
    key_observations: List[str] = field(default_factory=list)


# ─── 核心计算函数 ─────────────────────────────────────────────

def _sma(prices: List[float], period: int) -> Optional[float]:
    """简单移动平均"""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def _ema(prices: List[float], period: int) -> Optional[float]:
    """指数移动平均"""
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period  # 初始值用 SMA
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def _ema_series(prices: List[float], period: int) -> List[float]:
    """计算完整的 EMA 序列"""
    if len(prices) < period:
        return []
    multiplier = 2 / (period + 1)
    ema_vals = [sum(prices[:period]) / period]
    for price in prices[period:]:
        ema_vals.append((price - ema_vals[-1]) * multiplier + ema_vals[-1])
    return ema_vals


def calc_moving_averages(closes: List[float]) -> MovingAverages:
    """计算均线系统"""
    ma = MovingAverages(
        sma_5=_sma(closes, 5),
        sma_10=_sma(closes, 10),
        sma_20=_sma(closes, 20),
        sma_50=_sma(closes, 50),
        sma_120=_sma(closes, 120),
        sma_250=_sma(closes, 250),
        ema_12=_ema(closes, 12),
        ema_26=_ema(closes, 26),
    )

    # 判断多空排列
    short_mas = [v for v in [ma.sma_5, ma.sma_10, ma.sma_20] if v is not None]
    if len(short_mas) >= 3:
        if short_mas[0] > short_mas[1] > short_mas[2]:
            ma.trend = "📈 多头排列"
        elif short_mas[0] < short_mas[1] < short_mas[2]:
            ma.trend = "📉 空头排列"
        else:
            ma.trend = "🔄 均线缠绕"

    return ma


def calc_rsi(closes: List[float], period: int = 14) -> RSIData:
    """计算 RSI"""
    if len(closes) < period + 1:
        return RSIData()

    gains = []
    losses = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    # Wilder's smoothing
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        rsi_value = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_value = 100 - (100 / (1 + rs))

    # 信号判断
    if rsi_value >= 70:
        signal = "🔴 超买"
    elif rsi_value <= 30:
        signal = "🟢 超卖"
    elif rsi_value >= 60:
        signal = "🟡 偏强"
    elif rsi_value <= 40:
        signal = "🟡 偏弱"
    else:
        signal = "⚪ 中性"

    return RSIData(
        rsi_14=round(rsi_value, 2),
        signal=signal
    )


def calc_macd(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> MACDData:
    """计算 MACD"""
    if len(closes) < slow + signal:
        return MACDData()

    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)

    # 对齐长度
    offset = slow - fast
    dif_series = []
    for i in range(len(ema_slow)):
        dif_series.append(ema_fast[i + offset] - ema_slow[i])

    if len(dif_series) < signal:
        return MACDData()

    # DEA = DIF 的 EMA
    dea_series = _ema_series(dif_series, signal)
    offset2 = len(dif_series) - len(dea_series)

    dif = dif_series[-1]
    dea = dea_series[-1]
    histogram = 2 * (dif - dea)  # MACD 柱 (×2 是国内标准)

    # 金叉/死叉判断
    cross = ""
    if len(dea_series) >= 2 and len(dif_series) >= 2:
        prev_dif = dif_series[-2]
        prev_dea = dea_series[-2]
        if prev_dif <= prev_dea and dif > dea:
            cross = "🟢 金叉"
        elif prev_dif >= prev_dea and dif < dea:
            cross = "🔴 死叉"

    return MACDData(
        macd_line=round(dif, 4),
        signal_line=round(dea, 4),
        histogram=round(histogram, 4),
        cross_signal=cross
    )


def calc_bollinger_bands(closes: List[float], period: int = 20, std_dev: float = 2.0) -> BollingerBands:
    """计算布林带"""
    if len(closes) < period:
        return BollingerBands()

    recent = closes[-period:]
    middle = sum(recent) / period

    variance = sum((x - middle) ** 2 for x in recent) / period
    std = math.sqrt(variance)

    upper = middle + std_dev * std
    lower = middle - std_dev * std
    bandwidth = (upper - lower) / middle * 100 if middle else 0

    current = closes[-1]
    if current > upper:
        pos = "🔴 上轨之上 (超买)"
    elif current > middle + (upper - middle) * 0.7:
        pos = "🟡 上轨附近"
    elif current < lower:
        pos = "🟢 下轨之下 (超卖)"
    elif current < middle - (middle - lower) * 0.7:
        pos = "🟡 下轨附近"
    else:
        pos = "⚪ 中轨附近"

    return BollingerBands(
        upper=round(upper, 2),
        middle=round(middle, 2),
        lower=round(lower, 2),
        bandwidth_pct=round(bandwidth, 2),
        position=pos
    )


def calc_support_resistance(bars: List[dict], levels: int = 3) -> SupportResistance:
    """
    计算支撑与阻力位
    基于近期的高低点聚类
    """
    if not bars:
        return SupportResistance()

    current = bars[-1]["close"]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]

    # 寻找局部高点/低点
    local_highs = []
    local_lows = []
    window = 5

    for i in range(window, len(bars) - window):
        h = bars[i]["high"]
        if all(h >= bars[j]["high"] for j in range(i - window, i + window + 1) if j != i):
            local_highs.append(h)

        l = bars[i]["low"]
        if all(l <= bars[j]["low"] for j in range(i - window, i + window + 1) if j != i):
            local_lows.append(l)

    # 聚类合并相近的价位 (误差 1.5%)
    def cluster(prices, threshold_pct=1.5):
        if not prices:
            return []
        prices = sorted(set(prices))
        clusters = [[prices[0]]]
        for p in prices[1:]:
            if (p - clusters[-1][-1]) / clusters[-1][-1] * 100 < threshold_pct:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        return [round(sum(c) / len(c), 2) for c in clusters]

    resistance = sorted([p for p in cluster(local_highs) if p > current], reverse=False)[:levels]
    support = sorted([p for p in cluster(local_lows) if p < current], reverse=True)[:levels]

    return SupportResistance(
        support_levels=support,
        resistance_levels=resistance,
        current_price=current
    )


def calc_volume_analysis(bars: List[dict]) -> VolumeAnalysis:
    """成交量分析"""
    if not bars:
        return VolumeAnalysis()

    volumes = [b["volume"] for b in bars]
    current_vol = volumes[-1] if volumes else 0

    avg_10 = sum(volumes[-10:]) / min(10, len(volumes)) if volumes else 0
    avg_20 = sum(volumes[-20:]) / min(20, len(volumes)) if volumes else 0
    ratio = current_vol / avg_10 if avg_10 > 0 else 0

    if ratio >= 2.0:
        trend = "🔴 显著放量"
    elif ratio >= 1.3:
        trend = "🟡 温和放量"
    elif ratio <= 0.5:
        trend = "🔵 显著缩量"
    elif ratio <= 0.7:
        trend = "🟡 温和缩量"
    else:
        trend = "⚪ 成交持平"

    return VolumeAnalysis(
        current_volume=current_vol,
        avg_volume_10d=round(avg_10, 0),
        avg_volume_20d=round(avg_20, 0),
        volume_ratio=round(ratio, 2),
        volume_trend=trend
    )


# ─── 综合分析 ─────────────────────────────────────────────────

def calc_technical_score(ma: MovingAverages, rsi: RSIData, macd: MACDData,
                         bb: BollingerBands, vol: VolumeAnalysis, current: float) -> Tuple[int, str, List[str]]:
    """
    综合评分: -100 (强烈看空) ~ +100 (强烈看多)
    返回: (score, signal_text, key_observations)
    """
    score = 0
    observations = []

    # 1. 均线评分 (±30)
    if ma.sma_5 and ma.sma_20:
        if current > ma.sma_5 > ma.sma_20:
            score += 30
            observations.append("价格站上短期均线，多头排列")
        elif current < ma.sma_5 < ma.sma_20:
            score -= 30
            observations.append("价格跌破短期均线，空头排列")
        elif current > ma.sma_20:
            score += 10
            observations.append("价格位于20日均线之上")
        else:
            score -= 10
            observations.append("价格位于20日均线之下")

    # 长期趋势
    if ma.sma_50 and current > ma.sma_50:
        score += 5
    elif ma.sma_50:
        score -= 5

    # 2. RSI 评分 (±25)
    if rsi.rsi_14 >= 80:
        score -= 25
        observations.append(f"RSI={rsi.rsi_14:.0f}，严重超买，回调风险高")
    elif rsi.rsi_14 >= 70:
        score -= 15
        observations.append(f"RSI={rsi.rsi_14:.0f}，进入超买区域")
    elif rsi.rsi_14 <= 20:
        score += 25
        observations.append(f"RSI={rsi.rsi_14:.0f}，严重超卖，反弹概率高")
    elif rsi.rsi_14 <= 30:
        score += 15
        observations.append(f"RSI={rsi.rsi_14:.0f}，进入超卖区域")
    elif 45 <= rsi.rsi_14 <= 55:
        observations.append(f"RSI={rsi.rsi_14:.0f}，中性")

    # 3. MACD 评分 (±25)
    if macd.cross_signal == "🟢 金叉":
        score += 25
        observations.append("MACD 金叉，看多信号")
    elif macd.cross_signal == "🔴 死叉":
        score -= 25
        observations.append("MACD 死叉，看空信号")
    elif macd.histogram > 0:
        score += 10
    else:
        score -= 10

    # 4. 布林带评分 (±15)
    if "超买" in bb.position:
        score -= 15
        observations.append("价格突破布林带上轨，短期超买")
    elif "超卖" in bb.position:
        score += 15
        observations.append("价格跌破布林带下轨，短期超卖")
    elif "上轨" in bb.position:
        score -= 5
    elif "下轨" in bb.position:
        score += 5

    # 5. 量能确认 (±5)
    if vol.volume_ratio >= 1.5 and score > 0:
        score += 5
        observations.append(f"量比 {vol.volume_ratio:.1f}x，放量上涨，多方动能充足")
    elif vol.volume_ratio >= 1.5 and score < 0:
        score -= 5
        observations.append(f"量比 {vol.volume_ratio:.1f}x，放量下跌，空方压力显著")

    # 限制范围
    score = max(-100, min(100, score))

    # 信号文字
    if score >= 60:
        signal = "🟢 强烈看多"
    elif score >= 30:
        signal = "🟢 看多"
    elif score >= 10:
        signal = "🟡 偏多"
    elif score <= -60:
        signal = "🔴 强烈看空"
    elif score <= -30:
        signal = "🔴 看空"
    elif score <= -10:
        signal = "🟡 偏空"
    else:
        signal = "⚪ 中性"

    return score, signal, observations


def analyze_symbol(client, symbol: str, period: str = "1 Y", bar_size: str = "1 day") -> Optional[TechnicalSummary]:
    """
    对单只股票执行完整技术分析
    """
    bars = client.get_historical_data(symbol, duration=period, bar_size=bar_size)
    if not bars or len(bars) < 30:
        return None

    closes = [b["close"] for b in bars]
    current = closes[-1]

    ma = calc_moving_averages(closes)
    rsi = calc_rsi(closes)
    macd = calc_macd(closes)
    bb = calc_bollinger_bands(closes)
    sr = calc_support_resistance(bars)
    vol = calc_volume_analysis(bars)

    score, signal, observations = calc_technical_score(ma, rsi, macd, bb, vol, current)

    return TechnicalSummary(
        symbol=symbol,
        current_price=current,
        ma=ma,
        rsi=rsi,
        macd=macd,
        bollinger=bb,
        support_resistance=sr,
        volume=vol,
        overall_signal=signal,
        score=score,
        key_observations=observations
    )


def analyze_portfolio(client) -> List[TechnicalSummary]:
    """对所有股票持仓执行技术分析，返回成功的分析结果列表"""
    positions = client.get_positions()
    stock_positions = [p for p in positions if p.sec_type == "STK"]

    if not stock_positions:
        print("ℹ️ 无股票持仓，跳过组合技术分析")
        return []

    results = []
    failed = []
    for p in stock_positions:
        try:
            summary = analyze_symbol(client, p.symbol, "1 Y", "1 day")
            if summary:
                results.append(summary)
            else:
                failed.append((p.symbol, "历史数据不足（至少需要 30 根 K 线）"))
        except Exception as e:
            failed.append((p.symbol, f"{type(e).__name__}: {e}"))

    if failed:
        print(f"⚠️ {len(failed)}/{len(stock_positions)} 只股票技术分析失败:")
        for symbol, reason in failed:
            print(f"   • {symbol}: {reason}")

    results.sort(key=lambda x: x.score, reverse=True)
    return results


# ─── 格式化输出 ───────────────────────────────────────────────

def _fmt_price(val: Optional[float]) -> str:
    return f"${val:,.2f}" if val is not None else "N/A"


def format_technical_summary(ts: TechnicalSummary) -> str:
    """格式化单只股票的完整技术分析"""
    lines = [
        f"📊 {ts.symbol} 技术分析  |  当前价: ${ts.current_price:,.2f}",
        f"{'=' * 60}",
        f"  🎯 综合评分: {ts.score:+d}/100  {ts.overall_signal}",
        "",
    ]

    # 关键发现
    if ts.key_observations:
        lines.append("  💡 关键发现:")
        for obs in ts.key_observations:
            lines.append(f"     • {obs}")
        lines.append("")

    # 均线
    lines.append(f"  📈 均线系统  {ts.ma.trend}")
    ma_items = [
        ("MA5", ts.ma.sma_5), ("MA10", ts.ma.sma_10), ("MA20", ts.ma.sma_20),
        ("MA50", ts.ma.sma_50), ("MA120", ts.ma.sma_120), ("MA250", ts.ma.sma_250)
    ]
    ma_line = "     "
    for label, val in ma_items:
        if val is not None:
            above = "▲" if ts.current_price > val else "▼"
            ma_line += f"{label}={_fmt_price(val)}{above}  "
    lines.append(ma_line)
    lines.append("")

    # RSI
    lines.append(f"  📉 RSI(14): {ts.rsi.rsi_14:.1f}  {ts.rsi.signal}")

    # MACD
    cross_text = f"  {ts.macd.cross_signal}" if ts.macd.cross_signal else ""
    lines.append(f"  📊 MACD: DIF={ts.macd.macd_line:.4f}  DEA={ts.macd.signal_line:.4f}  "
                 f"柱={ts.macd.histogram:+.4f}{cross_text}")

    # 布林带
    lines.append(f"  📏 布林带: 上轨={_fmt_price(ts.bollinger.upper)}  "
                 f"中轨={_fmt_price(ts.bollinger.middle)}  "
                 f"下轨={_fmt_price(ts.bollinger.lower)}  "
                 f"带宽={ts.bollinger.bandwidth_pct:.1f}%")
    lines.append(f"     位置: {ts.bollinger.position}")

    # 成交量
    lines.append(f"  📦 成交量: 今日={ts.volume.current_volume:,}  "
                 f"10日均量={ts.volume.avg_volume_10d:,.0f}  "
                 f"量比={ts.volume.volume_ratio:.2f}x  {ts.volume.volume_trend}")

    # 支撑阻力
    sr = ts.support_resistance
    if sr.resistance_levels:
        lines.append(f"  🔺 阻力位: {', '.join(_fmt_price(p) for p in sr.resistance_levels)}")
    if sr.support_levels:
        lines.append(f"  🔻 支撑位: {', '.join(_fmt_price(p) for p in sr.support_levels)}")

    return "\n".join(lines)


def format_portfolio_technical(summaries: List[TechnicalSummary]) -> str:
    """格式化组合技术分析概览"""
    if not summaries:
        return "📊 组合技术分析: 无股票持仓"

    lines = [
        "📊 持仓技术分析一览",
        "=" * 70,
        f"{'标的':8s} {'评分':>6s}  {'信号':10s} {'RSI':>6s}  {'MACD':8s}  {'均线趋势':12s}  {'量能':8s}",
        "-" * 70,
    ]

    for ts in summaries:
        macd_text = ts.macd.cross_signal if ts.macd.cross_signal else ("多" if ts.macd.histogram > 0 else "空")
        lines.append(
            f"  {ts.symbol:8s} {ts.score:>+4d}    {ts.overall_signal:10s} "
            f"{ts.rsi.rsi_14:>5.1f}   {macd_text:8s}  "
            f"{ts.ma.trend:12s}  {ts.volume.volume_trend}"
        )

    # 统计
    bullish = sum(1 for s in summaries if s.score > 10)
    bearish = sum(1 for s in summaries if s.score < -10)
    neutral = len(summaries) - bullish - bearish
    avg_score = sum(s.score for s in summaries) / len(summaries) if summaries else 0

    lines.append("")
    lines.append(f"  📌 组合平均评分: {avg_score:+.1f}  |  看多 {bullish} / 中性 {neutral} / 看空 {bearish}")

    return "\n".join(lines)


def to_json_summary(ts: TechnicalSummary) -> str:
    """输出纯净的 JSON 数据格式，供 AI 分析使用（剔除主观判定文本）"""
    data = dataclasses.asdict(ts)
    
    # 剔除或简化一些强主观的预测性字段（在 JSON 模式下，这些推导应由 AI 完成）
    data.pop('overall_signal', None)
    data.pop('key_observations', None)
    data.pop('score', None)
    data['ma'].pop('trend', None)
    data['rsi'].pop('signal', None)
    data['macd'].pop('cross_signal', None)
    data['bollinger'].pop('position', None)
    data['volume'].pop('volume_trend', None)
    
    return json.dumps(data, ensure_ascii=False, indent=2)


def format_portfolio_json(summaries: List[TechnicalSummary]) -> str:
    """输出 JSON 格式的组合概览"""
    data = []
    for ts in summaries:
        item = dataclasses.asdict(ts)
        # 精简 JSON
        item.pop('overall_signal', None)
        item.pop('key_observations', None)
        item.pop('score', None)
        item['ma'].pop('trend', None)
        item['rsi'].pop('signal', None)
        item['macd'].pop('cross_signal', None)
        item['bollinger'].pop('position', None)
        item['volume'].pop('volume_trend', None)
        data.append(item)
    return json.dumps(data, ensure_ascii=False, indent=2)



# ─── 独立运行入口 ─────────────────────────────────────────────

def main():
    """独立运行：技术分析演示"""
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ibkr_readonly import IBKRReadOnlyClient, util

    util.patchAsyncio()
    client = IBKRReadOnlyClient()

    if not client.connect():
        print("❌ 无法连接 IB Gateway")
        return

    print("📊 技术分析报告")
    print("=" * 60)

    # 1. 单个股票详细分析
    test_symbol = "AAPL"
    print(f"\n⏳ 正在分析 {test_symbol}...")
    summary = analyze_symbol(client, test_symbol)
    if summary:
        print(format_technical_summary(summary))
    else:
        print(f"⚠️ {test_symbol} 分析失败")

    # 2. 组合概览
    print(f"\n{'=' * 60}")
    print("⏳ 正在分析全部持仓...")
    portfolio_ta = analyze_portfolio(client)
    if portfolio_ta:
        print(format_portfolio_technical(portfolio_ta))
        # 打印评分最高/最低的详细分析
        print(f"\n{'=' * 60}")
        print(f"🏆 最强持仓详细分析：")
        print(format_technical_summary(portfolio_ta[0]))
        if len(portfolio_ta) > 1 and portfolio_ta[-1].score < 0:
            print(f"\n{'=' * 60}")
            print(f"⚠️ 最弱持仓详细分析：")
            print(format_technical_summary(portfolio_ta[-1]))
    else:
        print("ℹ️ 无股票持仓")

    client.disconnect()
    print("\n✅ 技术分析完成")


if __name__ == "__main__":
    main()
