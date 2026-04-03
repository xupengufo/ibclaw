#!/usr/bin/env python3
"""
主动告警模块
设计为通过 cron 定期运行，监控持仓风险并推送 Telegram 通知。
复用 keepalive.py 的 Telegram 通知基础设施。

告警类型：
1. 持仓大跌/大涨提醒
2. 持仓集中度警告
3. 期权到期提醒
4. Watchlist 目标价提醒

Crontab 建议 (每小时交易时段检查一次):
0 9-16 * * 1-5 cd ~/trading && ./run-alerts.sh >> ~/trading/alerts.log 2>&1

⚠️ 纯只读操作，不包含任何交易功能。
"""

import os
import json
import socket
from datetime import datetime
from typing import List, Dict

# ─── 配置 ─────────────────────────────────────────────────────

def load_local_env():
    """加载脚本同目录的 .env"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value

load_local_env()

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")

# 告警阈值（可通过 .env 自定义）
PRICE_DROP_THRESHOLD = float(os.getenv("ALERT_DROP_PCT", "5"))       # 日跌幅 > 5% 告警
PRICE_SURGE_THRESHOLD = float(os.getenv("ALERT_SURGE_PCT", "10"))    # 日涨幅 > 10% 告警
CONCENTRATION_THRESHOLD = float(os.getenv("ALERT_CONC_PCT", "25"))   # 单只占比 > 25% 告警
OPTION_EXPIRY_DAYS = int(os.getenv("ALERT_EXPIRY_DAYS", "7"))        # 期权到期 < 7 天告警

# 状态文件，避免重复告警
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, ".alert_state.json")
WATCHLIST_FILE = os.path.join(os.path.expanduser("~"), ".ibkr_watchlist.json")


# ─── 通知 ─────────────────────────────────────────────────────

def log(msg):
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(f"{timestamp} {msg}")


def send_telegram(message: str):
    """发送 Telegram 通知"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        log("⚠️ Telegram 未配置 (TG_BOT_TOKEN / TG_CHAT_ID)")
        return
    try:
        import requests
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TG_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=10)
        log("📤 Telegram 通知已发送")
    except Exception as e:
        log(f"⚠️ Telegram 发送失败: {e}")


# ─── 状态管理 ─────────────────────────────────────────────────

def load_state() -> dict:
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"alerts_sent": {}, "last_check": ""}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _alert_key(alert_type: str, symbol: str) -> str:
    """生成告警去重 key（每天每种告警每个 symbol 只发一次）"""
    today = datetime.now().strftime("%Y-%m-%d")
    return f"{today}:{alert_type}:{symbol}"


def _should_alert(state: dict, alert_type: str, symbol: str) -> bool:
    """检查是否应该发送告警（避免重复）"""
    key = _alert_key(alert_type, symbol)
    return key not in state.get("alerts_sent", {})


def _mark_alerted(state: dict, alert_type: str, symbol: str):
    """标记已发送"""
    key = _alert_key(alert_type, symbol)
    if "alerts_sent" not in state:
        state["alerts_sent"] = {}
    state["alerts_sent"][key] = datetime.now().isoformat()

    # 清理过期 key（只保留今天的）
    today = datetime.now().strftime("%Y-%m-%d")
    state["alerts_sent"] = {
        k: v for k, v in state["alerts_sent"].items()
        if k.startswith(today)
    }


# ─── 告警检查 ─────────────────────────────────────────────────

def check_price_alerts(client, state: dict) -> List[str]:
    """检查持仓大跌/大涨"""
    alerts = []
    positions = client.get_positions()

    for p in positions:
        if p.sec_type != "STK":
            continue

        try:
            quote = client.get_quote(p.symbol)
            if not quote or quote.change_pct == 0:
                continue

            if quote.change_pct <= -PRICE_DROP_THRESHOLD:
                if _should_alert(state, "drop", p.symbol):
                    msg = (
                        f"📉 <b>持仓大跌提醒</b>\n"
                        f"{p.symbol} 今日跌幅: {quote.change_pct:.2f}%\n"
                        f"当前价: ${quote.last_price:.2f}\n"
                        f"持仓: {p.quantity:.0f}股  市值: ${p.market_value:,.0f}\n"
                        f"未实现盈亏: ${p.unrealized_pnl:+,.0f} ({p.pnl_percent:+.1f}%)"
                    )
                    alerts.append(msg)
                    _mark_alerted(state, "drop", p.symbol)

            elif quote.change_pct >= PRICE_SURGE_THRESHOLD:
                if _should_alert(state, "surge", p.symbol):
                    msg = (
                        f"🚀 <b>持仓大涨提醒</b>\n"
                        f"{p.symbol} 今日涨幅: +{quote.change_pct:.2f}%\n"
                        f"当前价: ${quote.last_price:.2f}\n"
                        f"持仓: {p.quantity:.0f}股  市值: ${p.market_value:,.0f}\n"
                        f"未实现盈亏: ${p.unrealized_pnl:+,.0f} ({p.pnl_percent:+.1f}%)"
                    )
                    alerts.append(msg)
                    _mark_alerted(state, "surge", p.symbol)

        except Exception as e:
            log(f"⚠️ 获取 {p.symbol} 行情失败: {e}")

    return alerts


def check_concentration_alerts(client, state: dict) -> List[str]:
    """检查持仓集中度"""
    alerts = []
    positions = client.get_positions()
    total_value = sum(abs(p.market_value) for p in positions)

    if total_value == 0:
        return alerts

    for p in positions:
        weight = abs(p.market_value) / total_value * 100
        if weight > CONCENTRATION_THRESHOLD:
            if _should_alert(state, "concentration", p.symbol):
                msg = (
                    f"⚠️ <b>持仓集中度警告</b>\n"
                    f"{p.symbol} 占比: {weight:.1f}% (阈值: {CONCENTRATION_THRESHOLD}%)\n"
                    f"市值: ${p.market_value:,.0f} / 总资产: ${total_value:,.0f}\n"
                    f"建议适当分散，降低单一标的风险。"
                )
                alerts.append(msg)
                _mark_alerted(state, "concentration", p.symbol)

    return alerts


def check_expiration_alerts(client, state: dict) -> List[str]:
    """检查期权到期日"""
    from options_analytics import get_expiration_calendar

    alerts = []
    calendar = get_expiration_calendar(client)

    urgent_options = [e for e in calendar if 0 <= e.days_left <= OPTION_EXPIRY_DAYS]

    if urgent_options and _should_alert(state, "expiry", "batch"):
        lines = [f"⏰ <b>期权到期提醒</b>\n以下期权将在 {OPTION_EXPIRY_DAYS} 天内到期:\n"]
        for e in urgent_options:
            right_name = "看涨" if e.right == "C" else "看跌"
            lines.append(
                f"  • {e.symbol} ({right_name} ${e.strike:.0f})\n"
                f"    到期: {e.expiry_date} ({e.days_left}天后)\n"
                f"    持仓: {e.quantity:.0f}张  市值: ${e.market_value:,.0f}"
            )
        lines.append("\n请及时决策是否平仓/展期。")
        alerts.append("\n".join(lines))
        _mark_alerted(state, "expiry", "batch")

    return alerts


def check_watchlist_targets(client, state: dict) -> List[str]:
    """检查 Watchlist 中的目标价"""
    alerts = []

    if not os.path.exists(WATCHLIST_FILE):
        return alerts

    try:
        with open(WATCHLIST_FILE, "r") as f:
            watchlist = json.load(f)
    except (json.JSONDecodeError, IOError):
        return alerts

    for item in watchlist.get("items", []):
        symbol = item.get("symbol", "")
        target_buy = item.get("target_buy")
        target_sell = item.get("target_sell")

        if not symbol or (not target_buy and not target_sell):
            continue

        try:
            quote = client.get_quote(symbol)
            if not quote:
                continue

            if target_buy and quote.last_price <= target_buy:
                if _should_alert(state, "target_buy", symbol):
                    msg = (
                        f"🎯 <b>触达买入目标价</b>\n"
                        f"{symbol} 当前价: ${quote.last_price:.2f}\n"
                        f"目标买入价: ${target_buy:.2f}\n"
                        f"今日涨跌: {quote.change_pct:+.2f}%"
                    )
                    if item.get("notes"):
                        msg += f"\n备注: {item['notes']}"
                    alerts.append(msg)
                    _mark_alerted(state, "target_buy", symbol)

            if target_sell and quote.last_price >= target_sell:
                if _should_alert(state, "target_sell", symbol):
                    msg = (
                        f"🎯 <b>触达卖出目标价</b>\n"
                        f"{symbol} 当前价: ${quote.last_price:.2f}\n"
                        f"目标卖出价: ${target_sell:.2f}\n"
                        f"今日涨跌: {quote.change_pct:+.2f}%"
                    )
                    if item.get("notes"):
                        msg += f"\n备注: {item['notes']}"
                    alerts.append(msg)
                    _mark_alerted(state, "target_sell", symbol)

        except Exception as e:
            log(f"⚠️ 获取 {symbol} 行情失败: {e}")

    return alerts


# ─── 主入口 ───────────────────────────────────────────────────

def run_all_checks(client) -> List[str]:
    """执行所有告警检查，返回告警消息列表"""
    state = load_state()
    all_alerts = []

    log("🔍 开始告警检查...")

    # 1. 价格异动
    log("  检查价格异动...")
    all_alerts.extend(check_price_alerts(client, state))

    # 2. 集中度
    log("  检查持仓集中度...")
    all_alerts.extend(check_concentration_alerts(client, state))

    # 3. 期权到期
    log("  检查期权到期...")
    try:
        all_alerts.extend(check_expiration_alerts(client, state))
    except Exception as e:
        log(f"  ⚠️ 期权到期检查失败: {e}")

    # 4. Watchlist 目标价
    log("  检查 Watchlist 目标价...")
    all_alerts.extend(check_watchlist_targets(client, state))

    # 保存状态
    state["last_check"] = datetime.now().isoformat()
    save_state(state)

    return all_alerts


def main():
    """主入口，由 cron 调用"""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ibkr_readonly import IBKRReadOnlyClient

    client = IBKRReadOnlyClient()

    # 先检查 IB Gateway 是否可连
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((client.host, client.port))
        sock.close()
        if result != 0:
            log("⚠️ IB Gateway 端口不通，跳过告警检查")
            return
    except Exception:
        log("⚠️ 网络检查失败，跳过告警检查")
        return

    if not client.connect():
        log("❌ 无法连接 IB Gateway，跳过告警检查")
        return

    try:
        alerts = run_all_checks(client)

        if alerts:
            log(f"📢 发现 {len(alerts)} 条告警")
            for alert_msg in alerts:
                send_telegram(alert_msg)
                print(alert_msg)
                print()
        else:
            log("✅ 无告警")

    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
