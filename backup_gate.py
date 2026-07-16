import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def _parse_github_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def successful_schedule_today(runs, now, current_run_id):
    start_of_day = now.astimezone(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    for run in runs:
        if run.get("event") != "schedule":
            continue
        if run.get("conclusion") != "success":
            continue
        if int(run.get("id", 0)) == int(current_run_id):
            continue
        try:
            created_at = _parse_github_time(run["created_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if created_at >= start_of_day:
            return True
    return False


def decide(event_name, event_schedule, primary_cron, runs, now, current_run_id):
    if event_name == "workflow_dispatch":
        return True, "manual run"
    if event_name != "schedule":
        return False, "non-production event"
    if event_schedule == primary_cron:
        return True, "primary schedule"
    if successful_schedule_today(runs, now, current_run_id):
        return False, "primary schedule already succeeded today"
    return True, "backup schedule is needed"


def fetch_successful_runs(environ):
    repository = environ["GITHUB_REPOSITORY"]
    workflow_file = environ["WORKFLOW_FILE"]
    branch = environ.get("GITHUB_REF_NAME", "master")
    params = urllib.parse.urlencode(
        {
            "event": "schedule",
            "status": "success",
            "branch": branch,
            "per_page": 20,
        }
    )
    url = (
        f"https://api.github.com/repos/{repository}/actions/workflows/"
        f"{workflow_file}/runs?{params}"
    )
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {environ['GITHUB_TOKEN']}",
            "User-Agent": "checkin-backup-gate",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    runs = payload.get("workflow_runs", [])
    return runs if isinstance(runs, list) else []


def write_output(environ, should_run):
    output_path = environ.get("GITHUB_OUTPUT")
    line = f"run_checkin={'true' if should_run else 'false'}\n"
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(line)
    else:
        print(line, end="")


def main(environ=None):
    environ = os.environ if environ is None else environ
    event_name = environ.get("GITHUB_EVENT_NAME", "")
    event_schedule = environ.get("EVENT_SCHEDULE", "")
    primary_cron = environ["PRIMARY_CRON"]
    current_run_id = int(environ.get("GITHUB_RUN_ID", "0"))

    runs = []
    if event_name == "schedule" and event_schedule != primary_cron:
        try:
            runs = fetch_successful_runs(environ)
        except Exception as error:
            print(f"无法读取当天运行历史，将保守执行备用任务：{error}")

    should_run, reason = decide(
        event_name,
        event_schedule,
        primary_cron,
        runs,
        datetime.now(timezone.utc),
        current_run_id,
    )
    write_output(environ, should_run)
    print(f"签到决策：{'执行' if should_run else '跳过'}（{reason}）")


if __name__ == "__main__":
    main()

