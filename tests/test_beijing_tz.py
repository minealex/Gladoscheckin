from datetime import datetime, timezone
import unittest

import backup_gate


class BeijingTimezoneTests(unittest.TestCase):
    """GLaDOS/Railgun 按北京时间签到，backup_gate 的'当天'必须用北京时间判断。

    回归测试：防止改回 UTC 天判断，导致北京时间跨天时漏签。
    """

    def test_beijing_crosses_utc_day_still_checks_in(self):
        """北京时间已跨天但 UTC 仍同一天时，新一天的签到必须执行。

        场景（真实故障）：#825 10-20 17:28 BJ 成功，#827 10-21 02:02 BJ 触发。
        两者都在 UTC 10-20，若按 UTC 天判断会误跳过 #827，导致 10-21 漏签。
        """
        runs = [{
            "event": "schedule", "conclusion": "success", "id": 100,
            "created_at": "2026-10-20T09:28:00Z",  # 10-20 17:28 BJ
        }]
        now = datetime(2026, 10, 20, 18, 2, tzinfo=timezone.utc)  # 10-21 02:02 BJ
        ok, reason = backup_gate.decide(
            "schedule", "51 18 * * *", "17 12 * * *", runs, now, 200
        )
        self.assertTrue(ok, f"10-21 BJ 当天未签应执行，却得到 {reason}")

    def test_same_beijing_day_still_skips_backup(self):
        """同一北京时间当天已有成功，备用窗口应跳过（去重仍有效）。"""
        runs = [{
            "event": "schedule", "conclusion": "success", "id": 100,
            "created_at": "2026-10-20T09:28:00Z",  # 10-20 17:28 BJ
        }]
        now = datetime(2026, 10, 20, 15, 21, tzinfo=timezone.utc)  # 10-20 23:21 BJ
        ok, reason = backup_gate.decide(
            "schedule", "33 21 * * *", "17 12 * * *", runs, now, 300
        )
        self.assertFalse(ok, f"10-20 BJ 已签应跳过，却得到 {reason}")


if __name__ == "__main__":
    unittest.main()
