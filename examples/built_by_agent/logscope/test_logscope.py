from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import logscope


class LogScopeTests(unittest.TestCase):
    def test_parse_json_line(self) -> None:
        event = logscope.parse_line(
            '{"timestamp":"2026-04-30T09:00:01Z","level":"warn","service":"api",'
            '"message":"slow request","status":504}'
        )
        self.assertEqual(event.level, "WARN")
        self.assertEqual(event.service, "api")
        self.assertEqual(event.status, 504)

    def test_parse_plain_text_line(self) -> None:
        event = logscope.parse_line("2026-04-30T09:01:04 ERROR api - failed status=500")
        self.assertEqual(event.level, "ERROR")
        self.assertEqual(event.service, "api")
        self.assertEqual(event.status, 500)

    def test_summary_detects_burst(self) -> None:
        lines = "\n".join(
            [
                "2026-04-30T09:00:01 INFO api - ok status=200",
                "2026-04-30T09:01:01 ERROR api - fail status=500",
                "2026-04-30T09:01:02 ERROR api - fail status=500",
                "2026-04-30T09:01:03 ERROR api - fail status=500",
                "2026-04-30T09:02:01 INFO api - ok status=200",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.log"
            path.write_text(lines, encoding="utf-8")
            events = logscope.load_events(path)

        report = logscope.summarize(events, bucket="minute", top=2)
        self.assertEqual(report["total_events"], 5)
        self.assertIn(("2026-04-30 09:01", 3), report["bursts"])


if __name__ == "__main__":
    unittest.main()

