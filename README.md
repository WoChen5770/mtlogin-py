# M-Team 青龙面板保活

本仓库用于在青龙面板中运行 M-Team 账号保活任务。青龙入口脚本是 `ql_mtlogin.py`，核心逻辑文件是无后缀的 `mtlogin`，根目录只保留一个 `.py` 文件，避免青龙订阅自动生成多个定时任务。

## 青龙订阅

青龙面板进入「订阅管理」后添加仓库：

```text
https://github.com/WoChen5770/mtlogin-py.git
```

建议订阅匹配规则只匹配：

```text
ql_mtlogin.py
```

脚本头部已提供青龙识别用的 `# cron:` 和 `# new Env('M-Team 保活')`，订阅生成的任务名称应为 `M-Team 保活`。

## 依赖

在青龙依赖管理中安装 Python 依赖：

```text
pyotp
requests
curl-cffi
```

也可以在青龙终端中执行：

```bash
pip3 install -r requirements.txt
```

## 环境变量

青龙入口统一使用 `MT_` 前缀变量，避免与面板或其他脚本变量冲突。

| 环境变量 | 必填 | 说明 |
|---|---|---|
| `MT_USERNAME` | 条件必填 | M-Team 用户名；使用 `MT_M_TEAM_AUTH` 时可不填 |
| `MT_PASSWORD` | 条件必填 | M-Team 密码；使用 `MT_M_TEAM_AUTH` 时可不填 |
| `MT_TOTPSECRET` | 条件必填 | TOTP 二次验证密钥；使用 `MT_M_TEAM_AUTH` 时可不填 |
| `MT_M_TEAM_AUTH` | 否 | 已有 Authorization token，有值时跳过账号密码登录 |
| `MT_M_TEAM_DID` | 否 | 设备 DID |
| `MT_PROXY` | 否 | HTTP/HTTPS 代理地址 |
| `MT_DB_PATH` | 否 | SQLite 缓存路径，默认 `/ql/data/db/mt/cookie.db` |
| `MT_SKIP_CACHE` | 否 | 设置为 `1`/`true` 时跳过本地 token 缓存 |
| `MT_VERBOSE_CONFIG` | 否 | 设置为 `1`/`true` 时打印脱敏启动配置 |
| `MT_DRY_RUN` | 否 | 设置为 `1`/`true` 时只验证变量解析，不请求网络 |

## 多账号

多个账号使用 `&` 分隔，同一组变量按位置一一对应：

```bash
export MT_USERNAME="user1&user2"
export MT_PASSWORD="pass1&pass2"
export MT_TOTPSECRET="totp_secret1&totp_secret2"
export MT_DB_PATH="/ql/data/db/mt/user1.db&/ql/data/db/mt/user2.db"
```

如果某个变量只配置一个值，会作为所有账号的公共配置使用，例如公共代理：

```bash
export MT_PROXY="http://127.0.0.1:7890"
```

建议多账号分别配置 `MT_DB_PATH`，避免不同账号共用 token 缓存和保活快照。

## 定时任务

青龙订阅生成的任务命令应为：

```bash
python3 ql_mtlogin.py
```

默认定时：

```text
12 */6 * * *
```

首次配置后可以先开启 dry-run 验证变量解析：

```bash
MT_VERBOSE_CONFIG=1 MT_DRY_RUN=1 python3 ql_mtlogin.py
```

确认账号数量、必填项和缓存路径无误后，再关闭 `MT_DRY_RUN` 正式运行。

## 通知

`ql_mtlogin.py` 会调用青龙面板内置 `notify.py` 发送通知，成功和失败都会通知。通知渠道请在青龙面板「系统设置」或通知配置中统一配置，不需要在本脚本里配置 Telegram、QQPush、飞书或 ntfy 变量。

成功通知包含每个账号的：

- 上传量
- 下载量
- 魔力值
- 上次保活时间
- 本次保活时间
- 距离上次保活时间
- 距离上次保活的上传量变化
- 距离上次保活的下载量变化
- 距离上次保活的魔力值变化

首次成功运行时没有历史快照，变化量会显示为「首次记录」。之后每次成功保活都会把本次数据写入 `MT_DB_PATH` 对应的 SQLite 缓存，用于下次计算变化量。
