from __future__ import annotations

from contextlib import contextmanager
import itertools
import sys
import threading
import time
from typing import Iterator


class Style:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled and sys.stdout.isatty()

    def apply(self, text: str, code: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    def dim(self, text: str) -> str:
        return self.apply(text, "2")

    def bold(self, text: str) -> str:
        return self.apply(text, "1")

    def cyan(self, text: str) -> str:
        return self.apply(text, "36")

    def green(self, text: str) -> str:
        return self.apply(text, "32")

    def yellow(self, text: str) -> str:
        return self.apply(text, "33")

    def red(self, text: str) -> str:
        return self.apply(text, "31")

    def blue(self, text: str) -> str:
        return self.apply(text, "34")


class Console:
    def __init__(self, *, color: bool = True) -> None:
        self.style = Style(color)

    def banner(self, provider: str, model: str, workspace: str) -> None:
        title = self.style.bold(self.style.cyan("CodeCraft Agent"))
        print(f"\n{title}  {self.style.dim('raw-API coding assistant')}")
        print(self.style.dim(f"provider: {provider}"))
        print(self.style.dim(f"model: {model}"))
        print(self.style.dim(f"workspace: {workspace}"))
        print(self.style.dim("type /help for commands, /exit to quit\n"))

    def prompt(self) -> str:
        return self.style.bold(self.style.green("you ")) + self.style.dim("> ")

    def assistant(self, text: str) -> None:
        if not text.strip():
            return
        print(f"\n{self.style.bold(self.style.blue('agent'))} {self.style.dim('>')}")
        print(text.strip())
        print()

    def stream_start(self) -> None:
        print(f"\n{self.style.bold(self.style.blue('agent'))} {self.style.dim('>')}")

    def stream_delta(self, text: str) -> None:
        print(text, end="", flush=True)

    def stream_end(self) -> None:
        print("\n")

    def system(self, text: str) -> None:
        print(self.style.dim(text))

    def error(self, text: str) -> None:
        print(self.style.red(f"error: {text}"))

    def warn(self, text: str) -> None:
        print(self.style.yellow(f"warning: {text}"))

    def tool_start(self, name: str, summary: str) -> None:
        print(f"{self.style.cyan('[tool]')} {self.style.bold(name)} {self.style.dim(summary)}")

    def tool_done(self, ok: bool, summary: str) -> None:
        marker = self.style.green("ok") if ok else self.style.red("failed")
        print(f"{self.style.dim('       ')}{marker} {self.style.dim(summary)}")

    def tool_preview(self, text: str) -> None:
        if text.strip():
            print(self.style.dim(text.rstrip()))

    def confirm(self, question: str) -> bool:
        while True:
            answer = input(f"{self.style.yellow('?')} {question} [y/N] ").strip().lower()
            if answer in {"y", "yes"}:
                return True
            if answer in {"", "n", "no"}:
                return False

    @contextmanager
    def spinner(self, label: str) -> Iterator[None]:
        if not sys.stdout.isatty():
            print(self.style.dim(label))
            yield
            return

        stop = threading.Event()
        frames = itertools.cycle(["-", "\\", "|", "/"])

        def run() -> None:
            while not stop.is_set():
                sys.stdout.write("\r" + self.style.dim(f"{next(frames)} {label}"))
                sys.stdout.flush()
                time.sleep(0.08)
            sys.stdout.write("\r" + " " * (len(label) + 4) + "\r")
            sys.stdout.flush()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=0.2)
