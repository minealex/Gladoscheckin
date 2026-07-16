import unittest
from datetime import datetime, timezone

import backup_gate


NOW = datetime(2026, 7, 16, 10, 43, tzinfo=timezone.utc)
PRIMARY = "17 4 * * *"
BACKUP = "43 10 * * *"


def run(run_id, created_at, conclusion="success", event="schedule"):
    return {
        "id": run_id,
        "created_at": created_at,
        "conclusion": conclusion,
        "event": event,
    }


class BackupGateTests(unittest.TestCase):
    def test_push_never_runs_production(self):
        decision, _ = backup_gate.decide(
            "push", "", PRIMARY, [], NOW, current_run_id=10
        )
        self.assertFalse(decision)

    def test_manual_run_executes(self):
        decision, _ = backup_gate.decide(
            "workflow_dispatch", "", PRIMARY, [], NOW, current_run_id=10
        )
        self.assertTrue(decision)

    def test_primary_schedule_executes(self):
        decision, _ = backup_gate.decide(
            "schedule", PRIMARY, PRIMARY, [], NOW, current_run_id=10
        )
        self.assertTrue(decision)

    def test_backup_skips_after_successful_primary(self):
        runs = [run(9, "2026-07-16T04:20:00Z")]
        decision, _ = backup_gate.decide(
            "schedule", BACKUP, PRIMARY, runs, NOW, current_run_id=10
        )
        self.assertFalse(decision)

    def test_backup_runs_when_primary_failed(self):
        runs = [run(9, "2026-07-16T04:20:00Z", conclusion="failure")]
        decision, _ = backup_gate.decide(
            "schedule", BACKUP, PRIMARY, runs, NOW, current_run_id=10
        )
        self.assertTrue(decision)

    def test_backup_ignores_yesterdays_success(self):
        runs = [run(9, "2026-07-15T04:20:00Z")]
        decision, _ = backup_gate.decide(
            "schedule", BACKUP, PRIMARY, runs, NOW, current_run_id=10
        )
        self.assertTrue(decision)

    def test_current_run_is_not_counted(self):
        runs = [run(10, "2026-07-16T10:43:00Z")]
        decision, _ = backup_gate.decide(
            "schedule", BACKUP, PRIMARY, runs, NOW, current_run_id=10
        )
        self.assertTrue(decision)


if __name__ == "__main__":
    unittest.main()

