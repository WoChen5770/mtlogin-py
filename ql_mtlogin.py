#!/usr/bin/env python3
"""
青龙面板入口脚本 —— m-team 保活签到
====================================
用法：直接放在青龙面板的任务命令里执行。 python3 ql_mtlogin.py

多账号支持：
  环境变量用 & 分隔多个账号的对应字段，例如：
    export MT_USERNAME="user1&user2"
    export MT_PASSWORD="pass1&pass2"
    export MT_TOTPSECRET="sec1&sec2"
  每个字段的 & 数量必须一致（=账号数-1），否则脚本会报错退出。

环境变量命名（MT_ 前缀，避免与青龙内置变量冲突）：
  MT_USERNAME         用户名（必填，除非用 MT_M_TEAM_AUTH）
  MT_PASSWORD         密码   （必填，除非用 MT_M_TEAM_AUTH）
  MT_TOTPSECRET       TOTP 密钥（必填，除非用 MT_M_TEAM_AUTH）
  MT_M_TEAM_AUTH      m-team auth token（可选，有则跳过登录）
  MT_M_TEAM_DID       设备 ID（可选）
  MT_PROXY            代理地址
  MT_UA               User-Agent
  MT_API_HOST         API 域名
  MT_API_REFERER      Referer
  MT_QQPUSH           QQ 推送 QQ 号
  MT_QQPUSH_TOKEN     QQ 推送 token
  MT_WXCORPID         微信企业号 corpid
  MT_WXAGENTSECRET    微信企业号 agentsecret
  MT_WXAGENTID        微信企业号 agentid
  MT_WXUSERID         微信企业号 userid
  MT_DING_TALK_ROBOT_WEBHOOK_TOKEN  钉钉机器人 webhook
  MT_DING_TALK_ROBOT_SECRET         钉钉机器人 secret
  MT_DING_TALK_ROBOT_AT_MOBILES     钉钉 @手机号
  MT_TGBOT_TOKEN      Telegram Bot token
  MT_TGBOT_CHAT_ID    Telegram chat id
  MT_TGBOT_PROXY      Telegram 代理
  MT_FEISHU_WEBHOOKURL  飞书 webhook
  MT_FEISHU_SECRET      飞书 secret
  MT_FEISHU_APP_ID      飞书应用 app_id
  MT_FEISHU_APP_SECRET  飞书应用 secret
  MT_FEISHU_RECEIVE_ID  飞书接收者 ID
  MT_NTFY_URL         ntfy 地址
  MT_NTFY_TOPIC       ntfy topic
  MT_NTFY_USER        ntfy 用户名
  MT_NTFY_PASSWORD    ntfy 密码
  MT_NTFY_TOKEN       ntfy token
  MT_TIME_OUT         超时（秒）
  MT_DB_PATH          cookie 持久化路径
  MT_COOKIE_MODE      cookie 模式 (normal/strict)
  MT_SKIP_CACHE       跳过缓存 (1/true)
  MT_VERBOSE_CONFIG   打印启动配置 (1/true)
"""

import os
import sys
import time

# 确保当前目录在 sys.path 中，以便 import mtlogin
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mtlogin import Config, JobServer, log_info


# ── 青龙环境变量映射表 ──────────────────────────────────────────
# (青龙 MT_ 变量名, 原始 Config 属性名, 类型转换)
ENV_MAP = [
    ("MT_USERNAME", "username", str),
    ("MT_PASSWORD", "password", str),
    ("MT_TOTPSECRET", "totpsecret", str),
    ("MT_M_TEAM_AUTH", "m_team_auth", str),
    ("MT_M_TEAM_DID", "m_team_did", str),
    ("MT_PROXY", "proxy", str),
    ("MT_UA", "ua", str),
    ("MT_API_HOST", "api_host", str),
    ("MT_API_REFERER", "referer", str),
    ("MT_QQPUSH", "qqpush", str),
    ("MT_QQPUSH_TOKEN", "qqpush_token", str),
    ("MT_WXCORPID", "wxcorpid", str),
    ("MT_WXAGENTSECRET", "wxagentsecret", str),
    ("MT_WXAGENTID", "wxagentid", int),
    ("MT_WXUSERID", "wxuserid", str),
    ("MT_DING_TALK_ROBOT_WEBHOOK_TOKEN", "ding_talk_robot_webhook_token", str),
    ("MT_DING_TALK_ROBOT_SECRET", "ding_talk_robot_secret", str),
    ("MT_DING_TALK_ROBOT_AT_MOBILES", "ding_talk_robot_at_mobiles", str),
    ("MT_TGBOT_TOKEN", "tgbot_token", str),
    ("MT_TGBOT_CHAT_ID", "tgbot_chat_id", int),
    ("MT_TGBOT_PROXY", "tgbot_proxy", str),
    ("MT_FEISHU_WEBHOOKURL", "feishu_webhookurl", str),
    ("MT_FEISHU_SECRET", "feishu_secret", str),
    ("MT_FEISHU_APP_ID", "feishu_app_id", str),
    ("MT_FEISHU_APP_SECRET", "feishu_app_secret", str),
    ("MT_FEISHU_RECEIVE_ID", "feishu_receive_id", str),
    ("MT_NTFY_URL", "ntfy_url", str),
    ("MT_NTFY_TOPIC", "ntfy_topic", str),
    ("MT_NTFY_USER", "ntfy_user", str),
    ("MT_NTFY_PASSWORD", "ntfy_password", str),
    ("MT_NTFY_TOKEN", "ntfy_token", str),
    ("MT_TIME_OUT", "timeout", int),
    ("MT_DB_PATH", "db_path", str),
    ("MT_VERSION", "version", str),
    ("MT_WEB_VERSION", "web_version", str),
    ("MT_COOKIE_MODE", "cookie_mode", str),
]


def _bool_env(name: str) -> bool:
    """将青龙环境变量转为布尔值：1/true/yes -> True"""
    v = os.getenv(name, "")
    return v.strip().lower() in ("1", "true", "yes")


def parse_accounts() -> list:
    """
    解析多账号环境变量。
    用 & 分割每个 MT_* 变量，按位置组合成多个账号的配置字典。
    如果只有一个账号（无 &），返回单元素列表。
    """
    raw = {}

    for env_name, attr_name, cast in ENV_MAP:
        val = os.getenv(env_name, "")
        parts = val.split("&") if val else [""]
        raw[attr_name] = {"env_name": env_name, "parts": [cast(p) if p else (0 if cast is int else "") for p in parts]}

    # 计算账号数：取最长的拆分数量
    account_count = 1
    for item in raw.values():
        account_count = max(account_count, len(item["parts"]))

    # 校验：每个有值的字段，拆分数量要么是 1 要么是 account_count
    for item in raw.values():
        parts = item["parts"]
        if len(parts) > 1 and len(parts) != account_count:
            msg = (f"环境变量 {item['env_name']} 拆分数量 ({len(parts)}) "
                   f"与账号总数 ({account_count}) 不一致，请检查 & 分隔符数量")
            log_info(msg)
            raise SystemExit(msg)

    accounts = []
    for i in range(account_count):
        acc = {}
        for attr_name, item in raw.items():
            parts = item["parts"]
            acc[attr_name] = parts[i] if len(parts) > 1 else parts[0]
        accounts.append(acc)

    return accounts


def build_config(acc: dict, skip_cache: bool = False) -> Config:
    """根据账号字典构造 Config 对象"""
    return Config(
        username=acc.get("username", ""),
        password=acc.get("password", ""),
        totpsecret=acc.get("totpsecret", ""),
        proxy=acc.get("proxy", ""),
        qqpush=acc.get("qqpush", ""),
        qqpush_token=acc.get("qqpush_token", ""),
        m_team_auth=acc.get("m_team_auth", ""),
        ua=acc.get("ua") or Config.ua,
        api_host=acc.get("api_host") or "api.m-team.io",
        referer=acc.get("referer") or "https://kp.m-team.cc/",
        wxcorpid=acc.get("wxcorpid", ""),
        wxagentsecret=acc.get("wxagentsecret", ""),
        wxagentid=acc.get("wxagentid", 0),
        wxuserid=acc.get("wxuserid", "@all"),
        timeout=acc.get("timeout", 60),
        db_path=acc.get("db_path") or "/data/cookie.db",
        version=acc.get("version") or "1.1.4",
        web_version=acc.get("web_version") or "1140",
        m_team_did=acc.get("m_team_did", ""),
        ding_talk_robot_webhook_token=acc.get("ding_talk_robot_webhook_token", ""),
        ding_talk_robot_secret=acc.get("ding_talk_robot_secret", ""),
        ding_talk_robot_at_mobiles=acc.get("ding_talk_robot_at_mobiles", ""),
        tgbot_token=acc.get("tgbot_token", ""),
        tgbot_chat_id=acc.get("tgbot_chat_id", 0),
        tgbot_proxy=acc.get("tgbot_proxy", ""),
        feishu_webhookurl=acc.get("feishu_webhookurl", ""),
        feishu_secret=acc.get("feishu_secret", ""),
        feishu_app_id=acc.get("feishu_app_id", ""),
        feishu_app_secret=acc.get("feishu_app_secret", ""),
        feishu_receive_id=acc.get("feishu_receive_id", ""),
        ntfy_url=acc.get("ntfy_url", ""),
        ntfy_topic=acc.get("ntfy_topic", ""),
        ntfy_user=acc.get("ntfy_user", ""),
        ntfy_password=acc.get("ntfy_password", ""),
        ntfy_token=acc.get("ntfy_token", ""),
        cookie_mode=acc.get("cookie_mode", "normal"),
        skip_cache=skip_cache,
    )


def validate_account(acc: dict, index: int) -> None:
    label = f"账号 {index + 1}"
    if acc.get("m_team_auth"):
        return
    missing = [name for name in ("username", "password", "totpsecret") if not acc.get(name)]
    if missing:
        readable = ", ".join(f"MT_{name.upper()}" for name in missing)
        raise SystemExit(f"{label} 缺少必要配置: {readable}；或配置 MT_M_TEAM_AUTH")


def print_config_summary(accounts: list, skip_cache: bool, dry_run: bool) -> None:
    log_info(f"SKIP_CACHE={skip_cache}, DRY_RUN={dry_run}")
    for i, acc in enumerate(accounts):
        log_info(
            f"账号 {i + 1}: "
            f"has_username={bool(acc.get('username'))}, "
            f"has_password={bool(acc.get('password'))}, "
            f"has_totpsecret={bool(acc.get('totpsecret'))}, "
            f"has_m_team_auth={bool(acc.get('m_team_auth'))}, "
            f"db_path={acc.get('db_path') or '/data/cookie.db'}"
        )


def run_one_account(acc: dict, index: int, total: int, skip_cache: bool) -> bool:
    """运行单个账号的签到流程，返回是否成功"""
    label = f"账号 {index+1}/{total}"
    if acc.get("username"):
        label += f" ({acc['username']})"
    log_info(f"--- {label} 开始 ---")

    cfg = build_config(acc, skip_cache=skip_cache)
    try:
        job = JobServer(cfg)
        job.run_once()
        log_info(f"--- {label} 成功 ---")
        return True
    except Exception as e:
        log_info(f"--- {label} 失败: {e} ---")
        return False


def main():
    log_info("青龙面板 m-team 保活脚本启动 (ql_mtlogin.py)")

    accounts = parse_accounts()
    if not accounts or not any(any(v not in ("", 0) for v in acc.values()) for acc in accounts):
        log_info("未检测到任何账号配置，请设置 MT_USERNAME / MT_PASSWORD / MT_TOTPSECRET 环境变量")
        sys.exit(1)

    log_info(f"检测到 {len(accounts)} 个账号")

    skip_cache = _bool_env("MT_SKIP_CACHE")
    verbose_config = _bool_env("MT_VERBOSE_CONFIG")
    dry_run = _bool_env("MT_DRY_RUN")

    for i, acc in enumerate(accounts):
        validate_account(acc, i)

    if verbose_config:
        print_config_summary(accounts, skip_cache, dry_run)

    if dry_run:
        log_info("MT_DRY_RUN=1，仅验证青龙环境变量解析，不执行网络请求")
        return

    success_count = 0
    for i, acc in enumerate(accounts):
        if i > 0:
            wait_sec = 3
            log_info(f"等待 {wait_sec} 秒后处理下一个账号...")
            time.sleep(wait_sec)
        if run_one_account(acc, i, len(accounts), skip_cache):
            success_count += 1

    log_info(f"全部任务完成: {success_count}/{len(accounts)} 个账号成功")
    if success_count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
