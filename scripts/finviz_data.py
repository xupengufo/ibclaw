#!/usr/bin/env python3
"""
Finviz 数据模块
从 finviz.com 获取补充数据：基本面、分析师评级、内部人交易、同行公司、新闻。
所有函数均为独立 try/except，失败返回空值，不影响 IBKR 核心功能。

⚠️ 数据来源为 HTML 爬虫，Finviz 网站改版可能导致功能失效。
"""

import time
from typing import List, Dict, Optional


# ─── 基本面 ──────────────────────────────────────────────────

def get_finviz_fundamentals(symbol: str) -> Dict[str, str]:
    """
    获取 Finviz 60+ 字段基本面数据。
    返回 dict，key 为英文字段名，value 为字符串。
    失败返回空 dict。
    """
    try:
        from finvizfinance.quote import finvizfinance
        stock = finvizfinance(symbol.upper(), verbose=0)
        if not stock.flag:
            return {}
        data = stock.ticker_fundament(raw=True, output_format="dict")
        return data if data else {}
    except Exception as e:
        print(f"⚠️ Finviz 基本面获取失败 ({symbol}): {e}")
        return {}

def get_finviz_fundamentals_batch(symbols: List[str], max_workers: int = 5) -> Dict[str, Dict[str, str]]:
    """并发批量获取多只股票的基本面，极大提升效率"""
    import concurrent.futures
    results = {}
    
    if not symbols:
        return results

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_symbol = {executor.submit(get_finviz_fundamentals, sym): sym for sym in symbols}
        for future in concurrent.futures.as_completed(future_to_symbol):
            sym = future_to_symbol[future]
            try:
                data = future.result()
                results[sym] = data
            except Exception as e:
                print(f"⚠️ {sym} 并发查 Finviz 基本面失败: {e}")
                results[sym] = {}
                
    return results



def format_finviz_fundamentals(data: Dict[str, str], symbol: str) -> str:
    """格式化 Finviz 基本面数据"""
    if not data:
        return f"⚠️ {symbol}: Finviz 基本面数据不可用"

    # 精选最有价值的字段分组展示
    sections = {
        "📊 估值指标": [
            ("P/E", "市盈率 (TTM)"), ("Forward P/E", "前瞻市盈率"),
            ("PEG", "PEG"), ("P/S", "市销率"), ("P/B", "市净率"),
            ("P/C", "市现率"), ("P/FCF", "自由现金流倍数"),
        ],
        "💰 盈利与成长": [
            ("EPS (ttm)", "EPS (TTM)"), ("EPS next Y", "EPS 预期下年"),
            ("EPS next 5Y", "EPS 5年增速"), ("Sales past 5Y", "营收5年增速"),
            ("EPS Q/Q", "EPS 季度环比"), ("Sales Q/Q", "营收季度环比"),
        ],
        "📈 利润率与回报": [
            ("Gross Margin", "毛利率"), ("Oper. Margin", "营业利润率"),
            ("Profit Margin", "净利率"), ("ROA", "资产回报率"),
            ("ROE", "净资产回报率"), ("ROI", "投资回报率"),
        ],
        "🏦 财务健康": [
            ("Current Ratio", "流动比率"), ("Quick Ratio", "速动比率"),
            ("LT Debt/Eq", "长期负债/权益"), ("Debt/Eq", "负债/权益"),
        ],
        "📉 交易与波动": [
            ("Beta", "Beta"), ("ATR", "ATR(14)"),
            ("Volatility", "波动率(周/月)"), ("RSI (14)", "RSI(14)"),
            ("SMA20", "SMA20偏离"), ("SMA50", "SMA50偏离"), ("SMA200", "SMA200偏离"),
            ("52W High", "距52周高"), ("52W Low", "距52周低"),
        ],
        "🎯 分析师共识": [
            ("Target Price", "目标价"), ("Recom", "推荐评分(1买-5卖)"),
        ],
        "📦 股本与持仓": [
            ("Market Cap", "市值"), ("Shs Outstand", "总股本"),
            ("Shs Float", "流通股"), ("Insider Own", "内部人持股"),
            ("Inst Own", "机构持股"), ("Short Float", "做空比例"),
        ],
    }

    lines = [
        f"📊 {symbol} 基本面数据 (来源: Finviz)",
        "=" * 55,
        f"  公司: {data.get('Company', 'N/A')}",
        f"  行业: {data.get('Sector', 'N/A')} → {data.get('Industry', 'N/A')}",
        f"  国家: {data.get('Country', 'N/A')} | 交易所: {data.get('Exchange', 'N/A')}",
        "",
    ]

    for section_name, fields in sections.items():
        section_lines = []
        for key, label in fields:
            val = data.get(key)
            if val and val != "-" and val != "":
                section_lines.append(f"  {label:16s} {val}")
        if section_lines:
            lines.append(f"  {section_name}")
            lines.extend(section_lines)
            lines.append("")

    return "\n".join(lines)


# ─── 分析师评级 ───────────────────────────────────────────────

def get_finviz_ratings(symbol: str) -> List[Dict]:
    """
    获取分析师评级历史。
    返回 list[dict]，每个 dict 含 Date/Status/Outer/Rating/Price。
    """
    try:
        from finvizfinance.quote import finvizfinance
        stock = finvizfinance(symbol.upper(), verbose=0)
        if not stock.flag:
            return []
        df = stock.ticker_outer_ratings()
        if df is None or df.empty:
            return []
        records = df.to_dict("records")
        # 日期转字符串
        for r in records:
            if hasattr(r.get("Date"), "strftime"):
                r["Date"] = r["Date"].strftime("%Y-%m-%d")
            else:
                r["Date"] = str(r.get("Date", ""))
        return records
    except Exception as e:
        print(f"⚠️ Finviz 评级获取失败 ({symbol}): {e}")
        return []


def format_ratings(ratings: List[Dict], symbol: str) -> str:
    """格式化分析师评级"""
    if not ratings:
        return f"⚠️ {symbol}: 无分析师评级数据"

    lines = [
        f"⭐ {symbol} 分析师评级 (来源: Finviz)",
        "=" * 65,
        f"{'日期':12s} {'状态':12s} {'机构':18s} {'评级':14s} {'目标价':10s}",
    ]
    for r in ratings[:15]:
        lines.append(
            f"  {r.get('Date',''):10s} {r.get('Status',''):10s} "
            f"{r.get('Outer',''):16s} {r.get('Rating',''):12s} {r.get('Price',''):8s}"
        )
    if len(ratings) > 15:
        lines.append(f"\n  ...共 {len(ratings)} 条，仅展示前 15 条")
    return "\n".join(lines)


# ─── 内部人交易 ───────────────────────────────────────────────

def get_finviz_insider(symbol: str) -> List[Dict]:
    """
    获取个股内部人交易记录。
    返回 list[dict]。
    """
    try:
        from finvizfinance.quote import finvizfinance
        stock = finvizfinance(symbol.upper(), verbose=0)
        if not stock.flag:
            return []
        df = stock.ticker_inside_trader()
        if df is None or df.empty:
            return []
        return df.to_dict("records")
    except Exception as e:
        print(f"⚠️ Finviz 内部人交易获取失败 ({symbol}): {e}")
        return []


def get_finviz_insider_market(option: str = "latest") -> List[Dict]:
    """
    获取全市场内部人交易。
    option: latest, latest buys, latest sales, top week,
            top week buys, top week sales, top owner trade,
            top owner buys, top owner sales
    """
    try:
        from finvizfinance.insider import Insider
        finsider = Insider(option=option)
        df = finsider.get_insider()
        if df is None or df.empty:
            return []
        return df.to_dict("records")
    except Exception as e:
        print(f"⚠️ Finviz 全市场内部人数据获取失败: {e}")
        return []


def format_insider(records: List[Dict], title: str) -> str:
    """格式化内部人交易"""
    if not records:
        return f"⚠️ {title}: 无内部人交易数据"

    lines = [
        f"🕵️ {title} (来源: Finviz)",
        "=" * 80,
    ]

    for i, r in enumerate(records[:15]):
        insider_name = r.get("Insider Trading", r.get("Insider", ""))
        relationship = r.get("Relationship", "")
        date = r.get("Date", "")
        transaction = r.get("Transaction", "")
        value = r.get("Value ($)", r.get("Value", ""))
        cost = r.get("Cost", "")
        shares = r.get("#Shares", "")

        emoji = "🟢" if "Buy" in str(transaction) or "Purchase" in str(transaction) else "🔴"
        lines.append(
            f"  {emoji} {date:10s} {str(insider_name):20s} {str(transaction):12s} "
            f"${str(cost):>8s} x {str(shares):>10s} = ${str(value):>12s}"
        )
        if relationship:
            lines.append(f"     └─ {relationship}")

    if len(records) > 15:
        lines.append(f"\n  ...共 {len(records)} 条，仅展示前 15 条")
    return "\n".join(lines)


# ─── 同行公司 ────────────────────────────────────────────────

def get_finviz_peers(symbol: str) -> List[str]:
    """获取同行业竞品公司列表"""
    try:
        from finvizfinance.quote import finvizfinance
        stock = finvizfinance(symbol.upper(), verbose=0)
        if not stock.flag:
            return []
        peers = stock.ticker_peer()
        return peers if peers else []
    except Exception as e:
        print(f"⚠️ Finviz 同行公司获取失败 ({symbol}): {e}")
        return []


def format_peers(peers: List[str], symbol: str) -> str:
    """格式化同行公司"""
    if not peers:
        return f"⚠️ {symbol}: 无同行公司数据"
    return (
        f"🏢 {symbol} 同行公司 (来源: Finviz)\n"
        f"{'=' * 40}\n"
        f"  {', '.join(peers)}\n"
        f"  共 {len(peers)} 家同行业公司"
    )


# ─── 新闻 ────────────────────────────────────────────────────

def get_finviz_news(symbol: str) -> List[Dict]:
    """获取个股新闻"""
    try:
        from finvizfinance.quote import finvizfinance
        stock = finvizfinance(symbol.upper(), verbose=0)
        if not stock.flag:
            return []
        df = stock.ticker_news()
        if df is None or df.empty:
            return []
        records = df.to_dict("records")
        # 标准化日期字段
        for r in records:
            if hasattr(r.get("Date"), "strftime"):
                r["Date"] = r["Date"].strftime("%Y-%m-%d %H:%M")
            else:
                r["Date"] = str(r.get("Date", ""))
        return records
    except Exception as e:
        print(f"⚠️ Finviz 新闻获取失败 ({symbol}): {e}")
        return []


def get_finviz_market_news() -> Dict[str, List[Dict]]:
    """
    获取全市场新闻。
    返回 {'news': [...], 'blogs': [...]}
    """
    try:
        from finvizfinance.news import News
        fnews = News()
        all_news = fnews.get_news()
        result = {}
        for key in ("news", "blogs"):
            df = all_news.get(key)
            if df is not None and not df.empty:
                result[key] = df.to_dict("records")
            else:
                result[key] = []
        return result
    except Exception as e:
        print(f"⚠️ Finviz 市场新闻获取失败: {e}")
        return {"news": [], "blogs": []}


def format_news(records: List[Dict], title: str, limit: int = 15) -> str:
    """格式化新闻"""
    if not records:
        return f"⚠️ {title}: 无新闻数据"

    lines = [
        f"📰 {title} (来源: Finviz)",
        "=" * 65,
    ]
    for i, r in enumerate(records[:limit]):
        date = r.get("Date", "")
        news_title = r.get("Title", "")
        source = r.get("Source", "")
        link = r.get("Link", "")
        lines.append(f"  {i+1:2d}. [{date}] {news_title}")
        if source:
            lines.append(f"      来源: {source}")
        if link:
            lines.append(f"      🔗 {link}")
    if len(records) > limit:
        lines.append(f"\n  ...共 {len(records)} 条，仅展示前 {limit} 条")
    return "\n".join(lines)


# ─── 独立运行入口 ─────────────────────────────────────────────

def main():
    """独立运行：测试各数据源"""
    symbol = "AAPL"
    print(f"🧪 Finviz 数据模块测试 ({symbol})")
    print("=" * 60)

    print("\n1. 基本面...")
    fund = get_finviz_fundamentals(symbol)
    if fund:
        print(f"   ✅ 获取到 {len(fund)} 个字段")
        print(f"   P/E={fund.get('P/E')}, Market Cap={fund.get('Market Cap')}")
    else:
        print("   ❌ 失败")

    time.sleep(0.5)

    print("\n2. 分析师评级...")
    ratings = get_finviz_ratings(symbol)
    print(f"   ✅ {len(ratings)} 条评级" if ratings else "   ❌ 失败")

    time.sleep(0.5)

    print("\n3. 内部人交易...")
    insider = get_finviz_insider(symbol)
    print(f"   ✅ {len(insider)} 条记录" if insider else "   ❌ 失败")

    time.sleep(0.5)

    print("\n4. 同行公司...")
    peers = get_finviz_peers(symbol)
    print(f"   ✅ {peers}" if peers else "   ❌ 失败")

    time.sleep(0.5)

    print("\n5. 个股新闻...")
    news = get_finviz_news(symbol)
    print(f"   ✅ {len(news)} 条新闻" if news else "   ❌ 失败")

    print("\n✅ 测试完成")


if __name__ == "__main__":
    main()
