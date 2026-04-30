from __future__ import annotations

from collections import Counter
from pathlib import Path
import subprocess


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

LANGUAGE_BY_SUFFIX = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".c": "C",
    ".h": "C/C++",
    ".cc": "C++",
    ".cpp": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".sh": "Shell",
}

MARKERS = {
    "pyproject.toml": "Python package",
    "requirements.txt": "Python requirements",
    "package.json": "Node package",
    "Cargo.toml": "Rust package",
    "go.mod": "Go module",
    "pom.xml": "Maven project",
    "build.gradle": "Gradle project",
    "Makefile": "Makefile",
}


def build_project_context(workspace: Path) -> str:
    workspace = workspace.resolve()
    lines = [f"Workspace: {workspace}"]
    lines.append("")

    markers = [f"{name} ({label})" for name, label in MARKERS.items() if (workspace / name).exists()]
    lines.append("Detected project markers:")
    if markers:
        lines.extend(f"- {marker}" for marker in markers)
    else:
        lines.append("- none")
    lines.append("")

    languages = detect_languages(workspace)
    lines.append("Primary languages:")
    if languages:
        for language, count in languages.most_common(8):
            lines.append(f"- {language}: {count} file(s)")
    else:
        lines.append("- none detected")
    lines.append("")

    test_commands = detect_test_commands(workspace)
    lines.append("Suggested test commands:")
    if test_commands:
        lines.extend(f"- {command}" for command in test_commands)
    else:
        lines.append("- none detected")
    lines.append("")

    git_summary = get_git_summary(workspace)
    lines.append("Git:")
    lines.extend(f"- {line}" for line in git_summary)
    return "\n".join(lines)


def detect_languages(workspace: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in workspace.rglob("*"):
        if path.is_dir() or any(part in IGNORED_DIRS for part in path.parts):
            continue
        language = LANGUAGE_BY_SUFFIX.get(path.suffix.lower())
        if language:
            counts[language] += 1
    return counts


def detect_test_commands(workspace: Path) -> list[str]:
    commands: list[str] = []
    if (workspace / "pyproject.toml").exists() or (workspace / "tests").exists():
        if (workspace / "src").exists() and (workspace / "tests").exists():
            commands.append("PYTHONPATH=src python3 -m unittest discover -s tests")
        elif (workspace / "tests").exists():
            commands.append("python3 -m unittest discover -s tests")
    if any((workspace / name).exists() for name in ("pytest.ini", "tox.ini")):
        commands.append("python3 -m pytest")
    if (workspace / "package.json").exists():
        commands.append("npm test")
    if (workspace / "Cargo.toml").exists():
        commands.append("cargo test")
    if (workspace / "go.mod").exists():
        commands.append("go test ./...")
    if (workspace / "Makefile").exists():
        commands.append("make test")
    return commands


def get_git_summary(workspace: Path) -> list[str]:
    if not (workspace / ".git").exists():
        return ["not a git repository"]

    branch = _git(workspace, "branch", "--show-current") or "(detached)"
    status = _git(workspace, "status", "--short")
    lines = [f"branch: {branch}"]
    if status:
        changed = len(status.splitlines())
        lines.append(f"working tree: {changed} changed path(s)")
    else:
        lines.append("working tree: clean")
    return lines


def _git(workspace: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=workspace,
        text=True,
        capture_output=True,
        timeout=10,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()
