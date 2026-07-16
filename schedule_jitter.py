import hashlib
import os
from datetime import datetime, timezone


def bounded_delay_seconds(repository, day, schedule, max_minutes):
    """Return a deterministic daily delay within the configured window."""
    max_seconds = max(0, int(max_minutes)) * 60
    if max_seconds == 0:
        return 0
    material = f"{repository}|{day}|{schedule}".encode("utf-8")
    value = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    return value % (max_seconds + 1)


def delay_for_event(event_name, repository, day, schedule, max_minutes):
    if event_name != "schedule":
        return 0
    return bounded_delay_seconds(repository, day, schedule, max_minutes)


def write_output(environ, delay_seconds):
    output_path = environ.get("GITHUB_OUTPUT")
    line = f"delay_seconds={delay_seconds}\n"
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(line)
    else:
        print(line, end="")


def main(environ=None, now=None):
    environ = os.environ if environ is None else environ
    now = datetime.now(timezone.utc) if now is None else now
    delay_seconds = delay_for_event(
        environ.get("GITHUB_EVENT_NAME", ""),
        environ.get("GITHUB_REPOSITORY", ""),
        now.astimezone(timezone.utc).date().isoformat(),
        environ.get("EVENT_SCHEDULE", ""),
        environ.get("MAX_JITTER_MINUTES", "20"),
    )
    write_output(environ, delay_seconds)
    print(
        f"计划任务有界延迟：{delay_seconds // 60} 分 "
        f"{delay_seconds % 60} 秒"
    )


if __name__ == "__main__":
    main()

