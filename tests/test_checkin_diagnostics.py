import base64
import json
import unittest
from datetime import datetime, timedelta, timezone

import requests

import checkin


NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)


def session_cookie(payload):
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return f"koa:sess={encoded}; koa:sess.sig=signature"


class RecordingSession:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return type("Response", (), {"status_code": self.status_code})()


class CookieDiagnosticsTests(unittest.TestCase):
    def test_fingerprint_reports_session_fields(self):
        fingerprint = checkin.cookie_fingerprint(session_cookie({"expire": 1}))

        self.assertTrue(fingerprint["has_session"])
        self.assertTrue(fingerprint["has_signature"])
        self.assertEqual(len(fingerprint["sha256"]), 8)

    def test_fingerprint_flags_missing_session(self):
        fingerprint = checkin.cookie_fingerprint("foo=bar")

        self.assertFalse(fingerprint["has_session"])
        self.assertIn("缺少 koa:sess", checkin.describe_cookie("foo=bar"))

    def test_description_never_leaks_the_cookie_value(self):
        secret = session_cookie({"token": "super-secret-value"})

        self.assertNotIn("super-secret-value", checkin.describe_cookie(secret))

    def test_expiry_parses_milliseconds(self):
        expire_ms = int((NOW + timedelta(days=10)).timestamp() * 1000)

        expiry = checkin.parse_session_expiry(
            session_cookie({"expire": expire_ms}), now=NOW
        )

        self.assertIsNotNone(expiry)
        self.assertAlmostEqual(
            (expiry - NOW).total_seconds() / 86400.0, 10.0, delta=0.1
        )

    def test_expiry_parses_seconds(self):
        expire_s = int((NOW + timedelta(days=3)).timestamp())

        expiry = checkin.parse_session_expiry(
            session_cookie({"exp": expire_s}), now=NOW
        )

        self.assertAlmostEqual(
            (expiry - NOW).total_seconds() / 86400.0, 3.0, delta=0.1
        )

    def test_session_field_takes_priority_over_generic_expire(self):
        expire_ms = int((NOW + timedelta(days=2)).timestamp() * 1000)
        payload = {"_expire": expire_ms, "expire": int((NOW + timedelta(days=300)).timestamp() * 1000)}

        expiry, kind = checkin.session_expiry(session_cookie(payload), now=NOW)

        self.assertEqual(kind, "session")
        self.assertAlmostEqual((expiry - NOW).total_seconds() / 86400.0, 2.0, delta=0.1)

    def test_generic_expire_field_is_marked_unclear(self):
        expire_ms = int((NOW + timedelta(days=224)).timestamp() * 1000)

        expiry, kind = checkin.session_expiry(
            session_cookie({"expire": expire_ms}), now=NOW
        )

        self.assertEqual(kind, "unclear")
        self.assertIn("不代表会话有效期", checkin.expiry_summary(
            session_cookie({"expire": expire_ms}), now=NOW
        ))

    def test_expiry_returns_none_for_unreadable_cookie(self):
        self.assertIsNone(checkin.parse_session_expiry("koa:sess=not-base64!!"))
        self.assertIsNone(checkin.parse_session_expiry("nothing=here"))
        self.assertIsNone(checkin.parse_session_expiry(""))

    def test_summary_reports_remaining_days(self):
        expire_ms = int((NOW + timedelta(days=20)).timestamp() * 1000)

        summary = checkin.expiry_summary(
            session_cookie({"expire": expire_ms}), now=NOW
        )

        self.assertIn("剩余", summary)

    def test_summary_reports_expired_session(self):
        expire_ms = int((NOW - timedelta(days=2)).timestamp() * 1000)

        summary = checkin.expiry_summary(
            session_cookie({"expire": expire_ms}), now=NOW
        )

        self.assertIn("过期", summary)

    def test_alert_is_error_when_expired(self):
        expire_ms = int((NOW - timedelta(days=1)).timestamp() * 1000)

        alert = checkin.expiry_alert(
            session_cookie({"_expire": expire_ms}), now=NOW
        )

        self.assertTrue(alert.startswith("::error::"))

    def test_alert_is_warning_when_expiring_soon(self):
        expire_ms = int((NOW + timedelta(days=3)).timestamp() * 1000)

        alert = checkin.expiry_alert(
            session_cookie({"_expire": expire_ms}), now=NOW
        )

        self.assertTrue(alert.startswith("::warning::"))

    def test_no_alert_for_fresh_cookie(self):
        expire_ms = int((NOW + timedelta(days=25)).timestamp() * 1000)

        self.assertEqual(
            checkin.expiry_alert(session_cookie({"_expire": expire_ms}), now=NOW),
            "",
        )

    def test_no_alert_when_only_an_unclear_expire_field_exists(self):
        expire_ms = int((NOW + timedelta(days=1)).timestamp() * 1000)

        self.assertEqual(
            checkin.expiry_alert(session_cookie({"expire": expire_ms}), now=NOW),
            "",
        )


class PushTests(unittest.TestCase):
    def test_no_key_means_no_request(self):
        session = RecordingSession()

        self.assertFalse(checkin.send_push("", "title", "body", session=session))
        self.assertEqual(session.calls, [])

    def test_push_posts_to_pushdeer(self):
        session = RecordingSession()

        self.assertTrue(checkin.send_push("key", "title", "body", session=session))
        self.assertEqual(session.calls[0][0], checkin.PUSH_URL)
        self.assertEqual(session.calls[0][1]["data"]["pushkey"], "key")

    def test_push_failure_is_swallowed(self):
        class FailingSession:
            def post(self, url, **kwargs):
                raise requests.RequestException("boom")

        self.assertFalse(
            checkin.send_push("key", "t", "b", session=FailingSession())
        )


if __name__ == "__main__":
    unittest.main()
