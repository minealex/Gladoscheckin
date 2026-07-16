import unittest

import requests

import checkin


class FakeResponse:
    def __init__(self, payload=None, status_code=200, json_error=False):
        self.payload = payload
        self.status_code = status_code
        self.json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self.json_error:
            raise ValueError("invalid json")
        return self.payload


class FakeSession:
    def __init__(self, status_response=None, checkin_response=None):
        self.status_response = status_response
        self.checkin_response = checkin_response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.status_response

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.checkin_response


class CheckinTests(unittest.TestCase):
    def valid_status(self):
        return FakeResponse(
            {"code": 0, "data": {"email": "user@example.com", "leftDays": "12.8"}}
        )

    def test_success_validates_before_exactly_one_post(self):
        session = FakeSession(
            self.valid_status(),
            FakeResponse({"code": 0, "message": "Checkin! Got", "points": 10}),
        )

        result = checkin.checkin_site("secret", session=session)

        self.assertEqual(result.status, "签到成功")
        self.assertEqual(result.points, 10)
        self.assertEqual(result.leftdays, 12)
        self.assertEqual([call[0] for call in session.calls], ["GET", "POST"])
        self.assertTrue(all(checkin.SITE_DOMAIN in call[1] for call in session.calls))
        self.assertEqual(
            session.calls[1][2]["data"], {"token": checkin.SITE_DOMAIN}
        )

    def test_repeat_is_successful_without_retry(self):
        session = FakeSession(
            self.valid_status(),
            FakeResponse({"code": 1, "message": "Checkin Repeats!", "points": 0}),
        )

        result = checkin.checkin_site("secret", session=session)

        self.assertEqual(result.status, "今日已经签到")
        self.assertEqual([call[0] for call in session.calls], ["GET", "POST"])

    def test_invalid_cookie_never_sends_post(self):
        session = FakeSession(
            FakeResponse({"code": -2, "message": "No permission"})
        )

        with self.assertRaisesRegex(checkin.CheckinError, "认证失败"):
            checkin.checkin_site("expired", session=session)

        self.assertEqual([call[0] for call in session.calls], ["GET"])

    def test_multiline_cookie_is_rejected_before_network(self):
        session = FakeSession()

        with self.assertRaisesRegex(checkin.CheckinError, "必须是单行"):
            checkin.checkin_site("part-one;\npart-two", session=session)

        self.assertEqual(session.calls, [])

    def test_malformed_status_never_sends_post(self):
        session = FakeSession(FakeResponse(json_error=True))

        with self.assertRaisesRegex(checkin.CheckinError, "不是 JSON"):
            checkin.checkin_site("secret", session=session)

        self.assertEqual([call[0] for call in session.calls], ["GET"])

    def test_failed_post_is_not_retried(self):
        session = FakeSession(self.valid_status(), FakeResponse(status_code=500))

        with self.assertRaisesRegex(checkin.CheckinError, "签到请求失败"):
            checkin.checkin_site("secret", session=session)

        self.assertEqual([call[0] for call in session.calls], ["GET", "POST"])

    def test_cookie_and_cookies_secret_names_are_compatible(self):
        self.assertEqual(
            checkin.cookie_from_environment({"COOKIE": "one", "COOKIES": "two"}),
            "one",
        )
        self.assertEqual(
            checkin.cookie_from_environment({"COOKIES": "two"}),
            "two",
        )


if __name__ == "__main__":
    unittest.main()
