# IBKR 只读查询 Skill for OpenClaw

> 🔒 **只读安全模式**：此 Skill 仅能查询数据，**无法执行任何交易操作**。

通过 [OpenClaw](https://openclaw.ai) 在 Telegram 中直接查看你的 IBKR 持仓、余额和实时行情。

---

### 🔥 实际效果演示

![IBKR 持仓查询演示](1.png)

![IBKR 深度投研分析演示](2.png)

---

## ⚡ 一键安装（推荐）

直接把以下内容发送给你的 OpenClaw 机器人：

```
请帮我安装这个 Skill：https://github.com/liusai0820/ibkrclaw.git

安装完成后，请运行 setup.sh 完成环境配置，然后告诉我需要在 .env 文件里填写哪些 IBKR 账号信息。
```

OpenClaw 会自动完成所有安装步骤，完成后只需提供你的 **IBKR 账号（用户名）** 和 **密码**。

---

## 📋 前置条件

在开始前，请确认以下条件满足：

| 条件 | 说明 |
|------|------|
| **⚠️ 强烈建议：独立使用者账户** | <b>请勿使用你的主账户！</b>请在 IBKR 后台新创建一个<b>"使用者账户"（Secondary User）</b>，并<b>仅赋予只读权限（取消所有交易权限）</b>。这能从根本上保证你的资金安全。<br>👉 [点击查看：如何创建只读使用者账户的视频教程](http://xhslink.com/o/8qmxlBeeSGj) |
| IBKR 账户 | 确保上述创建的独立只读账户可登录（真实账户或模拟盘均可） |
| IBKR Key App | 安装在手机上，用于新创建的只读账户的 2FA 认证 |
| Java 17+ | 服务器或 Mac 上需要安装 |
| Python 3.9+ | 用于运行查询脚本 |
| Chrome/Chromium | 自动登录需要（Selenium 驱动） |

---

## 🛠️ 手动安装步骤

如果你想手动安装，按以下步骤操作：

### 第 1 步：克隆此仓库

```bash
git clone https://github.com/liusai0820/ibkrclaw.git
```

### 第 2 步：运行安装脚本

```bash
bash ibkrclaw/scripts/setup.sh
```

脚本会自动完成：
- ✅ 检查 Java、Chrome 环境
- ✅ 下载 IBKR Client Portal Gateway
- ✅ 创建 Python 虚拟环境并安装依赖（`ibeam`, `requests`, `selenium`）
- ✅ 创建 `.env` 配置文件模板
- ✅ 生成 `start-gateway.sh` 快捷脚本

### 第 3 步：填写 IBKR 账号信息

编辑 `~/trading/.env` 文件，填入你的 IBKR 账号：

```bash
# 只需修改这两行
IBEAM_ACCOUNT=你的IBKR用户名
IBEAM_PASSWORD='你的IBKR密码'

# 以下根据实际情况修改
IBEAM_GATEWAY_BASE_URL=https://localhost:5001
IBEAM_GATEWAY_DIR=/path/to/trading/clientportal
```

> ⚠️ **安全提示**：`.env` 文件只保存在本地，不会上传到任何服务器。

### 第 4 步：启动 Gateway

```bash
cd ~/trading
./start-gateway.sh
```

等待约 20 秒让 Gateway 完全启动。

### 第 5 步：首次认证

Gateway 启动后，运行保活脚本即可自动完成认证（通过 Selenium 自动填入账号密码）：

```bash
cd ~/trading && venv/bin/python keepalive.py
```

如果你的账户需要 2FA（非 bot 专用账户），则需要手动触发认证：

```bash
cd ~/trading && venv/bin/python manual_auth.py
```

然后在手机上打开 IBKR Key App 批准登录。

---

## 💬 在 OpenClaw / Telegram 中使用

安装并认证成功后，直接在 Telegram 中向 OpenClaw 机器人发送以下消息即可：

| 你说的话 | 机器人返回 |
|----------|-----------|
| 我的 IBKR 持仓有哪些？ | 所有持仓、成本价、当前市值、盈亏% |
| 帮我查一下持仓盈亏 | 账户余额 + 持仓盈亏汇总 |
| 帮我看看苹果 (AAPL) 最近的基本面，市值和市盈率怎么样？ | 最新基本面数据（市值、P/E、EPS）+ 财报与公司业务分析 |
| 利用 IBKR 历史数据，分析一下 NVDA 最近 3 个月的走势 | 调用历史 K 线并计算近期支撑/阻力位，输出趋势判断 |
| 今天美股涨得最猛的 10 只股票是哪些？ | 调取市场扫描器获取涨幅榜，并分析哪些板块在领涨 |
| 帮我复盘一下过往的投资情况，分析我的投资风格 | 基于你的持仓与历史盈亏，通过大模型深入分析你的投资偏好和收益特征并生成个人投资画像 |
| 帮我查一下 LMND 最近有什么新闻，为什么暴跌？ | 通过新闻引擎聚合财经头条，叠加 AI 事件驱动推演逻辑 |

**触发词**：`IBKR`、`分析公司`、`盈透`、`持仓`、`股价`、`行情`、`基本面`、`财报`、`投资建议`

---

## 🔄 会话保活（三层自愈架构）

IBKR 会话默认数小时过期，同时 Gateway 进程也可能因重启等原因丢失。本 Skill 内建了**三层自愈架构**，确保 7×24 无人值守运行：

### 第 1 层：Gateway 进程保活（launchd）

通过 macOS `launchd` 守护进程确保 Gateway Java 进程常驻，崩溃后 30 秒内自动重启。

**安装方法：**

将以下 plist 文件放到 `~/Library/LaunchAgents/com.ibkr.gateway.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ibkr.gateway</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/你的用户名/trading/start-gateway.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/你的用户名/trading/clientportal</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>30</integer>
</dict>
</plist>
```

加载守护进程：

```bash
launchctl load ~/Library/LaunchAgents/com.ibkr.gateway.plist
```

### 第 2 层：会话 Tickle 续命（cron + keepalive.py）

每 5 分钟调用 IBKR 的 `/tickle` 接口延长会话有效期。

```bash
# 添加 crontab
crontab -e

# 写入以下内容
*/5 * * * * cd ~/trading && venv/bin/python /path/to/ibkrclaw/scripts/keepalive.py >> ~/trading/keepalive.log 2>&1
```

### 第 3 层：断线自动重登（Selenium）

当 keepalive.py 检测到会话过期时，会自动调用内置的 Selenium 模块，通过 headless Chrome 执行网页登录流程（填入 `.env` 中的账号密码并提交），**全程无需手动干预**。

> 💡 此功能特别适合不需要 2FA 的专用 bot 账户。如果你的账户开启了 2FA（IB Key），自动重登后仍需在手机上批准。

**整体流程图：**

```
cron (每5分钟)
  └─ keepalive.py
       ├─ Gateway 无响应？ → 等待 launchd 自动重启
       ├─ 已认证？ → tickle 续命 ✅
       └─ 未认证？ → Selenium 自动登录 🔄
            ├─ 登录成功 → 会话恢复 ✅
            └─ 登录失败 → 打日志，等下次重试
```

---

## 🔧 功能说明

| 功能 | 支持 | 说明 |
|------|------|------|
| 查看持仓 | ✅ | 股票持仓、成本价、市值、盈亏 |
| 查看余额 | ✅ | 现金余额、净资产 |
| 实时行情 | ✅ | 任意股票的实时价格与多空买卖价 |
| 深度基本面 | ✅ | 查询公司市值、P/E市盈率、EPS、股息收益及行业分类 |
| 历史K线走势 | ✅ | 获取过去 N 天/月/年的价格序列，用于趋势分析 |
| 市场大盘扫描 | ✅ | 查询全市场涨幅榜、跌幅榜及异动榜 |
| 最新财经事件 | ✅ | 获取最新公司新闻事件，通过AI进行舆情与驱动分析 |
| 下单 | ❌ | **完全不支持** |
| 修改/取消订单 | ❌ | **完全不支持** |

---

## 📁 文件结构

```
ibkr-trader/
├── SKILL.md              # OpenClaw Skill 描述文件
├── README.md             # 本文档
├── scripts/
│   ├── setup.sh          # 一键安装脚本（部署 Gateway + Python 环境）
│   ├── ibkr_readonly.py  # 核心只读查询客户端（持仓/行情/基本面/K线/扫描）
│   └── keepalive.py      # 保活脚本（tickle续命 + 断线自动Selenium重登）
└── references/
    └── ...               # 参考文档
```

**部署后在 `~/trading/` 目录下的文件：**

```
~/trading/
├── .env                  # IBKR 凭证（本地保存，不上传）
├── clientportal/         # IBKR Client Portal Gateway（Java）
├── venv/                 # Python 虚拟环境
├── start-gateway.sh      # Gateway 启动脚本（由 launchd 调用）
├── keepalive.py          # 保活脚本副本（cron 调用）
├── manual_auth.py        # 手动认证脚本（备用）
├── keepalive.log         # 保活日志
└── gateway-launchd.log   # Gateway 启动日志
```

---

## 🚨 故障排查

| 问题 | 排查步骤 |
|------|----------|
| Gateway 无响应 | `pgrep -af GatewayStart` 检查进程 → 无进程则 `launchctl list \| grep ibkr` 检查 launchd 状态 |
| 认证过期 | 查看 `~/trading/keepalive.log` 最后几行 → 正常情况下 keepalive 会自动重登 |
| 自动重登失败 | 检查 Chrome/chromedriver 是否安装：`which chromedriver` |
| 连接被拒绝 | Gateway 未启动 → `bash ~/trading/start-gateway.sh` 或重新加载 launchd |
| 端口冲突 | `lsof -i :5001` 检查端口占用 → 可在 `clientportal/root/conf.yaml` 修改 `listenPort` |
| keepalive 没执行 | `crontab -l` 检查是否注册 → 检查 `~/trading/keepalive.log` 是否有最近的日志 |

---

## 🔐 安全说明

- 此 Skill **仅使用 GET 请求**，不调用任何修改账户的 API
- 账号密码存储在本地 `.env` 文件中，不会传输到第三方
- 源代码完全开源，可自行审查
- 即使有人要求下单，此 Skill **技术上无法执行**
- Selenium 自动登录仅在本地运行，浏览器实例为 headless 模式，用完即销毁

---

## ⚖️ 免责声明 (Disclaimer)

**请在安装和使用此工具前仔细阅读：**

1. **按"原样"提供**：本工具代码完全开源且免费，按"原样"提供，不带任何明示或暗示的保证。
2. **数据准确性风险**：通过此工具查询到的持仓、余额、盈亏或行情及报价数据，可能因网络延迟、API 限制或代码逻辑问题而出现误差、未及时更新或根本错误。**本工具的数据不能代替官方渠道（TWS 或 IBKR Mobile App），仅供一般性参考，请勿据此做出任何投资或交易的决定。**
3. **资金安全责任自负**：虽然我们在设计上将其限制为"只读"并强烈建议您通过"只读使用者账户"来使用，但在自行部署和提供凭证的过程中可能遇到的任何意外（如账号本身设置错误、服务器被黑等），作者概不负责。
4. **无责任担保**：对于任何人因使用、无法使用、或依赖本工具提供的信息而导致的任何直接或间接的财务损失、利润损失或其他后果，**工具作者不承担任何法律责任。使用本工具即代表您同意自行承担所有可能产生的风险。**

---

## 📄 License

MIT License - 自由使用、修改和分发。
