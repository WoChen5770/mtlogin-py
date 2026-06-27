#!/usr/bin/env python3
# cron: 12 */6 * * *
# new Env('M-Team 保活')
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
  MT_TIME_OUT         超时（秒）
  MT_DB_PATH          cookie 持久化路径
  MT_COOKIE_MODE      cookie 模式 (normal/strict)
  MT_SKIP_CACHE       跳过缓存 (1/true)
  MT_VERBOSE_CONFIG   打印启动配置 (1/true)
"""

import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

def resolve_core_path() -> Path:
    candidates = [Path(__file__).resolve().parent / "mtlogin"]
    ql_repo_dir = Path(os.getenv("QL_REPO_DIR", "/ql/data/repo"))
    if ql_repo_dir.exists():
        candidates.extend(ql_repo_dir.glob("**/mtlogin"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("无法加载核心脚本 mtlogin，请确认订阅已拉取完整仓库")


CORE_PATH = resolve_core_path()
_loader = SourceFileLoader("mtlogin_core", str(CORE_PATH))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
if _spec is None:
    raise RuntimeError(f"无法加载核心脚本: {CORE_PATH}")
mtlogin_core = importlib.util.module_from_spec(_spec)
sys.modules[_loader.name] = mtlogin_core
_loader.exec_module(mtlogin_core)

Config = mtlogin_core.Config
MTClient = mtlogin_core.MTClient
log_info = mtlogin_core.log_info


DEFAULT_QL_DB_PATH = "/ql/data/db/mt/cookie.db"


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


def fail_with_notify(message: str) -> None:
    log_info(message)
    send_ql_notify("M-Team 保活异常", message)
    raise SystemExit(message)


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
            fail_with_notify(msg)

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
        qqpush="",
        qqpush_token="",
        m_team_auth=acc.get("m_team_auth", ""),
        ua=acc.get("ua") or Config.ua,
        api_host=acc.get("api_host") or "api.m-team.io",
        referer=acc.get("referer") or "https://kp.m-team.cc/",
        wxcorpid="",
        wxagentsecret="",
        wxagentid=0,
        wxuserid="@all",
        timeout=acc.get("timeout", 60),
        db_path=acc.get("db_path") or DEFAULT_QL_DB_PATH,
        version=acc.get("version") or "1.1.4",
        web_version=acc.get("web_version") or "1140",
        m_team_did=acc.get("m_team_did", ""),
        ding_talk_robot_webhook_token="",
        ding_talk_robot_secret="",
        ding_talk_robot_at_mobiles="",
        tgbot_token="",
        tgbot_chat_id=0,
        tgbot_proxy="",
        feishu_webhookurl="",
        feishu_secret="",
        feishu_app_id="",
        feishu_app_secret="",
        feishu_receive_id="",
        ntfy_url="",
        ntfy_topic="",
        ntfy_user="",
        ntfy_password="",
        ntfy_token="",
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
        fail_with_notify(f"{label} 缺少必要配置: {readable}；或配置 MT_M_TEAM_AUTH")


def print_config_summary(accounts: list, skip_cache: bool, dry_run: bool) -> None:
    log_info(f"SKIP_CACHE={skip_cache}, DRY_RUN={dry_run}")
    for i, acc in enumerate(accounts):
        log_info(
            f"账号 {i + 1}: "
            f"has_username={bool(acc.get('username'))}, "
            f"has_password={bool(acc.get('password'))}, "
            f"has_totpsecret={bool(acc.get('totpsecret'))}, "
            f"has_m_team_auth={bool(acc.get('m_team_auth'))}, "
            f"db_path={acc.get('db_path') or DEFAULT_QL_DB_PATH}"
        )


def send_ql_notify(title: str, content: str) -> None:
    """调用青龙内置 notify.py 发送通知；本地运行时不存在则只记录日志。"""
    notify_paths = [
        Path("/ql/data/scripts/notify.py"),
        Path("/ql/scripts/notify.py"),
        Path(__file__).resolve().parent / "notify.py",
    ]
    notify_file = next((path for path in notify_paths if path.exists()), None)
    if not notify_file:
        log_info("未找到青龙 notify.py，跳过青龙面板通知")
        return

    try:
        sys.path.insert(0, str(notify_file.parent))
        from notify import send  # type: ignore

        send(title, content)
        log_info("青龙面板通知发送完成")
    except Exception as exc:
        log_info(f"青龙面板通知发送失败: {exc}")



def format_bytes(value: int) -> str:
    sign = "-" if value < 0 else ""
    size = abs(float(value))
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    unit = units[0]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            break
        size /= 1024
    if unit == "B":
        return f"{sign}{int(size)} {unit}"
    return f"{sign}{size:.2f} {unit}"


def format_number_delta(value: float) -> str:
    sign = "+" if value > 0 else ""
    if abs(value - round(value)) < 0.000001:
        return f"{sign}{int(round(value))}"
    return f"{sign}{value:.2f}"


def format_duration(seconds: int) -> str:
    if seconds < 0:
        seconds = 0
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}天")
    if hours:
        parts.append(f"{hours}小时")
    if minutes:
        parts.append(f"{minutes}分钟")
    if seconds or not parts:
        parts.append(f"{seconds}秒")
    return "".join(parts)


def parse_snapshot_time(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    return None


def snapshot_key(name: str, index: int) -> str:
    safe_name = name or f"account-{index + 1}"
    return f"ql-mtlogin-snapshot:{safe_name}"


def load_snapshot(client, name: str, index: int) -> dict:
    raw = client.store.get(snapshot_key(name, index))
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def save_snapshot(client, key_name: str, snapshot: dict, index: int) -> None:
    client.store.put(snapshot_key(key_name, index), json.dumps(snapshot, ensure_ascii=False))


def build_account_result(client, previous: dict, index: int, run_at: str) -> dict:
    name = client.username or f"账号{index + 1}"
    current = {
        "username": name,
        "uploaded_bytes": client.uploaded_bytes,
        "downloaded_bytes": client.downloaded_bytes,
        "bonus": client.bonus_value,
        "run_at": run_at,
    }
    result = {
        "ok": True,
        "username": name,
        "uploaded": client.uploaded,
        "downloaded": client.downloaded,
        "bonus": client.bonus,
        "previous_run_at": previous.get("run_at") or client.last_browse or "无记录",
        "current_run_at": run_at,
        "first_snapshot": not previous,
        "snapshot": current,
    }
    if previous:
        previous_time = parse_snapshot_time(str(previous.get("run_at", "")))
        current_time = parse_snapshot_time(run_at)
        if previous_time and current_time:
            result["elapsed"] = format_duration(int((current_time - previous_time).total_seconds()))
        else:
            result["elapsed"] = "未知"
        result["uploaded_delta"] = client.uploaded_bytes - int(previous.get("uploaded_bytes", 0) or 0)
        result["downloaded_delta"] = client.downloaded_bytes - int(previous.get("downloaded_bytes", 0) or 0)
        result["bonus_delta"] = client.bonus_value - float(previous.get("bonus", 0) or 0)
    else:
        result["elapsed"] = "首次记录"
        result["uploaded_delta"] = None
        result["downloaded_delta"] = None
        result["bonus_delta"] = None
    return result


def build_ql_notify_content(results: list) -> tuple:
    total = len(results)
    success_count = sum(1 for item in results if item.get("ok"))
    failed_count = total - success_count
    title = "M-Team 保活成功" if failed_count == 0 else "M-Team 保活异常"
    lines = [f"总账号: {total}", f"成功: {success_count}", f"失败: {failed_count}"]
    for idx, item in enumerate(results, 1):
        lines.append("")
        name = item.get("username") or f"账号{idx}"
        if not item.get("ok"):
            lines.extend([f"账号 {idx}: {name}", "状态: 失败", f"错误: {item.get('error', '未知错误')}"])
            continue
        lines.extend([
            f"账号 {idx}: {name}",
            "状态: 成功",
            f"上传量: {item['uploaded']}",
            f"下载量: {item['downloaded']}",
            f"魔力值: {item['bonus']}",
            f"上次保活时间: {item['previous_run_at']}",
            f"本次保活时间: {item['current_run_at']}",
        ])
        if item.get("first_snapshot"):
            lines.append("距离上次保活: 首次记录")
        else:
            lines.extend([
                f"距离上次保活: {item.get('elapsed', '未知')}",
                f"上传量变化: {format_bytes(item['uploaded_delta'])}",
                f"下载量变化: {format_bytes(item['downloaded_delta'])}",
                f"魔力值变化: {format_number_delta(item['bonus_delta'])}",
            ])
    return title, "\n".join(lines)


def run_one_account(acc: dict, index: int, total: int, skip_cache: bool) -> dict:
    label = f"账号 {index + 1}/{total}"
    if acc.get("username"):
        label += f" ({acc['username']})"
    log_info(f"--- {label} 开始 ---")

    cfg = build_config(acc, skip_cache=skip_cache)
    client = MTClient(cfg)
    previous_name = acc.get("username") or f"account-{index + 1}"
    previous = load_snapshot(client, previous_name, index)
    try:
        if not cfg.m_team_auth and not cfg.m_team_did:
            client.login()
        client.check()
    except RuntimeError as exc:
        if "Full authentication is required" not in str(exc):
            log_info(f"--- {label} 失败: {exc} ---")
            return {"ok": False, "username": acc.get("username") or f"账号{index + 1}", "error": str(exc)}
        log_info("Cached token expired, retrying with fresh login (username+password+TOTP)")
        try:
            client.login(force=True)
            client.check()
        except Exception as retry_exc:
            log_info(f"--- {label} 失败: {retry_exc} ---")
            return {"ok": False, "username": acc.get("username") or f"账号{index + 1}", "error": str(retry_exc)}
    except Exception as exc:
        log_info(f"--- {label} 失败: {exc} ---")
        return {"ok": False, "username": acc.get("username") or f"账号{index + 1}", "error": str(exc)}

    run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result = build_account_result(client, previous, index, run_at)
    save_snapshot(client, previous_name, result["snapshot"], index)
    log_info(f"--- {label} 成功 ---")
    return result

def main():
    log_info("青龙面板 m-team 保活脚本启动 (ql_mtlogin.py)")

    accounts = parse_accounts()
    if not accounts or not any(any(v not in ("", 0) for v in acc.values()) for acc in accounts):
        fail_with_notify("未检测到任何账号配置，请设置 MT_USERNAME / MT_PASSWORD / MT_TOTPSECRET 环境变量")

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
        dry_results = []
        for i, acc in enumerate(accounts):
            name = acc.get("username") or f"账号{i + 1}"
            dry_results.append({
                "ok": True,
                "username": name,
                "uploaded": "0.00 Gb",
                "downloaded": "0.00 Gb",
                "bonus": "0",
                "previous_run_at": "dry-run",
                "current_run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "first_snapshot": True,
                "elapsed": "首次记录",
            })
        title, content = build_ql_notify_content(dry_results)
        send_ql_notify(title, content)
        return

    results = []
    for i, acc in enumerate(accounts):
        if i > 0:
            wait_sec = 3
            log_info(f"等待 {wait_sec} 秒后处理下一个账号...")
            time.sleep(wait_sec)
        results.append(run_one_account(acc, i, len(accounts), skip_cache))

    success_count = sum(1 for item in results if item.get("ok"))
    log_info(f"全部任务完成: {success_count}/{len(accounts)} 个账号成功")
    title, content = build_ql_notify_content(results)
    send_ql_notify(title, content)
    if success_count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
