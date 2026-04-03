#!/usr/bin/env python3
"""
数据导出模块
提供：持仓 CSV 导出、资产配置 CSV 导出、综合投资报告生成。
所有函数接收 IBKRReadOnlyClient 实例，纯只读操作。
"""

import csv
import os
from datetime import datetime
from typing import Optional


# ─── CSV 导出 ─────────────────────────────────────────────────

def export_portfolio_csv(client, filepath: str = None) -> str:
    """
    导出当前持仓为 CSV 文件
    返回导出文件路径
    """
    if not filepath:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(os.path.expanduser("~"), f"ibkr_portfolio_{timestamp}.csv")

    positions = client.get_positions()
    balance = client.get_balance()

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)

        # 账户摘要
        writer.writerow(["IBKR 持仓报告"])
        writer.writerow(["生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        writer.writerow([])

        # 余额信息
        writer.writerow(["账户摘要"])
        cash = balance.get("TotalCashValue", {}).get("amount", 0)
        net_liq = balance.get("NetLiquidation", {}).get("amount", 0)
        writer.writerow(["现金余额", f"${cash:,.2f}" if isinstance(cash, (int, float)) else cash])
        writer.writerow(["净资产", f"${net_liq:,.2f}" if isinstance(net_liq, (int, float)) else net_liq])
        writer.writerow([])

        # 持仓明细
        writer.writerow(["持仓明细"])
        writer.writerow([
            "标的", "类型", "数量", "成本价", "市值", "未实现盈亏", "盈亏%",
            "币种", "到期日", "行权价", "方向"
        ])

        total_value = 0
        total_pnl = 0
        for p in positions:
            writer.writerow([
                p.symbol,
                p.sec_type,
                p.quantity,
                f"${p.avg_cost:,.2f}",
                f"${p.market_value:,.2f}",
                f"${p.unrealized_pnl:+,.2f}",
                f"{p.pnl_percent:+.2f}%",
                p.currency,
                p.expiry if p.sec_type == "OPT" else "",
                f"${p.strike:.2f}" if p.sec_type == "OPT" and p.strike else "",
                p.right if p.sec_type == "OPT" else ""
            ])
            total_value += p.market_value
            total_pnl += p.unrealized_pnl

        writer.writerow([])
        writer.writerow(["合计", "", "", "", f"${total_value:,.2f}", f"${total_pnl:+,.2f}"])

    print(f"✅ 持仓已导出到: {filepath}")
    return filepath


def export_allocation_csv(client, filepath: str = None) -> str:
    """
    导出资产配置分析为 CSV
    """
    if not filepath:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(os.path.expanduser("~"), f"ibkr_allocation_{timestamp}.csv")

    # 避免循环导入
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from portfolio_analytics import get_portfolio_allocation, get_concentration_risk

    alloc = get_portfolio_allocation(client)
    conc = get_concentration_risk(client)

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)

        writer.writerow(["资产配置分析报告"])
        writer.writerow(["生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        writer.writerow([])

        # 按资产类型
        writer.writerow(["按资产类型"])
        writer.writerow(["类型", "市值", "占比", "持仓数"])
        for item in alloc.get("by_type", []):
            writer.writerow([item.label, f"${item.market_value:,.2f}", f"{item.weight_pct:.1f}%", item.count])
        writer.writerow([])

        # 按行业
        writer.writerow(["按行业板块 (仅股票)"])
        writer.writerow(["板块", "市值", "占比", "持仓数"])
        for item in alloc.get("by_sector", []):
            writer.writerow([item.label, f"${item.market_value:,.2f}", f"{item.weight_pct:.1f}%", item.count])
        writer.writerow([])

        # 集中度
        writer.writerow(["持仓集中度"])
        writer.writerow(["HHI 指数", conc.hhi_index])
        writer.writerow(["最大单只占比", f"{conc.max_single_pct:.1f}%"])
        writer.writerow([])

        if conc.warnings:
            writer.writerow(["风险警告"])
            for w in conc.warnings:
                writer.writerow([w])

    print(f"✅ 资产配置已导出到: {filepath}")
    return filepath


# ─── 综合报告 ─────────────────────────────────────────────────

def generate_investment_report(client, filepath: str = None) -> str:
    """
    生成综合文本投资报告，一站式展示所有关键信息
    """
    if not filepath:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(os.path.expanduser("~"), f"ibkr_report_{timestamp}.txt")

    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from ibkr_readonly import format_currency, format_pnl
    from portfolio_analytics import (
        get_portfolio_allocation, get_concentration_risk,
        get_performance_attribution,
        format_allocation, format_concentration, format_attribution
    )
    from options_analytics import (
        get_expiration_calendar, format_expiration_calendar
    )
    from trade_review import (
        get_trade_history, get_trade_statistics,
        format_trade_history, format_trade_statistics
    )

    lines = []
    lines.append("╔══════════════════════════════════════════════════════════════╗")
    lines.append("║            IBKR 投资分析综合报告                             ║")
    lines.append(f"║            {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):^40s}          ║")
    lines.append("╚══════════════════════════════════════════════════════════════╝")
    lines.append("")

    # ═══ 1. 账户摘要 ═══
    lines.append("═" * 60)
    lines.append("📊 一、账户摘要")
    lines.append("═" * 60)

    balance = client.get_balance()
    accounts = client.get_accounts()

    cash = balance.get("TotalCashValue", {}).get("amount", 0)
    net_liq = balance.get("NetLiquidation", {}).get("amount", 0)
    buying_power = balance.get("BuyingPower", {}).get("amount", 0)

    if accounts:
        lines.append(f"  账户: {', '.join(accounts)}")
    lines.append(f"  现金余额:   {format_currency(cash) if isinstance(cash, (int, float)) else cash}")
    lines.append(f"  净资产:     {format_currency(net_liq) if isinstance(net_liq, (int, float)) else net_liq}")
    if isinstance(buying_power, (int, float)):
        lines.append(f"  购买力:     {format_currency(buying_power)}")
    lines.append("")

    # ═══ 2. 持仓明细 ═══
    lines.append("═" * 60)
    lines.append("📈 二、持仓明细")
    lines.append("═" * 60)

    positions = client.get_positions()
    if not positions:
        lines.append("  (无持仓)")
    else:
        total_value = sum(p.market_value for p in positions)
        total_pnl = sum(p.unrealized_pnl for p in positions)

        for p in positions:
            weight = abs(p.market_value) / abs(total_value) * 100 if total_value else 0
            pnl = format_pnl(p.unrealized_pnl, p.pnl_percent)
            type_tag = f"[{p.sec_type}]" if p.sec_type != "STK" else ""
            lines.append(
                f"  {p.symbol} {type_tag}: {p.quantity:.0f}股 "
                f"@ {format_currency(p.avg_cost)} → 市值 {format_currency(p.market_value)} "
                f"({weight:.1f}%) {pnl}"
            )

        lines.append(f"\n  总市值: {format_currency(total_value)}  "
                      f"总未实现盈亏: {format_currency(total_pnl)}")
    lines.append("")

    # ═══ 3. 资产配置 ═══
    lines.append("═" * 60)
    lines.append("📦 三、资产配置分析")
    lines.append("═" * 60)

    try:
        alloc = get_portfolio_allocation(client)
        lines.append(format_allocation(alloc))
    except Exception as e:
        lines.append(f"  ⚠️ 获取失败: {e}")
    lines.append("")

    # ═══ 4. 集中度风险 ═══
    lines.append("═" * 60)
    lines.append("🎯 四、集中度风险分析")
    lines.append("═" * 60)

    try:
        conc = get_concentration_risk(client)
        lines.append(format_concentration(conc))
    except Exception as e:
        lines.append(f"  ⚠️ 获取失败: {e}")
    lines.append("")

    # ═══ 5. 盈亏归因 ═══
    lines.append("═" * 60)
    lines.append("🧩 五、盈亏归因")
    lines.append("═" * 60)

    try:
        attrs = get_performance_attribution(client)
        lines.append(format_attribution(attrs))
    except Exception as e:
        lines.append(f"  ⚠️ 获取失败: {e}")
    lines.append("")

    # ═══ 6. 期权到期日历 ═══
    lines.append("═" * 60)
    lines.append("📅 六、期权到期日历")
    lines.append("═" * 60)

    try:
        calendar = get_expiration_calendar(client)
        lines.append(format_expiration_calendar(calendar))
    except Exception as e:
        lines.append(f"  ⚠️ 获取失败: {e}")
    lines.append("")

    # ═══ 7. 近期交易 ═══
    lines.append("═" * 60)
    lines.append("📋 七、近期交易记录")
    lines.append("═" * 60)

    try:
        history = get_trade_history(client)
        lines.append(format_trade_history(history, limit=15))

        stats = get_trade_statistics(client)
        if stats:
            lines.append("")
            lines.append(format_trade_statistics(stats))
    except Exception as e:
        lines.append(f"  ⚠️ 获取失败: {e}")
    lines.append("")

    # ═══ 结尾 ═══
    lines.append("═" * 60)
    lines.append(f"报告生成完毕 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("⚠️ 本报告仅供参考，不构成任何投资建议")
    lines.append("═" * 60)

    report_text = "\n".join(lines)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"✅ 综合报告已导出到: {filepath}")
    return filepath


# ─── 独立运行入口 ─────────────────────────────────────────────

def main():
    """独立运行：生成所有导出文件"""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ibkr_readonly import IBKRReadOnlyClient

    client = IBKRReadOnlyClient()

    if not client.connect():
        print("❌ 无法连接 IB Gateway")
        return

    print("📤 数据导出")
    print("=" * 60)

    # 1. 持仓 CSV
    print("\n⏳ 正在导出持仓 CSV...")
    csv_path = export_portfolio_csv(client)
    print(f"   → {csv_path}")

    # 2. 配置 CSV
    print("\n⏳ 正在导出资产配置 CSV...")
    alloc_path = export_allocation_csv(client)
    print(f"   → {alloc_path}")

    # 3. 综合报告
    print("\n⏳ 正在生成综合报告...")
    report_path = generate_investment_report(client)
    print(f"   → {report_path}")

    client.disconnect()
    print("\n✅ 所有导出完成")


if __name__ == "__main__":
    main()
