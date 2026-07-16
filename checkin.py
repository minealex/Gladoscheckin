import os
from dataclasses import dataclass
from typing import Mapping, Optional

import requests


SITE_DOMAIN = "glados.cloud"
SITE_LABEL = "GLaDOS"
REQUEST_TIMEOUT = 20
COOKIE_ENV_NAMES = ("SITE_COOKIE", "COOKIE", "COOKIES")


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


def cookie_from_environment(environ: Mapping[str, str]):
    """Support both existing COOKIE and COOKIES repository secrets."""
    for variable in COOKIE_ENV_NAMES:
        cookie = environ.get(variable, "").strip()
        if cookie:
            return cookie
    return ""


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
    try:
        status_response = session.get(
            f"{origin}/api/user/status",
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        status_response.raise_for_status()
    except requests.RequestException as error:
        raise CheckinError(f"状态请求失败：{error}") from error

    status_payload = _response_dict(status_response, "状态接口")
    state_data = status_payload.get("data")
    if not isinstance(state_data, dict) or not state_data:
        message = str(status_payload.get("message") or "未返回账户数据")
        raise CheckinError(f"认证失败：{message}")

    # Deliberately no automatic retry to avoid duplicate check-in requests.
    try:
        checkin_response = session.post(
            f"{origin}/api/user/checkin",
            headers=headers,
            data={"token": SITE_DOMAIN},
            timeout=REQUEST_TIMEOUT,
        )
        checkin_response.raise_for_status()
    except requests.RequestException as error:
        raise CheckinError(f"签到请求失败：{error}") from error

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
    if not cookie:
        print("未配置 COOKIE 或 COOKIES Secret")
        raise SystemExit(1)

    try:
        result = checkin_site(cookie)
    except CheckinError as error:
        print(f"{SITE_LABEL} 签到失败：{error}")
        raise SystemExit(1)

    account = result.email or SITE_DOMAIN
    days = f"{result.leftdays} 天" if result.leftdays is not None else "未知"
    print(
        f"{SITE_LABEL} | {account} | {result.status} | "
        f"积分 +{result.points} | 剩余 {days}"
    )


if __name__ == "__main__":
    main()
