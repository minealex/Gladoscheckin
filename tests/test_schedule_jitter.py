import unittest
from datetime import datetime, timezone

import schedule_jitter


class ScheduleJitterTests(unittest.TestCase):
    def test_same_inputs_are_reproducible(self):
        args = ("minealex/repo", "2026-07-16", "17 4 * * *", 20)
        self.assertEqual(
            schedule_jitter.bounded_delay_seconds(*args),
            schedule_jitter.bounded_delay_seconds(*args),
        )

    def test_delay_stays_inside_window(self):
        delay = schedule_jitter.bounded_delay_seconds(
            "minealex/repo", "2026-07-16", "17 4 * * *", 20
        )
        self.assertGreaterEqual(delay, 0)
        self.assertLessEqual(delay, 20 * 60)

    def test_manual_and_push_events_have_no_delay(self):
        for event_name in ("workflow_dispatch", "push"):
            delay = schedule_jitter.delay_for_event(
                event_name,
                "minealex/repo",
                "2026-07-16",
                "17 4 * * *",
                20,
            )
            self.assertEqual(delay, 0)

    def test_zero_window_has_no_delay(self):
        delay = schedule_jitter.bounded_delay_seconds(
            "minealex/repo", "2026-07-16", "17 4 * * *", 0
        )
        self.assertEqual(delay, 0)

    def test_main_writes_numeric_output_without_sleeping(self):
        outputs = []

        class OutputCapture(dict):
            pass

        environ = OutputCapture(
            {
                "GITHUB_EVENT_NAME": "schedule",
                "GITHUB_REPOSITORY": "minealex/repo",
                "EVENT_SCHEDULE": "17 4 * * *",
                "MAX_JITTER_MINUTES": "20",
            }
        )
        original = schedule_jitter.write_output
        try:
            schedule_jitter.write_output = (
                lambda _environ, delay: outputs.append(delay)
            )
            schedule_jitter.main(
                environ,
                now=datetime(2026, 7, 16, tzinfo=timezone.utc),
            )
        finally:
            schedule_jitter.write_output = original

        self.assertEqual(len(outputs), 1)
        self.assertIsInstance(outputs[0], int)
        self.assertLessEqual(outputs[0], 20 * 60)


if __name__ == "__main__":
    unittest.main()

