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
    def __init__(self, status_response, checkin_response=None):
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

    def test_success_validates_before_single_post(self):
        session = FakeSession(
            self.valid_status(),
            FakeResponse({"code": 0, "message": "Checkin! Got", "points": 10}),
        )

        result = checkin.checkin_site("railgun.info", "secret", session=session)

        self.assertEqual(result.status, "签到成功")
        self.assertEqual(result.points, 10)
        self.assertEqual(result.leftdays, 12)
        self.assertEqual([call[0] for call in session.calls], ["GET", "POST"])
        self.assertEqual(session.calls[1][2]["data"], {"token": "railgun.info"})

    def test_repeat_is_a_successful_result(self):
        session = FakeSession(
            self.valid_status(),
            FakeResponse({"code": 1, "message": "Checkin Repeats!", "points": 0}),
        )

        result = checkin.checkin_site("glados.cloud", "secret", session=session)

        self.assertEqual(result.status, "今日已经签到")
        self.assertEqual([call[0] for call in session.calls], ["GET", "POST"])

    def test_invalid_cookie_never_sends_post(self):
        session = FakeSession(FakeResponse({"code": -2, "message": "No permission"}))

        with self.assertRaisesRegex(checkin.CheckinError, "认证失败"):
            checkin.checkin_site("railgun.info", "expired", session=session)

        self.assertEqual([call[0] for call in session.calls], ["GET"])

    def test_malformed_status_never_sends_post(self):
        session = FakeSession(FakeResponse(json_error=True))

        with self.assertRaisesRegex(checkin.CheckinError, "不是 JSON"):
            checkin.checkin_site("glados.cloud", "secret", session=session)

        self.assertEqual([call[0] for call in session.calls], ["GET"])

    def test_explicit_secrets_do_not_cross_domains(self):
        sites = checkin.configured_sites(
            {
                "COOKIES": "legacy-cookie-is-ignored",
                "RAILGUN_INFO_COOKIE": " railgun-cookie ",
            }
        )

        self.assertEqual(sites, [("railgun.info", "railgun-cookie")])


if __name__ == "__main__":
    unittest.main()
