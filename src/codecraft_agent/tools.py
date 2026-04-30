from __future__ import annotations

from dataclasses import dataclass
import difflib
import fnmatch
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
from typing import Any, Callable

from .context import build_project_context


IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
}
MAX_TOOL_OUTPUT = 24_000


class ToolError(RuntimeError):
    """Raised when a local tool cannot complete."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., str]
    requires_approval: bool = False
    preview: Callable[..., str] | None = None

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _truncate(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return text[:limit] + f"\n\n[output truncated: {omitted} characters omitted]"


def _line_range(text: str, start_line: int, max_lines: int) -> str:
    lines = text.splitlines()
    start = max(start_line, 1) - 1
    end = min(start + max_lines, len(lines))
    numbered = [f"{idx + 1:>5} | {lines[idx]}" for idx in range(start, end)]
    trailer = ""
    if end < len(lines):
        trailer = f"\n... {len(lines) - end} more lines"
    return "\n".join(numbered) + trailer


class ToolRegistry:
    def __init__(self, workspace: Path, *, default_timeout: int = 30) -> None:
        self.workspace = workspace.resolve()
        self.default_timeout = default_timeout
        self._tools = {
            tool.name: tool
            for tool in [
                Tool(
                    name="project_context",
                    description="Summarize the workspace: languages, project markers, test commands, and git state.",
                    parameters={"type": "object", "properties": {}, "required": []},
                    handler=self.project_context,
                ),
                Tool(
                    name="list_files",
                    description="List files under a workspace path, skipping common dependency/cache folders.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Directory to list, relative to workspace."},
                            "max_depth": {
                                "type": "integer",
                                "description": "Maximum directory depth to include.",
                                "minimum": 1,
                                "maximum": 8,
                            },
                        },
                        "required": [],
                    },
                    handler=self.list_files,
                ),
                Tool(
                    name="read_file",
                    description="Read a text file with line numbers.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path relative to workspace."},
                            "start_line": {"type": "integer", "minimum": 1},
                            "max_lines": {"type": "integer", "minimum": 1, "maximum": 1000},
                        },
                        "required": ["path"],
                    },
                    handler=self.read_file,
                ),
                Tool(
                    name="search_files",
                    description="Search text files for a literal or regex query.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search text or regex."},
                            "path": {"type": "string", "description": "Directory to search, relative to workspace."},
                            "glob": {"type": "string", "description": "File glob such as *.py or *."},
                            "regex": {"type": "boolean", "description": "Treat query as regular expression."},
                            "max_matches": {"type": "integer", "minimum": 1, "maximum": 200},
                        },
                        "required": ["query"],
                    },
                    handler=self.search_files,
                ),
                Tool(
                    name="write_file",
                    description="Create or overwrite a text file.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path relative to workspace."},
                            "content": {"type": "string", "description": "Complete file content."},
                        },
                        "required": ["path", "content"],
                    },
                    handler=self.write_file,
                    requires_approval=True,
                    preview=self.preview_write_file,
                ),
                Tool(
                    name="replace_in_file",
                    description="Replace exact text in a file. Use for targeted edits after reading the file.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path relative to workspace."},
                            "old": {"type": "string", "description": "Exact text to replace."},
                            "new": {"type": "string", "description": "Replacement text."},
                            "expected_replacements": {
                                "type": "integer",
                                "description": "Expected number of replacements.",
                                "minimum": 1,
                            },
                        },
                        "required": ["path", "old", "new"],
                    },
                    handler=self.replace_in_file,
                    requires_approval=True,
                    preview=self.preview_replace_in_file,
                ),
                Tool(
                    name="make_directory",
                    description="Create a directory under the workspace.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Directory path relative to workspace."}
                        },
                        "required": ["path"],
                    },
                    handler=self.make_directory,
                    requires_approval=True,
                ),
                Tool(
                    name="git_status",
                    description="Show concise git status for the workspace.",
                    parameters={"type": "object", "properties": {}, "required": []},
                    handler=self.git_status,
                ),
                Tool(
                    name="git_diff",
                    description="Show the current git diff for the workspace or a single path.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Optional path relative to workspace."},
                            "staged": {"type": "boolean", "description": "Show staged diff instead of working diff."},
                        },
                        "required": [],
                    },
                    handler=self.git_diff,
                ),
                Tool(
                    name="run_tests",
                    description="Run a test command. If no command is provided, use the best detected test command.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "Optional test command."},
                            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
                        },
                        "required": [],
                    },
                    handler=self.run_tests,
                    requires_approval=True,
                    preview=self.preview_run_tests,
                ),
                Tool(
                    name="run_command",
                    description="Run a shell command in the workspace and return stdout, stderr, and exit code.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "Shell command to execute."},
                            "timeout_seconds": {
                                "type": "integer",
                                "description": "Timeout in seconds.",
                                "minimum": 1,
                                "maximum": 300,
                            },
                        },
                        "required": ["command"],
                    },
                    handler=self.run_command,
                    requires_approval=True,
                    preview=self.preview_run_command,
                ),
            ]
        }

    @property
    def tools(self) -> list[Tool]:
        return list(self._tools.values())

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self.tools]

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolError(f"unknown tool: {name}") from exc

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self.get(name)
        try:
            output = tool.handler(**arguments)
            return _truncate(output)
        except ToolError:
            raise
        except TypeError as exc:
            raise ToolError(f"invalid arguments for {name}: {exc}") from exc
        except OSError as exc:
            raise ToolError(str(exc)) from exc

    def preview(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self.get(name)
        if not tool.preview:
            return ""
        try:
            return _truncate(tool.preview(**arguments), 12_000)
        except TypeError as exc:
            raise ToolError(f"invalid arguments for {name}: {exc}") from exc

    def summarize_args(self, name: str, arguments: dict[str, Any]) -> str:
        if name in {"read_file", "write_file", "replace_in_file", "make_directory", "git_diff"}:
            return str(arguments.get("path", ""))
        if name == "run_tests":
            return str(arguments.get("command", "auto-detect"))
        if name == "search_files":
            return json.dumps(
                {
                    "query": arguments.get("query", ""),
                    "path": arguments.get("path", "."),
                    "glob": arguments.get("glob", "*"),
                },
                ensure_ascii=True,
            )
        if name == "run_command":
            return str(arguments.get("command", ""))
        return json.dumps(arguments, ensure_ascii=True)[:120]

    def resolve(self, path: str | None) -> Path:
        raw = Path(path or ".").expanduser()
        resolved = raw if raw.is_absolute() else self.workspace / raw
        resolved = resolved.resolve()
        if resolved != self.workspace and self.workspace not in resolved.parents:
            raise ToolError(f"path escapes workspace: {path}")
        return resolved

    def project_context(self) -> str:
        return build_project_context(self.workspace)

    def list_files(self, path: str = ".", max_depth: int = 3) -> str:
        root = self.resolve(path)
        if not root.exists():
            raise ToolError(f"path does not exist: {path}")
        if not root.is_dir():
            raise ToolError(f"path is not a directory: {path}")

        max_depth = max(1, min(int(max_depth), 8))
        entries: list[str] = []
        for current, dirs, files in os.walk(root):
            current_path = Path(current)
            rel_depth = len(current_path.relative_to(root).parts)
            dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".git"))
            files = sorted(files)

            if rel_depth >= max_depth:
                dirs[:] = []
            prefix = current_path.relative_to(self.workspace)
            display_prefix = "." if str(prefix) == "." else str(prefix)
            for dirname in dirs:
                entries.append(f"{display_prefix}/{dirname}/")
            for filename in files:
                file_path = current_path / filename
                try:
                    size = file_path.stat().st_size
                except OSError:
                    size = 0
                entries.append(f"{display_prefix}/{filename} ({size} bytes)")
            if len(entries) >= 500:
                entries.append("... result limit reached")
                break

        return "\n".join(entries) if entries else "(empty)"

    def read_file(self, path: str, start_line: int = 1, max_lines: int = 240) -> str:
        file_path = self.resolve(path)
        if not file_path.exists():
            raise ToolError(f"file does not exist: {path}")
        if not file_path.is_file():
            raise ToolError(f"path is not a file: {path}")
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ToolError(f"file is not valid UTF-8 text: {path}") from exc
        return _line_range(text, int(start_line), int(max_lines))

    def search_files(
        self,
        query: str,
        path: str = ".",
        glob: str = "*",
        regex: bool = False,
        max_matches: int = 80,
    ) -> str:
        root = self.resolve(path)
        if not root.exists():
            raise ToolError(f"path does not exist: {path}")
        try:
            pattern = re.compile(query) if regex else None
        except re.error as exc:
            raise ToolError(f"invalid regex: {exc}") from exc
        matches: list[str] = []
        max_matches = max(1, min(int(max_matches), 200))

        paths = [root] if root.is_file() else root.rglob("*")
        for file_path in paths:
            if file_path.is_dir():
                continue
            if any(part in IGNORED_DIRS for part in file_path.parts):
                continue
            if not fnmatch.fnmatch(file_path.name, glob):
                continue
            try:
                text = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                hit = bool(pattern.search(line)) if pattern else query in line
                if hit:
                    rel = file_path.relative_to(self.workspace)
                    matches.append(f"{rel}:{line_number}: {line}")
                    if len(matches) >= max_matches:
                        return "\n".join(matches) + "\n... match limit reached"
        return "\n".join(matches) if matches else "(no matches)"

    def write_file(self, path: str, content: str) -> str:
        file_path = self.resolve(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        rel = file_path.relative_to(self.workspace)
        line_count = len(content.splitlines())
        return f"wrote {rel} ({line_count} lines, {len(content)} bytes)"

    def preview_write_file(self, path: str, content: str) -> str:
        file_path = self.resolve(path)
        old = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
        return self._diff_for_path(file_path, old, content)

    def replace_in_file(
        self,
        path: str,
        old: str,
        new: str,
        expected_replacements: int = 1,
    ) -> str:
        file_path = self.resolve(path)
        if not file_path.exists():
            raise ToolError(f"file does not exist: {path}")
        text = file_path.read_text(encoding="utf-8")
        actual = text.count(old)
        if actual == 0:
            raise ToolError("old text was not found")
        if int(expected_replacements) != actual:
            raise ToolError(
                f"expected {expected_replacements} replacement(s), found {actual}. "
                "Refine the old text or update expected_replacements."
            )
        file_path.write_text(text.replace(old, new), encoding="utf-8")
        rel = file_path.relative_to(self.workspace)
        return f"updated {rel} ({actual} replacement(s))"

    def preview_replace_in_file(
        self,
        path: str,
        old: str,
        new: str,
        expected_replacements: int = 1,
    ) -> str:
        file_path = self.resolve(path)
        if not file_path.exists():
            raise ToolError(f"file does not exist: {path}")
        text = file_path.read_text(encoding="utf-8")
        actual = text.count(old)
        if actual == 0:
            raise ToolError("old text was not found")
        if int(expected_replacements) != actual:
            raise ToolError(
                f"expected {expected_replacements} replacement(s), found {actual}. "
                "Refine the old text or update expected_replacements."
            )
        return self._diff_for_path(file_path, text, text.replace(old, new))

    def make_directory(self, path: str) -> str:
        directory = self.resolve(path)
        directory.mkdir(parents=True, exist_ok=True)
        rel = directory.relative_to(self.workspace)
        return f"created {rel}/"

    def git_status(self) -> str:
        return self._run_git(["status", "--short", "--branch"])

    def git_diff(self, path: str | None = None, staged: bool = False) -> str:
        args = ["diff"]
        if staged:
            args.append("--staged")
        if path:
            resolved = self.resolve(path)
            args.extend(["--", str(resolved.relative_to(self.workspace))])
        return self._run_git(args)

    def run_tests(self, command: str | None = None, timeout_seconds: int | None = None) -> str:
        test_command = command or self._detect_test_command()
        if not test_command:
            raise ToolError("no test command detected; provide a command explicitly")
        return self.run_command(test_command, timeout_seconds=timeout_seconds)

    def preview_run_tests(self, command: str | None = None, timeout_seconds: int | None = None) -> str:
        test_command = command or self._detect_test_command() or "(none detected)"
        return self.preview_run_command(test_command, timeout_seconds=timeout_seconds)

    def run_command(self, command: str, timeout_seconds: int | None = None) -> str:
        risk, reason = self.assess_command(command)
        if risk == "blocked":
            raise ToolError(f"blocked command: {reason}")
        timeout = int(timeout_seconds or self.default_timeout)
        timeout = max(1, min(timeout, 300))
        rendered_command = shlex.join(["/bin/sh", "-lc", command])
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            parts = [
                f"$ {rendered_command}",
                f"timed out after {timeout} second(s)",
            ]
            if stdout:
                parts.append("stdout:\n" + str(stdout).rstrip())
            if stderr:
                parts.append("stderr:\n" + str(stderr).rstrip())
            raise ToolError("\n".join(parts)) from exc
        parts = [
            f"$ {rendered_command}",
            f"exit_code: {completed.returncode}",
        ]
        if completed.stdout:
            parts.append("stdout:\n" + completed.stdout.rstrip())
        if completed.stderr:
            parts.append("stderr:\n" + completed.stderr.rstrip())
        if not completed.stdout and not completed.stderr:
            parts.append("(no output)")
        return "\n".join(parts)

    def preview_run_command(self, command: str, timeout_seconds: int | None = None) -> str:
        risk, reason = self.assess_command(command)
        timeout = int(timeout_seconds or self.default_timeout)
        return "\n".join(
            [
                f"command risk: {risk}",
                f"reason: {reason}",
                f"timeout: {max(1, min(timeout, 300))} second(s)",
            ]
        )

    def assess_command(self, command: str) -> tuple[str, str]:
        blocked_patterns = [
            (r"\brm\s+-[^\n]*[rf][^\n]*\s+/(?:\s|$)", "recursive removal of filesystem root"),
            (r"\bsudo\b", "sudo is not allowed inside agent shell tools"),
            (r"\bmkfs(?:\.\w+)?\b", "filesystem formatting command"),
            (r"\bdiskutil\s+erase", "disk erase command"),
            (r":\s*\(\s*\)\s*\{", "shell fork bomb pattern"),
        ]
        for pattern, reason in blocked_patterns:
            if re.search(pattern, command):
                return "blocked", reason

        high_patterns = [
            (r"\brm\s+-[^\n]*r", "recursive removal"),
            (r"\bcurl\b.+\|\s*(?:sh|bash)\b", "downloaded script piped to shell"),
            (r"\bchmod\s+-R\b", "recursive permission change"),
            (r"\bkillall\b", "kills processes by name"),
        ]
        for pattern, reason in high_patterns:
            if re.search(pattern, command):
                return "high", reason
        return "low", "read-only or ordinary local command"

    def _diff_for_path(self, file_path: Path, old: str, new: str) -> str:
        rel = file_path.relative_to(self.workspace)
        fromfile = f"a/{rel}" if file_path.exists() else "/dev/null"
        tofile = f"b/{rel}"
        diff = "".join(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=fromfile,
                tofile=tofile,
            )
        )
        return diff or "(no textual changes)"

    def _run_git(self, args: list[str]) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.workspace,
            text=True,
            capture_output=True,
            timeout=30,
        )
        parts = [f"exit_code: {completed.returncode}"]
        if completed.stdout:
            parts.append(completed.stdout.rstrip())
        if completed.stderr:
            parts.append("stderr:\n" + completed.stderr.rstrip())
        if not completed.stdout and not completed.stderr:
            parts.append("(no output)")
        return "\n".join(parts)

    def _detect_test_command(self) -> str:
        if (self.workspace / "src").exists() and (self.workspace / "tests").exists():
            return "PYTHONPATH=src python3 -m unittest discover -s tests"
        if (self.workspace / "tests").exists():
            return "python3 -m unittest discover -s tests"
        if (self.workspace / "package.json").exists():
            return "npm test"
        if (self.workspace / "Cargo.toml").exists():
            return "cargo test"
        if (self.workspace / "go.mod").exists():
            return "go test ./..."
        if (self.workspace / "Makefile").exists():
            return "make test"
        return ""
