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

    def test_invalid_regex_is_tool_error(self) -> None:
        self.tools.write_file("notes.txt", "alpha\n")
        with self.assertRaises(ToolError):
            self.tools.search_files("[", regex=True)


if __name__ == "__main__":
    unittest.main()

