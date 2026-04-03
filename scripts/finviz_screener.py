#!/usr/bin/env python3
"""
Finviz 多维条件选股模块
利用 finvizfinance Screener 实现行业+估值+技术面+信号 任意组合的服务端过滤。
弥补 IBKR Scanner 只能单维排名的不足。

用法:
    run_finviz_screen({'Sector': 'Technology', 'P/E': 'Under 20'}, signal='Oversold', limit=20)
"""

import json
from typing import Dict, List, Optional


# ─── 常用过滤维度快捷映射 ──────────────────────────────────────
# CLI 参数 → Finviz filter_dict key
# 完整列表见 finvizfinance.constants.filter_dict
CLI_FILTER_MAP = {
    "--sector":      "Sector",
    "--industry":    "Industry",
    "--country":     "Country",
    "--cap":         "Market Cap.",
    "--pe":          "P/E",
    "--fpe":         "Forward P/E",
    "--peg":         "PEG",
    "--ps":          "P/S",
    "--pb":          "P/B",
    "--dividend":    "Dividend Yield",
    "--rsi":         "RSI (14)",
    "--beta":        "Beta",
    "--price":       "Price",
    "--change":      "Change",
    "--volume":      "Average Volume",
    "--exchange":    "Exchange",
    "--index":       "Index",
    "--eps-growth":  "EPS growththis year",
    "--sales-growth": "Sales growthpast 5 years",
    "--float-short": "Float Short",
    "--analyst":     "Analyst Recom.",
    "--earnings":    "Earnings Date",
}

# 可用信号列表
AVAILABLE_SIGNALS = [
    "Top Gainers", "Top Losers", "New High", "New Low",
    "Most Volatile", "Most Active", "Unusual Volume",
    "Overbought", "Oversold", "Downgrades", "Upgrades",
    "Earnings Before", "Earnings After",
    "Recent Insider Buying", "Recent Insider Selling", "Major News",
    "Horizontal S/R", "TL Resistance", "TL Support",
    "Wedge Up", "Wedge Down", "Triangle Ascending", "Triangle Descending",
    "Channel Up", "Channel Down", "Double Top", "Double Bottom",
    "Multiple Top", "Multiple Bottom",
    "Head & Shoulders", "Head & Shoulders Inverse",
]


def list_available_filters() -> Dict[str, str]:
    """列出 CLI 可用的过滤参数"""
    return {k: v for k, v in CLI_FILTER_MAP.items()}


def list_available_signals() -> List[str]:
    """列出可用的信号"""
    return AVAILABLE_SIGNALS.copy()


def _get_filter_options(filter_name: str) -> List[str]:
    """获取某个过滤维度的可选值"""
    try:
        from finvizfinance.constants import filter_dict
        if filter_name in filter_dict:
            return list(filter_dict[filter_name]["option"].keys())
    except Exception:
        pass
    return []


def run_finviz_screen(
    filters: Optional[Dict[str, str]] = None,
    signal: str = "",
    order: str = "Ticker",
    limit: int = 20,
    ascend: bool = True,
) -> List[Dict]:
    """
    多维条件选股。

    Args:
        filters: 过滤条件 dict，如 {'Sector': 'Technology', 'P/E': 'Under 20'}
        signal: 交易信号，如 'Top Gainers', 'Oversold'
        order: 排序字段
        limit: 最大返回数量
        ascend: 升序

    Returns:
        list[dict]，每个 dict 含 Ticker, Company, Sector, Industry, Market Cap, P/E, Price, Change, Volume 等
    """
    try:
        from finvizfinance.screener.overview import Overview

        foverview = Overview()
        foverview.set_filter(
            signal=signal,
            filters_dict=filters or {},
        )
        df = foverview.screener_view(
            order=order,
            limit=limit,
            verbose=0,
            ascend=ascend,
            sleep_sec=0.5,
        )

        if df is None or df.empty:
            return []

        return df.to_dict("records")

    except Exception as e:
        print(f"❌ Finviz 选股失败: {e}")
        return []


def parse_screen_args(args: list) -> tuple:
    """
    解析 CLI 参数为 (filters_dict, signal, limit, json_output)

    示例:
        screen --sector Technology --pe "Under 20" --signal Oversold --size 10 --json
    """
    filters = {}
    signal = ""
    limit = 20
    json_output = False

    i = 0
    while i < len(args):
        if args[i] == "--json":
            json_output = True
            i += 1
        elif args[i] == "--signal" and i + 1 < len(args):
            signal = args[i + 1]
            i += 2
        elif args[i] == "--size" and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
        elif args[i] == "list":
            # 列出可用过滤器和信号
            return None, None, None, None  # 特殊标记
        elif args[i] in CLI_FILTER_MAP and i + 1 < len(args):
            finviz_key = CLI_FILTER_MAP[args[i]]
            filters[finviz_key] = args[i + 1]
            i += 2
        else:
            i += 1

    return filters, signal, limit, json_output


def format_screen_results(results: List[Dict], filters: Dict, signal: str) -> str:
    """格式化选股结果"""
    if not results:
        filter_desc = ", ".join(f"{k}={v}" for k, v in (filters or {}).items())
        if signal:
            filter_desc += f", Signal={signal}"
        return f"📡 Finviz 选股: 无结果 (条件: {filter_desc or '无'})"

    # 构建筛选条件说明
    filter_parts = []
    if filters:
        filter_parts.extend(f"{k}={v}" for k, v in filters.items())
    if signal:
        filter_parts.append(f"Signal={signal}")
    condition_text = " | ".join(filter_parts) if filter_parts else "默认"

    lines = [
        f"📡 Finviz 多维选股结果 (条件: {condition_text})",
        "=" * 75,
        f"{'#':3s} {'Ticker':8s} {'公司':22s} {'行业':16s} {'市值':>10s} {'P/E':>8s} {'价格':>10s} {'涨跌':>8s}",
    ]

    for i, r in enumerate(results, 1):
        ticker = str(r.get("Ticker", ""))
        company = str(r.get("Company", ""))[:20]
        industry = str(r.get("Industry", ""))[:14]
        market_cap = str(r.get("Market Cap", ""))
        pe = str(r.get("P/E", ""))
        price = r.get("Price", 0)
        change = r.get("Change", 0)

        price_str = f"${price:,.2f}" if isinstance(price, (int, float)) else str(price)
        change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else str(change)

        lines.append(
            f"{i:3d} {ticker:8s} {company:22s} {industry:16s} "
            f"{market_cap:>10s} {pe:>8s} {price_str:>10s} {change_str:>8s}"
        )

    lines.append(f"\n  共 {len(results)} 只股票")
    return "\n".join(lines)


def to_json_screen_results(results: List[Dict]) -> str:
    """JSON 输出"""
    return json.dumps(results, ensure_ascii=False, indent=2, default=str)


# ─── 独立运行入口 ─────────────────────────────────────────────

def main():
    """独立测试"""
    print("🧪 Finviz 多维选股测试")
    print("=" * 60)

    print("\n1. 科技板块大盘股...")
    results = run_finviz_screen(
        filters={"Sector": "Technology", "Market Cap.": "+Large (over $10bln)"},
        limit=5
    )
    if results:
        print(format_screen_results(results, {"Sector": "Technology"}, ""))
    else:
        print("   ❌ 无结果")

    print("\n2. Top Gainers 信号...")
    results = run_finviz_screen(signal="Top Gainers", limit=5)
    if results:
        print(format_screen_results(results, {}, "Top Gainers"))
    else:
        print("   ❌ 无结果")

    print("\n✅ 测试完成")


if __name__ == "__main__":
    main()
