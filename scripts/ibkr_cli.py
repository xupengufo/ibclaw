#!/usr/bin/env python3
"""
IBKR CLI 统一入口
为 Agent 提供简洁的命令行调用接口，替代冗长的 inline Python 命令。
每个子命令自动处理连接/断开和错误上报。

用法:
    python ibkr_cli.py quote AAPL
    python ibkr_cli.py analyze AAPL
    python ibkr_cli.py fundamentals AAPL
    python ibkr_cli.py ratings AAPL
    python ibkr_cli.py insider AAPL
    python ibkr_cli.py peers AAPL
    python ibkr_cli.py screen --sector Technology --pe "Under 20" --json
    python ibkr_cli.py portfolio [allocation|concentration|beta|benchmark|attribution|drawdown|all]
    python ibkr_cli.py options [calendar|greeks|summary|all]
    python ibkr_cli.py trades [history|stats|all]
    python ibkr_cli.py scanner --code TOP_PERC_GAIN [--size 10]
    python ibkr_cli.py watchlist [list|add|remove] [SYMBOL] [--buy PRICE] [--sell PRICE] [--notes TEXT]
    python ibkr_cli.py news AAPL
    python ibkr_cli.py export [portfolio|allocation|report|all]
    python ibkr_cli.py status

⚠️ 安全模式：此脚本不包含任何下单、修改订单、取消订单的功能。
"""

import os
import sys
import traceback

# 确保能找到同目录的模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _connect_client():
    """创建并连接 IBKR 客户端，失败时输出诊断信息并退出"""
    from ibkr_readonly import IBKRReadOnlyClient

    client = IBKRReadOnlyClient()
    if not client.connect():
        print("❌ 无法连接 IB Gateway。")
        print("   诊断信息:")
        print(f"   • 目标地址: {client.host}:{client.port}")
        print(f"   • Client ID: {client.client_id}")
        print("   可能原因:")
        print("   1. IB Gateway 未启动（桌面上看不到 IB Gateway 窗口）")
        print("   2. IB Gateway 未登录（需要手机 2FA 确认）")
        print("   3. API Settings 中未启用 Socket Clients")
        print(f"   4. 端口不是 {client.port}（检查 API Settings）")
        print("   5. Trusted IPs 中未包含 127.0.0.1")
        sys.exit(1)

    return client


def _safe_disconnect(client):
    """安全断开连接"""
    try:
        client.disconnect()
    except Exception:
        pass


# ─── 子命令 ────────────────────────────────────────────────────

def cmd_status(args):
    """检查 IB Gateway 连接状态"""
    import socket
    from ibkr_readonly import IB_HOST, IB_PORT

    print("🔍 IB Gateway 连接状态检查")
    print("=" * 50)
    print(f"  目标: {IB_HOST}:{IB_PORT}")

    # 端口检查
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((IB_HOST, IB_PORT))
        sock.close()
        if result == 0:
            print("  端口: ✅ 可达")
        else:
            print("  端口: ❌ 不可达")
            print("  → IB Gateway 可能未启动或未登录")
            return
    except Exception as e:
        print(f"  端口: ❌ 检查失败 ({e})")
        return

    # 完整连接测试
    client = _connect_client()
    accounts = client.get_accounts()
    print(f"  连接: ✅ 成功")
    print(f"  账户: {', '.join(accounts) if accounts else '(未获取到)'}")
    _safe_disconnect(client)
    print("✅ IB Gateway 连接正常")


def cmd_quote(args):
    """查询实时行情"""
    json_output = "--json" in args
    symbols = [a.upper() for a in args if a != "--json"]

    client = _connect_client()
    from ibkr_readonly import format_currency

    if not symbols:
        # 获取股票持仓作为默认代码
        positions = client.get_positions()
        symbols = [p.symbol for p in positions if p.sec_type == "STK"]
        if not symbols:
            if json_output:
                import json
                print(json.dumps({"error": "未指定股票，且未找到股票持仓"}))
            else:
                print("⚠️ 未指定股票代码，且当前无股票持仓。用法: python ibkr_cli.py quote SYMBOL")
            _safe_disconnect(client)
            sys.exit(1)

    # 批量获取行情
    quotes_map = client.get_quotes_batch(symbols)

    json_results = {}
    for symbol in symbols:
        quote = quotes_map.get(symbol)
        if json_output:
            if quote:
                import dataclasses
                json_results[symbol] = dataclasses.asdict(quote)
            else:
                json_results[symbol] = {"error": "获取行情失败"}
        else:
            if quote:
                emoji = "📈" if quote.change_pct > 0 else "📉" if quote.change_pct < 0 else "➖"
                print(f"{emoji} {quote.symbol}: ${quote.last_price:.2f} ({quote.change_pct:+.2f}%) "
                      f"| Bid: ${quote.bid:.2f} Ask: ${quote.ask:.2f} | Vol: {quote.volume:,}")
            else:
                print(f"⚠️ {symbol}: 未找到该股票或获取行情失败（请检查股票代码是否正确）")

    if json_output:
        import json
        print(json.dumps(json_results, ensure_ascii=False, indent=2))

    _safe_disconnect(client)


def cmd_analyze(args):
    """技术分析"""
    if not args:
        print("用法: python ibkr_cli.py analyze SYMBOL [SYMBOL2 ...] [--period '1 Y'] [--bar '1 day'] [--json]")
        sys.exit(1)

    period = "1 Y"
    bar_size = "1 day"
    json_output = False
    symbols = []
    i = 0
    while i < len(args):
        if args[i] == "--period" and i + 1 < len(args):
            period = args[i + 1]
            i += 2
        elif args[i] == "--bar" and i + 1 < len(args):
            bar_size = args[i + 1]
            i += 2
        elif args[i] == "--json":
            json_output = True
            i += 1
        else:
            symbols.append(args[i].upper())
            i += 1

    if not symbols:
        print("❌ 请指定至少一个股票代码")
        sys.exit(1)

    client = _connect_client()
    from technical_analysis import analyze_symbol, format_technical_summary, to_json_summary

    for symbol in symbols:
        if not json_output:
            print(f"⏳ 正在分析 {symbol}...")
        result = analyze_symbol(client, symbol, period=period, bar_size=bar_size)
        if result:
            if json_output:
                print(to_json_summary(result))
            else:
                print(format_technical_summary(result))
        else:
            if json_output:
                import json
                print(json.dumps({"error": f"{symbol} 技术分析失败: 历史数据不足或股票代码无效"}))
            else:
                print(f"⚠️ {symbol} 技术分析失败: 历史数据不足（至少需要 30 根 K 线）或股票代码无效")
        if not json_output:
            print()

    _safe_disconnect(client)


def cmd_fundamentals(args):
    """基本面查询（IBKR + Finviz 双源合并）"""
    if not args or (len(args) == 1 and args[0] in ("-h", "--help")):
        print("用法: python ibkr_cli.py fundamentals SYMBOL [SYMBOL2 ...] [--json]")
        sys.exit(1)

    json_output = "--json" in args
    symbols = [a for a in args if a != "--json"]

    client = _connect_client()
    from finviz_data import get_finviz_fundamentals, format_finviz_fundamentals

    json_results = {}

    for symbol in symbols:
        symbol = symbol.upper()

        # IBKR 基本面
        fund = client.get_fundamentals(symbol)
        # Finviz 基本面（补充）
        finviz_fund = get_finviz_fundamentals(symbol)

        if json_output:
            result = {}
            if fund:
                import dataclasses
                result["ibkr"] = dataclasses.asdict(fund)
            if finviz_fund:
                result["finviz"] = finviz_fund
            if not result:
                result = {"error": "未找到基本面数据"}
            json_results[symbol] = result
        else:
            if fund:
                print(f"📊 {symbol} 基本面数据 (来源: IBKR)")
                print("=" * 50)
                print(f"  公司: {fund.company_name}")
                print(f"  行业: {fund.industry} / {fund.category}")
                if fund.sector:
                    print(f"  板块: {fund.sector}")
                print(f"  市值: {fund.market_cap}")
                print(f"  P/E 市盈率: {fund.pe_ratio}")
                print(f"  EPS: {fund.eps}")
                print(f"  股息收益率: {fund.dividend_yield}")
                print(f"  52周最高: {fund.high_52w}")
                print(f"  52周最低: {fund.low_52w}")
                print(f"  10日均量: {fund.avg_volume}")
                print()

            if finviz_fund:
                print(format_finviz_fundamentals(finviz_fund, symbol))
            elif not fund:
                print(f"⚠️ {symbol}: IBKR 和 Finviz 均未找到基本面数据")
            print()

    if json_output:
        import json
        print(json.dumps(json_results, ensure_ascii=False, indent=2))

    _safe_disconnect(client)


def cmd_portfolio(args):
    """组合分析"""
    json_output = "--json" in args
    args = [a for a in args if a != "--json"]
    subcommand = args[0] if args else "all"
    client = _connect_client()

    from portfolio_analytics import (
        get_portfolio_allocation, get_concentration_risk, get_portfolio_beta,
        get_correlation_matrix, get_benchmark_comparison,
        get_performance_attribution, get_max_drawdown,
        format_allocation, format_concentration, format_benchmark,
        format_attribution, format_drawdown, to_json_portfolio
    )

    json_results = {}

    if subcommand in ("allocation", "all"):
        if not json_output: print("⏳ 正在分析资产配置...")
        alloc = get_portfolio_allocation(client)
        if json_output:
            json_results["allocation"] = alloc
        else:
            print(format_allocation(alloc))
            print()

    if subcommand in ("concentration", "all"):
        if not json_output: print("⏳ 正在分析持仓集中度...")
        conc = get_concentration_risk(client)
        if json_output:
            json_results["concentration"] = conc
        else:
            print(format_concentration(conc))
            print()

    if subcommand in ("beta", "all"):
        if not json_output: print("⏳ 正在计算组合 Beta...")
        beta = get_portfolio_beta(client, "SPY", "6 M")
        if json_output:
            json_results["beta"] = beta
        else:
            if beta:
                print(f"📊 组合 Beta: {beta['portfolio_beta']} (vs {beta['benchmark']}, {beta['period']})")
                for h in beta["holdings_beta"]:
                    print(f"   {h['symbol']:8s} β={h['beta']:+.3f}  权重={h['weight']:.1f}%")
            else:
                print("⚠️ 无法计算 Beta: 股票持仓不足或历史数据不足")
            print()

    if subcommand in ("benchmark", "all"):
        benchmark = args[1] if len(args) > 1 and subcommand == "benchmark" else "SPY"
        period = args[2] if len(args) > 2 and subcommand == "benchmark" else "3 M"
        if not json_output: print(f"⏳ 正在对比基准 ({benchmark}, {period})...")
        comp = get_benchmark_comparison(client, benchmark, period)
        if json_output:
            json_results["benchmark_comparison"] = comp
        else:
            if comp:
                print(format_benchmark(comp))
            else:
                print("⚠️ 无法计算基准对比: 股票持仓不足或历史数据不足")
            print()

    if subcommand in ("attribution", "all"):
        if not json_output: print("⏳ 正在分析盈亏归因...")
        attrs = get_performance_attribution(client)
        if json_output:
            json_results["attribution"] = attrs
        else:
            print(format_attribution(attrs))
            print()

    if subcommand in ("drawdown", "all"):
        target = args[1] if len(args) > 1 and subcommand == "drawdown" else None
        if not json_output: print("⏳ 正在计算最大回撤...")
        dd = get_max_drawdown(client, target, "1 Y")
        if json_output:
            json_results["drawdown"] = dd
        else:
            if dd:
                print(format_drawdown(dd))
            else:
                print("⚠️ 无法计算最大回撤: 历史数据不足")
            print()

    if subcommand in ("correlation", "all"):
        if not json_output: print("⏳ 正在计算相关性矩阵...")
        corr = get_correlation_matrix(client, "3 M")
        if json_output:
            json_results["correlation"] = corr
        else:
            if corr:
                print("📊 高相关性持仓对:")
                for pair in corr.get("high_correlation_pairs", []):
                    print(f"   {pair['pair']}: {pair['correlation']:+.3f} ({pair['warning']})")
                if not corr.get("high_correlation_pairs"):
                    print("   ✅ 未发现高度相关的持仓对")
            else:
                print("⚠️ 股票持仓不足两只，无法计算相关性")
            print()

    if json_output:
        print(to_json_portfolio(json_results))

    _safe_disconnect(client)


def cmd_options(args):
    """期权分析"""
    json_output = "--json" in args
    args = [a for a in args if a != "--json"]
    subcommand = args[0] if args else "all"
    client = _connect_client()

    from options_analytics import (
        get_expiration_calendar, get_portfolio_greeks_summary,
        get_option_greeks, format_expiration_calendar,
        format_greeks_summary, format_option_greeks, to_json_options
    )

    json_results = {}

    if subcommand in ("calendar", "all"):
        if not json_output: print("⏳ 正在获取到期日日历...")
        calendar = get_expiration_calendar(client)
        if json_output:
            json_results["calendar"] = calendar
        else:
            print(format_expiration_calendar(calendar))
            print()

    if subcommand in ("greeks", "all"):
        positions = client.get_positions()
        opt_positions = [p for p in positions if p.sec_type == "OPT"]
        
        greeks_list = []
        for p in opt_positions:
            g = get_option_greeks(client, p)
            if g: greeks_list.append(g)

        if json_output:
            json_results["greeks"] = greeks_list
        else:
            if greeks_list:
                print("📊 期权 Greeks 明细:")
                print("=" * 60)
                for g in greeks_list:
                    print(format_option_greeks(g))
                    print()
            else:
                print("ℹ️ 无期权持仓")

    if subcommand in ("summary", "all"):
        if not json_output: print("⏳ 正在计算组合 Greeks 汇总...")
        summary = get_portfolio_greeks_summary(client)
        if json_output:
            json_results["summary"] = summary
        else:
            if summary:
                print(format_greeks_summary(summary))
            else:
                print("ℹ️ 无期权持仓，跳过 Greeks 汇总")
            print()

    if json_output:
        print(to_json_options(json_results))

    _safe_disconnect(client)


def cmd_trades(args):
    """交易复盘"""
    json_output = "--json" in args
    args = [a for a in args if a != "--json"]
    subcommand = args[0] if args else "all"
    client = _connect_client()

    from trade_review import (
        get_trade_history, get_trade_statistics,
        format_trade_history, format_trade_statistics,
        to_json_trades
    )

    json_results = {}

    if subcommand in ("history", "all"):
        if not json_output: print("⏳ 正在获取近期成交记录...")
        history = get_trade_history(client)
        if json_output:
            json_results["history"] = history
        else:
            print(format_trade_history(history))
            print()

    if subcommand in ("stats", "all"):
        if not json_output: print("⏳ 正在统计交易数据...")
        stats = get_trade_statistics(client)
        if json_output:
            json_results["statistics"] = stats
        else:
            if stats:
                print(format_trade_statistics(stats))
            else:
                print("ℹ️ 无成交记录，无法生成统计")
            print()

    if json_output:
        print(to_json_trades(json_results))

    _safe_disconnect(client)


def cmd_scanner(args):
    """市场扫描"""
    from scanner_enhanced import (
        run_enhanced_scanner, list_scan_presets,
        format_scan_results, to_json_scan_results
    )

    if not args or args[0] == "list":
        print("📋 可用扫描预设 (也可直接使用 --code 指定原生 API scanCode):")
        for name, desc in list_scan_presets().items():
            print(f"  • {name}: {desc}")
        if not args:
            return
        return

    preset_name = None
    scan_code = None
    size = 10
    above_price = None
    below_price = None
    above_volume = None
    market_cap_above = None
    market_cap_below = None
    json_output = False

    i = 0
    while i < len(args):
        if args[i] == "--code" and i + 1 < len(args):
            scan_code = args[i + 1]
            i += 2
        elif args[i] == "--size" and i + 1 < len(args):
            size = int(args[i + 1])
            i += 2
        elif args[i] == "--price-above" and i + 1 < len(args):
            above_price = float(args[i + 1])
            i += 2
        elif args[i] == "--price-below" and i + 1 < len(args):
            below_price = float(args[i + 1])
            i += 2
        elif args[i] == "--cap-above" and i + 1 < len(args):
            market_cap_above = float(args[i + 1])
            i += 2
        elif args[i] == "--cap-below" and i + 1 < len(args):
            market_cap_below = float(args[i + 1])
            i += 2
        elif args[i] == "--vol-above" and i + 1 < len(args):
            above_volume = int(args[i + 1])
            i += 2
        elif args[i] == "--json":
            json_output = True
            i += 1
        else:
            if not args[i].startswith("--") and preset_name is None and scan_code is None:
                preset_name = args[i]
            elif args[i].isdigit() and preset_name is not None:
                size = int(args[i])
            i += 1

    client = _connect_client()
    
    scan_target = scan_code if scan_code else (preset_name if preset_name else "自定义条件")
    if not json_output:
        print(f"⏳ 正在扫描 [{scan_target}] (top {size})...")
        
    results = run_enhanced_scanner(
        client, 
        preset_name=preset_name,
        scan_code=scan_code,
        size=size,
        above_price=above_price,
        below_price=below_price,
        above_volume=above_volume,
        market_cap_above=market_cap_above,
        market_cap_below=market_cap_below
    )
    
    if json_output:
        print(to_json_scan_results(results))
    else:
        print(format_scan_results(results, scan_target))
        
    _safe_disconnect(client)


def cmd_watchlist(args):
    """Watchlist 管理"""
    from scanner_enhanced import (
        add_to_watchlist, remove_from_watchlist,
        get_watchlist_quotes, format_watchlist
    )

    subcommand = args[0] if args else "list"

    if subcommand == "add":
        if len(args) < 2:
            print("用法: python ibkr_cli.py watchlist add SYMBOL [--buy PRICE] [--sell PRICE] [--notes TEXT]")
            sys.exit(1)
        symbol = args[1].upper()
        target_buy = None
        target_sell = None
        notes = ""
        i = 2
        while i < len(args):
            if args[i] == "--buy" and i + 1 < len(args):
                target_buy = float(args[i + 1])
                i += 2
            elif args[i] == "--sell" and i + 1 < len(args):
                target_sell = float(args[i + 1])
                i += 2
            elif args[i] == "--notes" and i + 1 < len(args):
                notes = args[i + 1]
                i += 2
            else:
                i += 1
        add_to_watchlist(symbol, target_buy, target_sell, notes)

    elif subcommand == "remove":
        if len(args) < 2:
            print("用法: python ibkr_cli.py watchlist remove SYMBOL")
            sys.exit(1)
        remove_from_watchlist(args[1].upper())

    elif subcommand == "list":
        client = _connect_client()
        items = get_watchlist_quotes(client)
        print(format_watchlist(items))
        _safe_disconnect(client)

    else:
        print(f"未知子命令: {subcommand}")
        print("可用: list, add, remove")


def cmd_news(args):
    """查询公司新闻（Yahoo RSS + Finviz 双源合并）"""
    from finviz_data import get_finviz_news, get_finviz_market_news, format_news
    import json as _json

    json_output = "--json" in args
    clean_args = [a for a in args if a != "--json"]

    if not clean_args:
        print("用法: python ibkr_cli.py news SYMBOL [limit] [--json]")
        print("       python ibkr_cli.py news market [--json]")
        sys.exit(1)

    # 全市场新闻
    if clean_args[0].lower() == "market":
        market_news = get_finviz_market_news()
        if json_output:
            print(_json.dumps(market_news, ensure_ascii=False, indent=2, default=str))
        else:
            print(format_news(market_news.get("news", []), "全市场新闻", limit=20))
            print()
            print(format_news(market_news.get("blogs", []), "财经博客", limit=10))
        return

    symbol = clean_args[0].upper()
    limit = int(clean_args[1]) if len(clean_args) > 1 and clean_args[1].isdigit() else 10

    # 双源获取
    all_news = []

    # 源1: Yahoo RSS（需要 IB Gateway 连接）
    try:
        client = _connect_client()
        yahoo_news = client.get_company_news(symbol, limit=limit)
        _safe_disconnect(client)
        for item in yahoo_news:
            all_news.append({
                "Date": item.get("date", ""),
                "Title": item.get("title", ""),
                "Link": item.get("link", ""),
                "Source": "Yahoo Finance",
            })
    except Exception:
        pass

    # 源2: Finviz
    finviz_news = get_finviz_news(symbol)
    for item in finviz_news:
        all_news.append({
            "Date": item.get("Date", ""),
            "Title": item.get("Title", ""),
            "Link": item.get("Link", ""),
            "Source": item.get("Source", "Finviz"),
        })

    # 按标题去重
    seen_titles = set()
    unique_news = []
    for item in all_news:
        title = item.get("Title", "").strip()
        if title and title not in seen_titles:
            seen_titles.add(title)
            unique_news.append(item)

    if json_output:
        print(_json.dumps({
            "symbol": symbol,
            "count": len(unique_news[:limit]),
            "news": unique_news[:limit]
        }, ensure_ascii=False, indent=2, default=str))
    elif unique_news:
        print(f"📰 {symbol} 最新新闻 (Yahoo + Finviz, 共 {len(unique_news)} 条):")
        print("=" * 65)
        for idx, item in enumerate(unique_news[:limit], 1):
            source_tag = f"[{item.get('Source', '')}]" if item.get('Source') else ""
            print(f"  {idx:2d}. [{item['Date']}] {item['Title']}")
            if source_tag:
                print(f"      来源: {source_tag}")
            if item.get('Link'):
                print(f"      🔗 {item['Link']}")
    else:
        print(f"⚠️ {symbol}: Yahoo 和 Finviz 均未获取到新闻")


def cmd_export(args):
    """数据导出"""
    subcommand = args[0] if args else "all"
    client = _connect_client()

    from export import export_portfolio_csv, export_allocation_csv, generate_investment_report

    if subcommand in ("portfolio", "all"):
        print("⏳ 正在导出持仓 CSV...")
        path = export_portfolio_csv(client)
        print(f"   → {path}")

    if subcommand in ("allocation", "all"):
        print("⏳ 正在导出资产配置 CSV...")
        path = export_allocation_csv(client)
        print(f"   → {path}")

    if subcommand in ("report", "all"):
        print("⏳ 正在生成综合报告...")
        path = generate_investment_report(client)
        print(f"   → {path}")

    _safe_disconnect(client)
    print("\n✅ 导出完成")


def cmd_history(args):
    """查询历史 K 线"""
    if not args:
        print("用法: python ibkr_cli.py history SYMBOL [--period '3 M'] [--bar '1 day']")
        sys.exit(1)

    period = "3 M"
    bar_size = "1 day"
    symbol = args[0].upper()
    i = 1
    while i < len(args):
        if args[i] == "--period" and i + 1 < len(args):
            period = args[i + 1]
            i += 2
        elif args[i] == "--bar" and i + 1 < len(args):
            bar_size = args[i + 1]
            i += 2
        else:
            i += 1

    client = _connect_client()
    bars = client.get_historical_data(symbol, duration=period, bar_size=bar_size)
    if bars:
        print(f"📊 {symbol} 历史 K 线 ({period}, {bar_size})")
        print("=" * 60)
        print(f"{'日期':12s} {'开盘':>10s} {'最高':>10s} {'最低':>10s} {'收盘':>10s} {'成交量':>12s}")
        for bar in bars[-20:]:  # 只显示最近 20 根
            print(f"{bar['date']:12s} ${bar['open']:>9,.2f} ${bar['high']:>9,.2f} "
                  f"${bar['low']:>9,.2f} ${bar['close']:>9,.2f} {bar['volume']:>12,}")
        if len(bars) > 20:
            print(f"\n  ...共 {len(bars)} 根 K 线，仅展示最近 20 根")
    else:
        print(f"⚠️ {symbol}: 未获取到历史数据（股票代码可能无效或数据源暂时不可用）")

    _safe_disconnect(client)


# ─── Finviz 数据命令 ───────────────────────────────────────────

def cmd_ratings(args):
    """分析师评级（Finviz）"""
    from finviz_data import get_finviz_ratings, format_ratings

    if not args:
        print("用法: python ibkr_cli.py ratings SYMBOL [--json]")
        sys.exit(1)

    json_output = "--json" in args
    symbols = [a.upper() for a in args if a != "--json"]

    json_results = {}
    for symbol in symbols:
        ratings = get_finviz_ratings(symbol)
        if json_output:
            json_results[symbol] = ratings if ratings else {"error": "无评级数据"}
        else:
            print(format_ratings(ratings, symbol))
            print()

    if json_output:
        import json
        print(json.dumps(json_results, ensure_ascii=False, indent=2, default=str))


def cmd_insider(args):
    """内部人交易（Finviz）"""
    from finviz_data import (
        get_finviz_insider, get_finviz_insider_market, format_insider
    )

    if not args:
        print("用法: python ibkr_cli.py insider SYMBOL [--json]")
        print("       python ibkr_cli.py insider market [latest|top week|top owner trade]")
        sys.exit(1)

    json_output = "--json" in args
    clean_args = [a for a in args if a != "--json"]

    if clean_args[0].lower() == "market":
        option = " ".join(clean_args[1:]) if len(clean_args) > 1 else "latest"
        records = get_finviz_insider_market(option)
        if json_output:
            import json
            print(json.dumps(records, ensure_ascii=False, indent=2, default=str))
        else:
            print(format_insider(records, f"全市场内部人交易 ({option})"))
        return

    json_results = {}
    for symbol in clean_args:
        symbol = symbol.upper()
        records = get_finviz_insider(symbol)
        if json_output:
            json_results[symbol] = records if records else {"error": "无内部人交易数据"}
        else:
            print(format_insider(records, f"{symbol} 内部人交易"))
            print()

    if json_output:
        import json
        print(json.dumps(json_results, ensure_ascii=False, indent=2, default=str))


def cmd_peers(args):
    """同行公司（Finviz），可选批量行情对比"""
    from finviz_data import get_finviz_peers, format_peers

    if not args:
        print("用法: python ibkr_cli.py peers SYMBOL [--json] [--quote]")
        sys.exit(1)

    json_output = "--json" in args
    with_quote = "--quote" in args
    symbol = [a for a in args if not a.startswith("--")][0].upper()

    peers = get_finviz_peers(symbol)

    if json_output:
        import json
        result = {"symbol": symbol, "peers": peers}

        # 附加行情
        if with_quote and peers:
            try:
                client = _connect_client()
                quotes = client.get_quotes_batch(peers[:10])
                import dataclasses
                result["peer_quotes"] = {
                    k: dataclasses.asdict(v) for k, v in quotes.items()
                }
                _safe_disconnect(client)
            except Exception:
                pass

        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_peers(peers, symbol))

        # 附加行情对比
        if with_quote and peers:
            try:
                client = _connect_client()
                quotes = client.get_quotes_batch(peers[:10])
                if quotes:
                    print(f"\n📈 同行实时行情:")
                    for sym, q in quotes.items():
                        emoji = "📈" if q.change_pct > 0 else "📉" if q.change_pct < 0 else "➖"
                        print(f"  {emoji} {sym:8s} ${q.last_price:.2f} ({q.change_pct:+.2f}%)")
                _safe_disconnect(client)
            except Exception:
                pass


def cmd_screen(args):
    """Finviz 多维条件选股"""
    from finviz_screener import (
        parse_screen_args, run_finviz_screen,
        format_screen_results, to_json_screen_results,
        list_available_filters, list_available_signals,
        _get_filter_options,
    )

    if not args or args[0] in ("-h", "--help"):
        print("用法: python ibkr_cli.py screen [OPTIONS]")
        print("\n可用过滤参数:")
        for cli_key, finviz_key in list_available_filters().items():
            print(f"  {cli_key:18s} → {finviz_key}")
        print("\n其他参数:")
        print("  --signal NAME    交易信号 (如 Top Gainers, Oversold)")
        print("  --size N         最大返回数量 (默认 20)")
        print("  --json           JSON 输出")
        print("\n示例:")
        print('  ./ibkr screen --sector Technology --pe "Under 20" --json')
        print('  ./ibkr screen --signal Oversold --size 10')
        print('  ./ibkr screen list  # 列出可用信号')
        return

    if args[0] == "list":
        print("📋 可用交易信号:")
        for s in list_available_signals():
            print(f"  • {s}")
        print("\n📋 可用过滤参数 (每个参数用 --help 查看可选值):")
        for cli_key, finviz_key in list_available_filters().items():
            options = _get_filter_options(finviz_key)
            preview = ", ".join(options[:5]) + ("..." if len(options) > 5 else "")
            print(f"  {cli_key:18s} {finviz_key:22s} [{preview}]")
        return

    filters, signal, limit, json_output = parse_screen_args(args)
    if filters is None:  # list 命令已处理
        return

    if not json_output:
        filter_desc = ", ".join(f"{k}={v}" for k, v in (filters or {}).items())
        if signal:
            filter_desc += f", Signal={signal}"
        print(f"⏳ Finviz 选股中 ({filter_desc or '默认'}, top {limit})...")

    results = run_finviz_screen(
        filters=filters, signal=signal, limit=limit
    )

    if json_output:
        print(to_json_screen_results(results))
    else:
        print(format_screen_results(results, filters, signal))


# ─── 主入口 ────────────────────────────────────────────────────

COMMANDS = {
    "status": ("检查 IB Gateway 连接状态", cmd_status),
    "quote": ("查询实时行情: quote AAPL NVDA", cmd_quote),
    "analyze": ("技术分析: analyze AAPL", cmd_analyze),
    "fundamentals": ("基本面查询(IBKR+Finviz): fundamentals AAPL", cmd_fundamentals),
    "ratings": ("分析师评级(Finviz): ratings AAPL", cmd_ratings),
    "insider": ("内部人交易(Finviz): insider AAPL / insider market", cmd_insider),
    "peers": ("同行公司(Finviz): peers AAPL [--quote]", cmd_peers),
    "screen": ("Finviz多维选股: screen --sector Technology --pe 'Under 20'", cmd_screen),
    "history": ("历史 K 线: history AAPL --period '3 M'", cmd_history),
    "portfolio": ("组合分析: portfolio [all|allocation|...]", cmd_portfolio),
    "options": ("期权分析: options [all|calendar|greeks|summary]", cmd_options),
    "trades": ("交易复盘: trades [all|history|stats]", cmd_trades),
    "scanner": ("IBKR市场扫描: scanner --code TOP_PERC_GAIN", cmd_scanner),
    "watchlist": ("Watchlist: watchlist [list|add|remove] SYMBOL", cmd_watchlist),
    "news": ("公司新闻(Yahoo+Finviz): news AAPL / news market", cmd_news),
    "export": ("数据导出: export [all|portfolio|allocation|report]", cmd_export),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print("🏦 IBKR 只读查询 CLI")
        print("⚠️  安全模式：仅查询，无法执行任何交易操作")
        print()
        print("用法: python ibkr_cli.py <命令> [参数...]")
        print()
        print("可用命令:")
        for name, (desc, _) in COMMANDS.items():
            print(f"  {name:15s} {desc}")
        sys.exit(0)

    cmd_name = sys.argv[1]
    cmd_args = sys.argv[2:]

    if cmd_name not in COMMANDS:
        print(f"❌ 未知命令: {cmd_name}")
        print(f"可用命令: {', '.join(COMMANDS.keys())}")
        print("使用 --help 查看帮助")
        sys.exit(1)

    _, cmd_func = COMMANDS[cmd_name]

    try:
        cmd_func(cmd_args)
    except KeyboardInterrupt:
        print("\n⏹️ 已中断")
    except SystemExit:
        raise
    except Exception as e:
        print(f"\n❌ 执行失败: {e}")
        print(f"   错误类型: {type(e).__name__}")
        print(f"   完整堆栈:")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
