import os
from dataclasses import dataclass
from typing import Mapping, Optional

import requests

try:
    from pypushdeer import PushDeer
except ImportError:  # Push notifications are optional.
    PushDeer = None


COOKIE_ENV_BY_DOMAIN = (
    ("glados.cloud", "GLADOS_CLOUD_COOKIE"),
    ("railgun.info", "RAILGUN_INFO_COOKIE"),
)
REQUEST_TIMEOUT = 20


class CheckinError(RuntimeError):
    """A safe, user-facing check-in failure."""


@dataclass(frozen=True)
class CheckinResult:
    domain: str
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


def configured_sites(environ: Mapping[str, str]):
    """Return only explicitly configured domain-cookie pairs."""
    sites = []
    for domain, variable in COOKIE_ENV_BY_DOMAIN:
        cookie = environ.get(variable, "").strip()
        if cookie:
            sites.append((domain, cookie))
    return sites


def checkin_site(domain, cookie, session=requests):
    """Validate one cookie, then send at most one check-in request."""
    supported_domains = {item[0] for item in COOKIE_ENV_BY_DOMAIN}
    if domain not in supported_domains:
        raise CheckinError(f"不支持的域名：{domain}")
    if not cookie.strip():
        raise CheckinError(f"{domain} Cookie 为空")

    origin = f"https://{domain}"
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

    # Validate authentication first. An invalid cookie must never reach POST.
    try:
        status_response = session.get(
            f"{origin}/api/user/status",
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        status_response.raise_for_status()
    except requests.RequestException as error:
        raise CheckinError(f"{domain} 状态请求失败：{error}") from error

    status_payload = _response_dict(status_response, f"{domain} 状态接口")
    state_data = status_payload.get("data")
    if not isinstance(state_data, dict) or not state_data:
        message = str(status_payload.get("message") or "未返回账户数据")
        raise CheckinError(f"{domain} 认证失败：{message}")

    # No automatic retry: a retry could duplicate a state-changing request.
    try:
        checkin_response = session.post(
            f"{origin}/api/user/checkin",
            headers=headers,
            data={"token": domain},
            timeout=REQUEST_TIMEOUT,
        )
        checkin_response.raise_for_status()
    except requests.RequestException as error:
        raise CheckinError(f"{domain} 签到请求失败：{error}") from error

    checkin_payload = _response_dict(checkin_response, f"{domain} 签到接口")
    code = _number(checkin_payload.get("code"), default=-2)
    message = str(checkin_payload.get("message") or "")
    if code == 0:
        status = "签到成功"
    elif code == 1:
        status = "今日已经签到"
    else:
        raise CheckinError(f"{domain} 签到失败：{message or '未知错误'}")

    return CheckinResult(
        domain=domain,
        email=str(state_data.get("email") or ""),
        status=status,
        points=_number(checkin_payload.get("points")),
        leftdays=(
            _number(state_data.get("leftDays"))
            if state_data.get("leftDays") not in (None, "")
            else None
        ),
        message=message,
    )


def main(environ=None):
    environ = os.environ if environ is None else environ
    sites = configured_sites(environ)
    if not sites:
        print("未配置 GLADOS_CLOUD_COOKIE 或 RAILGUN_INFO_COOKIE")
        raise SystemExit(1)

    results = []
    failures = []
    for domain, cookie in sites:
        try:
            results.append(checkin_site(domain, cookie))
        except CheckinError as error:
            failures.append(str(error))

    detail_lines = []
    for result in results:
        account = result.email or result.domain
        days = f"{result.leftdays} 天" if result.leftdays is not None else "未知"
        detail_lines.append(
            f"{account}: {result.status}，积分 +{result.points}，剩余 {days}"
        )
    detail_lines.extend(f"失败：{failure}" for failure in failures)

    title = f"自动签到：成功/重复 {len(results)}，失败 {len(failures)}"
    content = "\n".join(detail_lines)
    print(title)
    print(content)

    sendkey = environ.get("SENDKEY", "").strip()
    if sendkey and PushDeer is not None:
        try:
            PushDeer(pushkey=sendkey).send_text(title, desp=content)
        except Exception as error:
            print(f"推送通知失败：{error}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
