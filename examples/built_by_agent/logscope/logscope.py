#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import re
from typing import Iterable


TEXT_LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\S+)\s+(?P<level>[A-Z]+)\s+(?P<service>[\w.-]+)\s+-\s+(?P<message>.*)$"
)
KEY_VALUE_PATTERN = re.compile(r"\b(?P<key>[A-Za-z_][\w.-]*)=(?P<value>\"[^\"]*\"|\S+)")


@dataclass(frozen=True)
class Event:
    timestamp: datetime | None
    level: str
    service: str
    message: str
    status: int | None
    raw: str


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def parse_status(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_key_values(message: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for match in KEY_VALUE_PATTERN.finditer(message):
        value = match.group("value").strip('"')
        pairs[match.group("key")] = value
    return pairs


def parse_json_line(line: str) -> Event | None:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    message = str(data.get("message") or data.get("msg") or "")
    return Event(
        timestamp=parse_timestamp(data.get("timestamp") or data.get("time") or data.get("ts")),
        level=str(data.get("level") or data.get("severity") or "INFO").upper(),
        service=str(data.get("service") or data.get("app") or "unknown"),
        message=message,
        status=parse_status(data.get("status") or data.get("status_code")),
        raw=line,
    )


def parse_text_line(line: str) -> Event:
    match = TEXT_LOG_PATTERN.match(line)
    if not match:
        return Event(None, "INFO", "unknown", line, None, line)

    message = match.group("message")
    fields = parse_key_values(message)
    return Event(
        timestamp=parse_timestamp(match.group("timestamp")),
        level=match.group("level").upper(),
        service=match.group("service"),
        message=message,
        status=parse_status(fields.get("status") or fields.get("status_code")),
        raw=line,
    )


def parse_line(line: str) -> Event:
    stripped = line.strip()
    return parse_json_line(stripped) or parse_text_line(stripped)


def load_events(path: Path) -> list[Event]:
    events: list[Event] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                events.append(parse_line(line))
    return events


def filter_events(events: Iterable[Event], *, level: str | None, service: str | None) -> list[Event]:
    selected = list(events)
    if level:
        selected = [event for event in selected if event.level == level.upper()]
    if service:
        selected = [event for event in selected if event.service == service]
    return selected


def bucket_key(timestamp: datetime | None, size: str) -> str:
    if timestamp is None:
        return "unknown"
    if size == "hour":
        return timestamp.strftime("%Y-%m-%d %H:00")
    return timestamp.strftime("%Y-%m-%d %H:%M")


def timeline(events: Iterable[Event], bucket: str) -> Counter[str]:
    return Counter(bucket_key(event.timestamp, bucket) for event in events)


def detect_bursts(counts: Counter[str], *, min_count: int = 3) -> list[tuple[str, int]]:
    if not counts:
        return []
    values = list(counts.values())
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    threshold = max(min_count, math.ceil(mean + math.sqrt(variance)))
    return sorted(
        [(bucket, count) for bucket, count in counts.items() if count >= threshold],
        key=lambda item: (-item[1], item[0]),
    )


def top_messages(events: Iterable[Event], limit: int) -> list[tuple[str, int]]:
    counter = Counter(event.message for event in events)
    return counter.most_common(limit)


def summarize(events: list[Event], *, bucket: str, top: int) -> dict[str, object]:
    timeline_counts = timeline(events, bucket)
    return {
        "total_events": len(events),
        "levels": dict(Counter(event.level for event in events).most_common()),
        "services": dict(Counter(event.service for event in events).most_common()),
        "statuses": dict(Counter(str(event.status) for event in events if event.status is not None).most_common()),
        "timeline": dict(sorted(timeline_counts.items())),
        "bursts": detect_bursts(timeline_counts),
        "top_messages": top_messages(events, top),
    }


def bar(count: int, maximum: int, width: int = 32) -> str:
    if maximum <= 0:
        return ""
    filled = max(1, round((count / maximum) * width))
    return "#" * filled


def render_counter(title: str, counts: dict[str, int]) -> str:
    lines = [title]
    if not counts:
        return title + "\n  (none)"
    maximum = max(counts.values())
    for name, count in counts.items():
        lines.append(f"  {name:14} {count:5}  {bar(count, maximum)}")
    return "\n".join(lines)


def render_report(summary: dict[str, object]) -> str:
    lines = [f"LogScope report: {summary['total_events']} event(s)", ""]
    lines.append(render_counter("Levels", summary["levels"]))  # type: ignore[arg-type]
    lines.append("")
    lines.append(render_counter("Services", summary["services"]))  # type: ignore[arg-type]
    lines.append("")
    lines.append(render_counter("Statuses", summary["statuses"]))  # type: ignore[arg-type]
    lines.append("")
    lines.append(render_counter("Timeline", summary["timeline"]))  # type: ignore[arg-type]
    lines.append("")
    lines.append("Bursts")
    bursts = summary["bursts"]
    if bursts:
        for bucket, count in bursts:  # type: ignore[assignment]
            lines.append(f"  {bucket:16} {count}")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append("Top messages")
    for message, count in summary["top_messages"]:  # type: ignore[assignment]
        lines.append(f"  {count:5}  {message[:90]}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze JSONL and plain-text application logs.")
    parser.add_argument("logfile", type=Path)
    parser.add_argument("--level", help="Only include one level, for example ERROR.")
    parser.add_argument("--service", help="Only include one service.")
    parser.add_argument("--bucket", choices=["minute", "hour"], default="minute")
    parser.add_argument("--top", type=int, default=5, help="Number of top messages to show.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    events = filter_events(load_events(args.logfile), level=args.level, service=args.service)
    report = summarize(events, bucket=args.bucket, top=args.top)
    if args.json:
        print(json.dumps(report, indent=2, default=list))
    else:
        print(render_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
