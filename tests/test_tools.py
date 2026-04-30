from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codecraft_agent.tools import ToolError, ToolRegistry


class ToolRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tempdir.name)
        self.tools = ToolRegistry(self.workspace, default_timeout=5)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_write_read_search_and_replace_file(self) -> None:
        result = self.tools.write_file("app/main.py", "def greet():\n    return 'hi'\n")
        self.assertIn("wrote app/main.py", result)

        read = self.tools.read_file("app/main.py")
        self.assertIn("1 | def greet():", read)

        search = self.tools.search_files("return", glob="*.py")
        self.assertIn("app/main.py:2:", search)

        replace = self.tools.replace_in_file(
            "app/main.py",
            "return 'hi'",
            "return 'hello'",
        )
        self.assertIn("updated app/main.py", replace)
        self.assertIn("hello", (self.workspace / "app/main.py").read_text())

    def test_resolve_blocks_paths_outside_workspace(self) -> None:
        with self.assertRaises(ToolError):
            self.tools.read_file("../outside.txt")

    def test_run_command_returns_exit_code_and_output(self) -> None:
        output = self.tools.run_command("python3 -c 'print(2 + 2)'")
        self.assertIn("exit_code: 0", output)
        self.assertIn("4", output)

    def test_write_preview_shows_unified_diff(self) -> None:
        self.tools.write_file("notes.txt", "old\n")
        preview = self.tools.preview("write_file", {"path": "notes.txt", "content": "new\n"})

        self.assertIn("--- a/notes.txt", preview)
        self.assertIn("+++ b/notes.txt", preview)
        self.assertIn("-old", preview)
        self.assertIn("+new", preview)

    def test_blocked_command_is_rejected(self) -> None:
        with self.assertRaises(ToolError):
            self.tools.run_command("rm -rf /")

    def test_project_context_mentions_python_tests(self) -> None:
        (self.workspace / "src").mkdir()
        (self.workspace / "tests").mkdir()
        (self.workspace / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")

        context = self.tools.project_context()

        self.assertIn("Python package", context)
        self.assertIn("PYTHONPATH=src python3 -m unittest discover -s tests", context)

    def test_invalid_regex_is_tool_error(self) -> None:
        self.tools.write_file("notes.txt", "alpha\n")
        with self.assertRaises(ToolError):
            self.tools.search_files("[", regex=True)


if __name__ == "__main__":
    unittest.main()
