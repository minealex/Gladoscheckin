import unittest

import checkin


class MultiAccountTests(unittest.TestCase):
    def test_single_cookie_backward_compatible(self):
        """单账号整段 Cookie 保持原有行为，域名用默认 SITE_DOMAIN。"""
        env = {"COOKIES": "koa:sess=aaa; koa:sess.sig=bbb"}
        accounts = checkin.parse_accounts(env)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0][0], checkin.SITE_DOMAIN)
        self.assertEqual(accounts[0][1], "koa:sess=aaa; koa:sess.sig=bbb")

    def test_multi_cookie_with_ampersand(self):
        """多账号用 & 分隔，默认域名统一。"""
        env = {"COOKIES": "cookie1&cookie2&cookie3"}
        accounts = checkin.parse_accounts(env)
        self.assertEqual(len(accounts), 3)
        self.assertTrue(all(d == checkin.SITE_DOMAIN for d, _ in accounts))
        self.assertEqual([c for _, c in accounts], ["cookie1", "cookie2", "cookie3"])

    def test_multi_cookie_with_per_account_domain(self):
        """每个账号可用 域名|Cookie 指定各自域名。"""
        env = {"COOKIES": "glados.cloud|ck1&glados.rocks|ck2"}
        accounts = checkin.parse_accounts(env)
        self.assertEqual(accounts, [("glados.cloud", "ck1"), ("glados.rocks", "ck2")])

    def test_mixed_domain_and_default(self):
        """可混合：有的带域名，有的不带。"""
        env = {"COOKIES": "glados.rocks|ckA&ckB"}
        accounts = checkin.parse_accounts(env)
        self.assertEqual(accounts[0], ("glados.rocks", "ckA"))
        self.assertEqual(accounts[1], (checkin.SITE_DOMAIN, "ckB"))

    def test_empty_and_blank_parts_ignored(self):
        """空段与纯空格段应被忽略。"""
        env = {"COOKIES": "ck1&  &ck2&"}
        accounts = checkin.parse_accounts(env)
        self.assertEqual([c for _, c in accounts], ["ck1", "ck2"])

    def test_no_cookie_returns_empty(self):
        self.assertEqual(checkin.parse_accounts({}), [])
        self.assertEqual(checkin.parse_accounts({"COOKIES": "   "}), [])

    def test_cookie_env_fallback(self):
        """COOKIE 与 COOKIES 都支持。"""
        self.assertEqual(
            checkin.parse_accounts({"COOKIE": "c1&c2"}),
            [(checkin.SITE_DOMAIN, "c1"), (checkin.SITE_DOMAIN, "c2")],
        )


if __name__ == "__main__":
    unittest.main()
