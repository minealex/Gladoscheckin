import os

import requests
from pypushdeer import PushDeer


DOMAINS = ("glados.cloud", "railgun.info")


def checkin(cookie):
    """Try the supported domains and return the first authenticated result."""
    useragent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/102.0.0.0 Safari/537.36"
    )

    for domain in DOMAINS:
        origin = f"https://{domain}"
        headers = {
            "cookie": cookie,
            "referer": f"{origin}/console/checkin",
            "origin": origin,
            "user-agent": useragent,
        }

        try:
            checkin_response = requests.post(
                f"{origin}/api/user/checkin",
                headers=headers,
                data={"token": domain},
                timeout=30,
            )
            checkin_response.raise_for_status()
            checkin_data = checkin_response.json()
        except (requests.RequestException, ValueError) as error:
            print(f"{domain}: request failed: {error}")
            continue

        code = checkin_data.get("code", -2)
        message = str(checkin_data.get("message") or "")
        if code not in (0, 1):
            print(f"{domain}: {message or 'authentication failed'}")
            continue

        state_data = {}
        try:
            state_response = requests.get(
                f"{origin}/api/user/status", headers=headers, timeout=30
            )
            if state_response.ok:
                state_data = state_response.json().get("data") or {}
        except (requests.RequestException, ValueError, AttributeError):
            pass

        leftdays_value = state_data.get("leftDays")
        leftdays = (
            int(float(leftdays_value))
            if leftdays_value not in (None, "")
            else None
        )

        return {
            "code": code,
            "domain": domain,
            "email": state_data.get("email", ""),
            "leftdays": leftdays,
            "message": message,
            "points": checkin_data.get("points", 0),
        }

    return None


def main():
    sendkey = os.environ.get("SENDKEY", "")
    cookies = [
        cookie.strip()
        for cookie in os.environ.get("COOKIES", "").split("&")
        if cookie.strip()
    ]

    if not cookies:
        print("未找到 COOKIES Secret")
        raise SystemExit(1)

    success = 0
    repeats = 0
    failures = 0
    details = []

    for index, cookie in enumerate(cookies, 1):
        result = checkin(cookie)
        if result is None:
            failures += 1
            details.append(f"账号 {index}: 认证失败，请更新 COOKIES Secret")
            continue

        if result["code"] == 0:
            success += 1
            status = f"签到成功，积分 +{result['points']}"
        else:
            repeats += 1
            status = "今日已经签到"

        days = f"{result['leftdays']} 天" if result["leftdays"] is not None else "未知"
        account = result["email"] or f"账号 {index}"
        details.append(
            f"{account}: {status}，剩余 {days}，域名 {result['domain']}"
        )

    title = f"Railgun 签到：成功 {success}，重复 {repeats}，失败 {failures}"
    content = "\n".join(details)
    print(title)
    print(content)

    if sendkey:
        PushDeer(pushkey=sendkey).send_text(title, desp=content)
    else:
        print("未设置 SENDKEY，跳过推送")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
