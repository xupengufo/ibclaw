#!/usr/bin/env python3
"""
组合历史快照模块
提供：每日组合快照存档、历史净值回溯、收益率计算。
设计为通过 cron 每日运行一次存档，CLI 可随时查阅历史。

Crontab 建议（每日收盘后存档）:
30 16 * * 1-5 cd ~/trading && ./run-snapshot.sh >> ~/trading/snapshots.log 2>&1

⚠️ 纯只读操作，不包含任何交易功能。
"""

import os
import json
import glob
from datetime import datetime, timedelta
from typing import List, Optional, Dict


# ─── 配置 ─────────────────────────────────────────────────────

SNAPSHOT_DIR = os.path.join(os.path.expanduser("~"), "trading", "snapshots")


def _ensure_snapshot_dir():
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)


# ─── 快照存储 ─────────────────────────────────────────────────

def save_snapshot(client) -> str:
    """
    保存当日组合快照到 JSON 文件。
    返回保存的文件路径。
    """
    _ensure_snapshot_dir()

    today = datetime.now().strftime("%Y-%m-%d")
    filepath = os.path.join(SNAPSHOT_DIR, f"{today}.json")

    # 账户余额
    balance = client.get_balance()
    nav = balance.get("NetLiquidation", {}).get("amount", 0)
    cash = balance.get("TotalCashValue", {}).get("amount", 0)

    # 持仓明细
    positions = client.get_positions()
    holdings = []
    total_value = 0
    total_pnl = 0

    for p in positions:
        holdings.append({
            "symbol": p.symbol,
            "sec_type": p.sec_type,
            "quantity": p.quantity,
            "avg_cost": p.avg_cost,
            "market_value": p.market_value,
            "unrealized_pnl": p.unrealized_pnl,
            "pnl_percent": round(p.pnl_percent, 2),
        })
        total_value += p.market_value
        total_pnl += p.unrealized_pnl

    snapshot = {
        "date": today,
        "timestamp": datetime.now().isoformat(),
        "nav": round(nav, 2) if isinstance(nav, (int, float)) else nav,
        "cash": round(cash, 2) if isinstance(cash, (int, float)) else cash,
        "total_positions_value": round(total_value, 2),
        "total_unrealized_pnl": round(total_pnl, 2),
        "holding_count": len(holdings),
        "holdings": holdings,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"✅ 快照已保存: {filepath}")
    return filepath


def load_snapshot(date_str: str) -> Optional[Dict]:
    """加载指定日期的快照"""
    filepath = os.path.join(SNAPSHOT_DIR, f"{date_str}.json")
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def load_recent_snapshots(days: int = 30) -> List[Dict]:
    """加载最近 N 天的快照"""
    _ensure_snapshot_dir()
    files = sorted(glob.glob(os.path.join(SNAPSHOT_DIR, "*.json")))
    if not files:
        return []

    snapshots = []
    for fp in files[-days:]:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
                snapshots.append(data)
        except (json.JSONDecodeError, IOError):
            continue

    return snapshots


# ─── 收益率计算 ───────────────────────────────────────────────

def calc_snapshot_performance(snapshots: List[Dict]) -> Optional[Dict]:
    """
    从快照序列计算收益率统计。
    """
    if len(snapshots) < 2:
        return None

    # 提取 NAV 序列
    nav_series = []
    for s in snapshots:
        nav = s.get("nav")
        if isinstance(nav, (int, float)) and nav > 0:
            nav_series.append({"date": s["date"], "nav": nav})

    if len(nav_series) < 2:
        return None

    first = nav_series[0]
    last = nav_series[-1]
    total_return = (last["nav"] - first["nav"]) / first["nav"] * 100

    # 日收益率
    daily_returns = []
    for i in range(1, len(nav_series)):
        prev = nav_series[i - 1]["nav"]
        curr = nav_series[i]["nav"]
        daily_returns.append((curr - prev) / prev * 100)

    # 最大回撤
    peak = nav_series[0]["nav"]
    max_dd = 0.0
    for ns in nav_series:
        if ns["nav"] > peak:
            peak = ns["nav"]
        dd = (peak - ns["nav"]) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # 统计
    avg_daily = sum(daily_returns) / len(daily_returns) if daily_returns else 0
    best_day = max(daily_returns) if daily_returns else 0
    worst_day = min(daily_returns) if daily_returns else 0
    positive_days = sum(1 for r in daily_returns if r > 0)
    negative_days = sum(1 for r in daily_returns if r < 0)

    return {
        "period_start": first["date"],
        "period_end": last["date"],
        "trading_days": len(nav_series),
        "start_nav": first["nav"],
        "end_nav": last["nav"],
        "total_return_pct": round(total_return, 2),
        "total_return_amount": round(last["nav"] - first["nav"], 2),
        "avg_daily_return_pct": round(avg_daily, 3),
        "best_day_pct": round(best_day, 2),
        "worst_day_pct": round(worst_day, 2),
        "positive_days": positive_days,
        "negative_days": negative_days,
        "win_rate_pct": round(positive_days / len(daily_returns) * 100, 1) if daily_returns else 0,
        "max_drawdown_pct": round(max_dd, 2),
        "nav_history": [{"date": ns["date"], "nav": ns["nav"]} for ns in nav_series],
    }


# ─── 格式化输出 ───────────────────────────────────────────────

def to_json_snapshots(data) -> str:
    """JSON 输出"""
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def format_snapshot_performance(perf: Dict) -> str:
    """格式化快照收益率统计"""
    if not perf:
        return "📸 历史快照: 数据不足 (需至少 2 天的快照)"

    total_emoji = "📈" if perf["total_return_pct"] >= 0 else "📉"

    lines = [
        "📸 组合历史表现",
        "=" * 55,
        f"  期间: {perf['period_start']} → {perf['period_end']} ({perf['trading_days']}个交易日)",
        f"  起始净值: ${perf['start_nav']:,.0f} → 当前净值: ${perf['end_nav']:,.0f}",
        "",
        f"  {total_emoji} 区间收益: {perf['total_return_pct']:+.2f}%  (${perf['total_return_amount']:+,.0f})",
        f"  📊 日均收益: {perf['avg_daily_return_pct']:+.3f}%",
        f"  ✅ 盈利天数: {perf['positive_days']}天  |  ❌ 亏损天数: {perf['negative_days']}天  |  胜率: {perf['win_rate_pct']:.1f}%",
        f"  🔥 最佳单日: {perf['best_day_pct']:+.2f}%  |  ❄️ 最差单日: {perf['worst_day_pct']:+.2f}%",
        f"  📉 最大回撤: {perf['max_drawdown_pct']:.2f}%",
    ]

    # 近期趋势线 (最后 10 天)
    nav_hist = perf.get("nav_history", [])
    if len(nav_hist) >= 3:
        recent = nav_hist[-min(10, len(nav_hist)):]
        lines.append("")
        lines.append("  近期走势:")
        for ns in recent:
            lines.append(f"    {ns['date']}  ${ns['nav']:>12,.0f}")

    return "\n".join(lines)


def format_snapshot_summary(snapshot: Dict) -> str:
    """格式化单日快照"""
    if not snapshot:
        return "📸 无快照数据"

    lines = [
        f"📸 组合快照 — {snapshot['date']}",
        "=" * 50,
        f"  净资产: ${snapshot.get('nav', 0):,.0f}",
        f"  现金: ${snapshot.get('cash', 0):,.0f}",
        f"  持仓市值: ${snapshot.get('total_positions_value', 0):,.0f}",
        f"  未实现盈亏: ${snapshot.get('total_unrealized_pnl', 0):+,.0f}",
        f"  持仓数: {snapshot.get('holding_count', 0)}",
    ]
    return "\n".join(lines)


# ─── 独立运行入口（cron 调用）──────────────────────────────────

def main():
    """独立运行：保存当日快照"""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ibkr_readonly import IBKRReadOnlyClient

    client = IBKRReadOnlyClient()
    if not client.connect():
        print("❌ 无法连接 IB Gateway")
        return

    try:
        save_snapshot(client)
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
