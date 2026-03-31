# 故障排查指南

## 快速诊断

运行连接状态检查：
```bash
./ibkr status
```

## 常见问题

### 1. 连接失败 — "无法连接 IB Gateway"

**症状**：`ibkr_cli.py` 输出 "❌ 无法连接 IB Gateway"

**排查步骤**：
1. 检查 IB Gateway 是否启动：桌面上应能看到 IB Gateway 窗口
2. 检查 IB Gateway 是否已登录：窗口标题栏应显示账户号
3. 检查端口：IB Gateway → Configure → Settings → API → Socket port 应为 **4001**
4. 检查 Socket Clients：确认 "Enable ActiveX and Socket Clients" 已勾选
5. 检查 Trusted IPs：确认包含 **127.0.0.1**
6. 检查 `.env` 配置是否匹配

### 2. clientId 冲突 — "clientId already in use"

**症状**：连接时报 clientId 冲突错误

**原因**：上一次连接未正常断开，IB Gateway 仍保留旧连接

**解决**：
```bash
# 方法 1：换一个 clientId（几分钟后恢复）
IB_CLIENT_ID=2 ./ibkr status

# 方法 2：等待 3-5 分钟后重试（旧连接会超时释放）
```

### 3. 端口不通

**排查**：
```bash
# macOS / Linux
nc -zv 127.0.0.1 4001

# 或在 Python 中
python -c "import socket; s=socket.socket(); s.settimeout(3); print(s.connect_ex(('127.0.0.1',4001))); s.close()"
# 输出 0 = 通，非 0 = 不通
```

**常见原因**：
- IB Gateway 未启动
- IB Gateway 启动了但未登录（2FA 未确认）
- 端口配置不是 4001（检查 API Settings）

### 4. 行情数据为 0 或 NaN

**原因**：使用免费延迟行情（`reqMarketDataType(3)`），在以下情况可能返回 0：
- 美股非交易时段（延迟行情无数据）
- 期权需要 OPRA 订阅（$1.5/月）

**说明**：持仓的市值和盈亏通过 `ib.portfolio()` 获取，不受此影响。

### 5. 基本面数据获取失败

**原因**：`reqFundamentalData()` 需要 Reuters/Refinitiv 基本面数据订阅

**降级**：脚本会自动用 ticker 数据（如 52 周高低）做补充

### 6. 期权 Greeks 为 0

**原因**：期权延迟行情需要 OPRA 数据订阅（$1.5/月）

**说明**：没有 OPRA 订阅时，`modelGreeks` 可能为空。持仓盈亏仍可通过 `portfolio()` 查看。

### 7. 历史数据不足

**原因**：
- 新上市不久的股票，历史数据有限
- 请求的 `durationStr` 超出可用范围
- IB Gateway 的历史数据速率限制（每 10 秒最多 10 个请求）

**建议**：
- 减少并行请求数量
- 对新股缩短查询期间

### 8. Scanner 扫描失败

**原因**：
- IB Gateway 未完全连接（刚登录，数据未就绪）
- Scanner 请求过于频繁

**建议**：登录后等待 30 秒再运行扫描

### 9. Mac 重启后无法连接

**操作**：
1. 手动启动 IB Gateway（Applications → IB Gateway）
2. 选择 "IB API" 模式
3. 输入只读子账户的用户名和密码
4. 在手机上确认 IBKR Key 2FA 通知
5. 等待 IB Gateway 完成启动（10-30 秒）

> **注意**：这是唯一需要手动干预的场景。IB Gateway 的 Auto Restart 可处理周末维护等情况。

### 10. 认证过期

**频率**：Auto Restart 模式下，约每周自动续一次

**如果 Auto Restart 失败**：手动重启 IB Gateway 并登录

## 日志位置

| 日志 | 路径 |
|------|------|
| 健康检查日志 | `~/trading/keepalive.log` |
| 告警日志 | `~/trading/alerts.log` |
| 连接状态文件 | `~/trading/.gw_state` |
| 告警状态文件 | `~/trading/.alert_state.json` |

## 联系方式

如果以上步骤无法解决问题，请检查 IB Gateway 的日志文件（通常在 `~/Jts/ibgateway/` 目录下）。
