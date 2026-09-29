import base64
import binascii
import gzip
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping, Optional

import requests


SITE_DOMAIN = "glados.cloud"
SITE_LABEL = "GLaDOS"
REQUEST_TIMEOUT = 20
COOKIE_ENV_NAMES = ("SITE_COOKIE", "COOKIE", "COOKIES")

# 只读的状态接口可以安全重试（不改变账号状态）；签到接口保持零重试，
# 避免网络抖动时重复提交签到请求。
STATUS_ATTEMPTS = 3
STATUS_RETRY_WAIT = 5
PUSH_ENV_NAMES = ("SENDKEY",)
PUSH_URL = "https://api2.pushdeer.com/message/push"
PUSH_TIMEOUT = 8
EXPIRY_WARN_DAYS = 7


class CheckinError(RuntimeError):
    """A safe, user-facing check-in failure."""


@dataclass(frozen=True)
class CheckinResult:
    email: str
    status: str
    points: int
    leftdays: Optional[int]
    message: str


def _response_dict(response, label):
    try:
        payload = response.json()
    except ValueError as error:
        raise CheckinError(f"{label}返回的不是 JSON") from error
    if not isinstance(payload, dict):
        raise CheckinError(f"{label}返回格式异常")
    return payload


def _number(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _response_hint(response):
    """Return a short, non-sensitive body snippet for failed requests."""
    if response is None:
        return "无响应内容"
    text = getattr(response, "text", "")
    if not isinstance(text, str) or not text.strip():
        return "无响应内容"
    snippet = " ".join(text.split())[:200]
    return f"响应摘要：{snippet}"


def cookie_from_environment(environ: Mapping[str, str]):
    """Support both existing COOKIE and COOKIES repository secrets."""
    for variable in COOKIE_ENV_NAMES:
        cookie = environ.get(variable, "").strip()
        if cookie:
            return cookie
    return ""


def cookie_source_name(environ: Mapping[str, str]):
    """Report which secret actually supplied the cookie."""
    for variable in COOKIE_ENV_NAMES:
        if environ.get(variable, "").strip():
            return variable
    return ""


def cookie_fingerprint(cookie):
    """Describe a cookie without revealing its value."""
    value = (cookie or "").strip()
    fields = [
        part.split("=", 1)[0].strip()
        for part in value.split(";")
        if "=" in part
    ]
    return {
        "length": len(value),
        "fields": fields,
        "has_session": "koa:sess" in fields,
        "has_signature": "koa:sess.sig" in fields,
        # GLaDOS 在 2026-09 前后把登录会话迁到了 gld:sess；只有旧的
        # koa:sess 时，状态接口会返回 code=-2「没有权限」。
        "has_gld_session": "gld:sess" in fields,
        "has_gld_signature": "gld:sess.sig" in fields,
        "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest()[:8],
    }


def describe_cookie(cookie):
    """One-line, leak-free description used in logs and notifications."""
    fingerprint = cookie_fingerprint(cookie)
    fields = ",".join(fingerprint["fields"][:6]) or "-"
    flags = []
    if not fingerprint["has_gld_session"]:
        flags.append("缺少 gld:sess")
    if not fingerprint["has_gld_signature"]:
        flags.append("缺少 gld:sess.sig")
    suffix = f"（{'，'.join(flags)}）" if flags else ""
    return (
        f"长度 {fingerprint['length']} 字符 | 字段 {fields} | "
        f"指纹 {fingerprint['sha256']}{suffix}"
    )


def _decode_session_value(raw):
    """koa session values are base64 encoded, sometimes url-safe."""
    padded = raw + "=" * (-len(raw) % 4)
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            return decoder(padded)
        except (binascii.Error, ValueError):
            continue
    return None


def _load_session_payload(raw):
    blob = _decode_session_value(raw)
    if not blob:
        return None
    try:
        return json.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        pass
    try:
        return json.loads(gzip.decompress(blob).decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None


# koa-session 自己的会话字段；其余 expire 类字段语义不确定（可能是账号到期时间）。
SESSION_EXPIRY_KEYS = ("_expire", "_maxAge")
UNCLEAR_EXPIRY_KEYS = ("expire", "exp", "expires")


def session_expiry(cookie, now=None):
    """Return (expiry or None, kind).

    kind is "session" when the value comes from koa-session fields,
    "unclear" when it comes from a generic expire field, "missing" otherwise.
    """
    now = datetime.now(timezone.utc) if now is None else now
    for part in (cookie or "").split(";"):
        if "=" not in part:
            continue
        name, raw = part.split("=", 1)
        if name.strip() != "koa:sess":
            continue
        payload = _load_session_payload(raw.strip())
        if not isinstance(payload, dict):
            return None, "missing"
        for keys, kind in (
            (SESSION_EXPIRY_KEYS, "session"),
            (UNCLEAR_EXPIRY_KEYS, "unclear"),
        ):
            for key in keys:
                value = payload.get(key)
                if isinstance(value, bool) or not isinstance(
                    value, (int, float, str)
                ):
                    continue
                try:
                    seconds = float(value)
                except (TypeError, ValueError):
                    continue
                if key == "_maxAge":
                    if seconds <= 0:
                        continue
                    return now + timedelta(seconds=seconds), kind
                if key != "_maxAge" and seconds > 1e11:  # milliseconds
                    seconds /= 1000.0
                if seconds <= 0:
                    continue
                return datetime.fromtimestamp(seconds, tz=timezone.utc), kind
        return None, "missing"
    return None, "missing"


def parse_session_expiry(cookie, now=None):
    """Extract the session expiry from koa:sess, or None when unavailable."""
    return session_expiry(cookie, now)[0]


def expiry_summary(cookie, now=None):
    """Human readable expiry line; never guesses when parsing fails."""
    now = datetime.now(timezone.utc) if now is None else now
    expiry, kind = session_expiry(cookie, now)
    if expiry is None:
        return "未能从 Cookie 解析有效期（不影响签到，仅无法提前预警）"
    remaining_days = (expiry - now).total_seconds() / 86400.0
    stamp = expiry.astimezone().strftime("%Y-%m-%d %H:%M")
    if remaining_days <= 0:
        if kind == "session":
            return f"会话已于 {stamp} 过期（{abs(remaining_days):.1f} 天前）"
        return f"Cookie 内到期字段为 {stamp}，已过期 {abs(remaining_days):.1f} 天"
    if kind == "session":
        return f"会话有效期至 {stamp}，剩余 {remaining_days:.1f} 天"
    return (
        f"Cookie 内到期字段为 {stamp}（剩余 {remaining_days:.1f} 天；"
        "该字段可能是账号到期时间，不代表会话有效期）"
    )


def expiry_alert(cookie, now=None):
    """Return an Actions annotation when the cookie session is expired/expiring.

    Only koa-session fields are trusted; a generic expire field can mean
    account expiry and must not raise a false alarm.
    """
    now = datetime.now(timezone.utc) if now is None else now
    expiry, kind = session_expiry(cookie, now)
    if expiry is None or kind != "session":
        return ""
    remaining_days = (expiry - now).total_seconds() / 86400.0
    if remaining_days <= 0:
        return (
            "::error::Cookie 已过期，请重新登录 GLaDOS 复制新的 Cookie "
            "并更新仓库 Secret（COOKIE / COOKIES）"
        )
    if remaining_days <= EXPIRY_WARN_DAYS:
        return (
            f"::warning::Cookie 将在 {remaining_days:.1f} 天后过期，"
            "建议尽快更新仓库 Secret（COOKIE / COOKIES）"
        )
    return ""


def send_push(sendkey, title, content, session=requests):
    """Best-effort PushDeer notification; failures never break the job."""
    if not sendkey:
        return False
    try:
        response = session.post(
            PUSH_URL,
            data={"pushkey": sendkey, "text": title, "desp": content},
            timeout=PUSH_TIMEOUT,
        )
    except requests.RequestException as error:
        print(f"推送失败（不影响签到结果）：{error}")
        return False
    status = getattr(response, "status_code", 0)
    if status >= 400:
        print(f"推送失败（不影响签到结果）：HTTP {status}")
        return False
    print("推送已发送")
    return True


def _request_status(session, url, headers):
    """GET the read-only status endpoint with bounded retries."""
    response = None
    for attempt in range(1, STATUS_ATTEMPTS + 1):
        try:
            response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            if attempt >= STATUS_ATTEMPTS:
                raise CheckinError(
                    f"状态请求失败：{error}；{_response_hint(response)}"
                ) from error
            print(
                f"状态请求第 {attempt} 次失败（{error}），"
                f"{STATUS_RETRY_WAIT} 秒后重试"
            )
            time.sleep(STATUS_RETRY_WAIT)
    raise CheckinError("状态请求失败：未知错误")


def checkin_site(cookie, session=requests):
    """Validate authentication, then send at most one check-in request."""
    cookie = cookie.strip()
    if not cookie:
        raise CheckinError("Cookie 为空")
    if "\r" in cookie or "\n" in cookie:
        raise CheckinError("Cookie 必须是单行，键值之间使用分号和空格")

    origin = f"https://{SITE_DOMAIN}"
    headers = {
        "cookie": cookie,
        "referer": f"{origin}/console/checkin",
        "origin": origin,
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    }

    # A read-only request validates the session before any state-changing call.
    status_response = _request_status(session, f"{origin}/api/user/status", headers)

    status_payload = _response_dict(status_response, "状态接口")
    state_data = status_payload.get("data")
    if not isinstance(state_data, dict) or not state_data:
        message = str(status_payload.get("message") or "未返回账户数据")
        status_code = getattr(status_response, "status_code", None)
        expiry, kind = session_expiry(cookie)
        if not cookie_fingerprint(cookie)["has_gld_session"]:
            reason = (
                "Cookie 缺少 gld:sess（站点现已改用 gld:sess 鉴权，"
                "只带旧的 koa:sess 会被拒绝）"
            )
        elif kind == "session" and expiry is not None and expiry <= datetime.now(
            timezone.utc
        ):
            reason = "Cookie 会话已过期"
        else:
            reason = (
                "Cookie 未被服务端接受（会话已作废，或复制时缺少/截断了 "
                "koa:sess、koa:sess.sig）"
            )
        raise CheckinError(
            f"认证失败：{message}（HTTP {status_code}；{reason}；"
            f"{describe_cookie(cookie)}；{expiry_summary(cookie)}；"
            f"请重新登录 {origin} 并完整复制 Cookie，更新仓库 Secret "
            "COOKIE / COOKIES）"
        )

    # Deliberately no automatic retry to avoid duplicate check-in requests.
    checkin_response = None
    try:
        checkin_response = session.post(
            f"{origin}/api/user/checkin",
            headers=headers,
            data={"token": SITE_DOMAIN},
            timeout=REQUEST_TIMEOUT,
        )
        checkin_response.raise_for_status()
    except requests.RequestException as error:
        raise CheckinError(
            f"签到请求失败：{error}；{_response_hint(checkin_response)}"
        ) from error

    checkin_payload = _response_dict(checkin_response, "签到接口")
    code = _number(checkin_payload.get("code"), default=-2)
    message = str(checkin_payload.get("message") or "")
    if code == 0:
        status = "签到成功"
    elif code == 1:
        status = "今日已经签到"
    else:
        raise CheckinError(f"签到失败：{message or '未知错误'}")

    leftdays_value = state_data.get("leftDays")
    return CheckinResult(
        email=str(state_data.get("email") or ""),
        status=status,
        points=_number(checkin_payload.get("points")),
        leftdays=(
            _number(leftdays_value)
            if leftdays_value not in (None, "")
            else None
        ),
        message=message,
    )


def main(environ=None):
    environ = os.environ if environ is None else environ
    cookie = cookie_from_environment(environ)
    sendkey = ""
    for variable in PUSH_ENV_NAMES:
        sendkey = environ.get(variable, "").strip()
        if sendkey:
            break

    if not cookie:
        message = (
            "未配置 Cookie Secret：请在仓库 Settings -> Secrets and variables -> "
            "Actions 中设置 COOKIE 或 COOKIES"
        )
        print(f"{SITE_LABEL} 签到失败：{message}")
        send_push(sendkey, f"{SITE_LABEL} 签到失败", message)
        raise SystemExit(1)

    print(f"Cookie 来源：{cookie_source_name(environ) or '未识别'}"
          f" | {describe_cookie(cookie)}")
    print(f"Cookie 有效期：{expiry_summary(cookie)}")
    alert = expiry_alert(cookie)
    if alert:
        print(alert)

    try:
        result = checkin_site(cookie)
    except CheckinError as error:
        message = f"{SITE_LABEL} 签到失败：{error}"
        print(message)
        send_push(sendkey, f"{SITE_LABEL} 签到失败", message)
        raise SystemExit(1)

    account = result.email or SITE_DOMAIN
    days = f"{result.leftdays} 天" if result.leftdays is not None else "未知"
    line = (
        f"{SITE_LABEL} | {account} | {result.status} | "
        f"积分 +{result.points} | 剩余 {days}"
    )
    print(line)
    send_push(sendkey, f"{SITE_LABEL} {result.status}", line)


if __name__ == "__main__":
    main()
