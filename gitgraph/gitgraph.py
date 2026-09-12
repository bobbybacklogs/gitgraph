#!/usr/bin/env python3
"""Browse git log --graph --all for repos under a folder. Stdlib only. Windows terminal OK."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

COMMIT_LIMIT = 400
SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "release",
    "build",
    ".next",
    "target",
    ".idea",
    ".vs",
}
MAX_WALK_DEPTH = 6
MARKER = "\t@@\t"

ANSI_RESET = "\x1b[0m"
ANSI_DIM = "\x1b[2m"
ANSI_BOLD = "\x1b[1m"
ANSI_REVERSE = "\x1b[7m"
ANSI_CYAN = "\x1b[36m"
ANSI_YELLOW = "\x1b[33m"
ANSI_MAGENTA = "\x1b[35m"
ANSI_GREEN = "\x1b[32m"
ANSI_BLUE = "\x1b[34m"
ANSI_WHITE = "\x1b[37m"
ANSI_HIDE = "\x1b[?25l"
ANSI_SHOW = "\x1b[?25h"
ALT_ON = "\x1b[?1049h"
ALT_OFF = "\x1b[?1049l"
CLEAR = "\x1b[2J\x1b[H"
GRAPH_COLORS = (ANSI_CYAN, ANSI_YELLOW, ANSI_MAGENTA, ANSI_GREEN, ANSI_BLUE)


@dataclass(frozen=True)
class Repo:
    path: Path
    name: str


@dataclass
class GraphLine:
    raw_prefix: str
    full_hash: str | None
    short_hash: str | None
    date: str | None
    subject: str | None
    refs: str | None
    display: str


def enable_windows_vt() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def term_size() -> tuple[int, int]:
    try:
        size = shutil.get_terminal_size()
        return max(24, size.columns), max(12, size.lines)
    except OSError:
        return 80, 24


def is_git_root(path: Path) -> bool:
    git = path / ".git"
    return git.is_dir() or git.is_file()


def discover_repos(root: Path, max_depth: int = MAX_WALK_DEPTH) -> list[Repo]:
    root = root.resolve()
    found: list[Repo] = []
    if is_git_root(root):
        found.append(Repo(root, root.name or str(root)))

    root_depth = len(root.parts)
    for dirpath, dirnames, _files in os.walk(root, followlinks=False):
        current = Path(dirpath)
        depth = len(current.parts) - root_depth
        dirnames[:] = [
            name
            for name in dirnames
            if name not in SKIP_DIRS and not name.startswith(".git")
        ]
        if depth >= max_depth:
            dirnames[:] = []
            continue
        if current == root:
            continue
        if is_git_root(current):
            found.append(Repo(current, current.name))
            dirnames[:] = []
    found.sort(key=lambda repo: str(repo.path).lower())
    return found


def run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def load_graph(repo: Path, limit: int = COMMIT_LIMIT) -> list[GraphLine]:
    pretty = f"{MARKER}%H{MARKER}%h{MARKER}%ad{MARKER}%s{MARKER}%D"
    result = run_git(
        repo,
        [
            "log",
            "--graph",
            "--all",
            "--date=short",
            f"--pretty=format:{pretty}",
            f"-n{limit}",
        ],
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git log failed")
    return parse_graph(result.stdout)


def parse_graph(text: str) -> list[GraphLine]:
    lines: list[GraphLine] = []
    for raw in text.splitlines():
        if MARKER in raw:
            prefix, payload = raw.split(MARKER, 1)
            parts = payload.split(MARKER)
            while len(parts) < 5:
                parts.append("")
            full, short, date, subject, refs = parts[:5]
            display = f"{prefix}{short}  {date}  {subject}"
            if refs:
                display = f"{display}  ({refs})"
            lines.append(
                GraphLine(
                    raw_prefix=prefix,
                    full_hash=full or None,
                    short_hash=short or None,
                    date=date or None,
                    subject=subject or None,
                    refs=refs or None,
                    display=display.rstrip(),
                )
            )
        else:
            lines.append(
                GraphLine(
                    raw_prefix=raw,
                    full_hash=None,
                    short_hash=None,
                    date=None,
                    subject=None,
                    refs=None,
                    display=raw,
                )
            )
    return lines


def load_commit_detail(repo: Path, full_hash: str) -> str:
    result = run_git(
        repo,
        ["show", "-s", "--format=%an <%ae>%n%n%B", full_hash],
    )
    if result.returncode != 0:
        return result.stderr.strip() or "Could not load commit."
    return result.stdout.strip()


def color_graph_prefix(prefix: str) -> str:
    out: list[str] = []
    color_i = 0
    for ch in prefix:
        if ch in "*|\\/":
            out.append(f"{GRAPH_COLORS[color_i % len(GRAPH_COLORS)]}{ch}{ANSI_RESET}")
            if ch == "*":
                color_i += 1
        else:
            out.append(ch)
    return "".join(out)


def paint_graph_line(line: GraphLine, width: int, selected: bool) -> str:
    prefix = color_graph_prefix(line.raw_prefix)
    if line.short_hash:
        rest = f"{ANSI_YELLOW}{line.short_hash}{ANSI_RESET}  {ANSI_DIM}{line.date}{ANSI_RESET}  {line.subject or ''}"
        if line.refs:
            rest += f"  {ANSI_MAGENTA}({line.refs}){ANSI_RESET}"
        painted = prefix + rest
    else:
        painted = prefix if prefix.strip() else line.display
    visible = strip_ansi(painted)
    if len(visible) > width:
        painted = clip_ansi(painted, width)
    if selected:
        return f"{ANSI_REVERSE}{strip_ansi(painted)[:width].ljust(width)}{ANSI_RESET}"
    return painted + " " * max(0, width - len(strip_ansi(painted)))


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def clip_ansi(text: str, width: int) -> str:
    out: list[str] = []
    visible = 0
    i = 0
    while i < len(text) and visible < width:
        if text[i] == "\x1b":
            match = ANSI_RE.match(text, i)
            if match:
                out.append(match.group(0))
                i = match.end()
                continue
        out.append(text[i])
        visible += 1
        i += 1
    out.append(ANSI_RESET)
    return "".join(out)


def first_commit_index(lines: list[GraphLine]) -> int:
    for index, line in enumerate(lines):
        if line.full_hash:
            return index
    return 0


class KeyReader:
    def __init__(self) -> None:
        self._fd = sys.stdin.fileno()
        self._old = None
        if os.name != "nt" and sys.stdin.isatty():
            import termios
            import tty

            self._old = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)

    def close(self) -> None:
        if self._old is not None:
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)

    def read(self) -> str:
        if os.name == "nt":
            import msvcrt

            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):
                extra = msvcrt.getwch()
                return {"H": "up", "P": "down", "I": "pageup", "Q": "pagedown"}.get(
                    extra, ""
                )
            if ch in ("\r", "\n"):
                return "enter"
            if ch == "\x1b":
                return "q"
            if ch.lower() == "q":
                return "q"
            if ch.lower() == "j":
                return "down"
            if ch.lower() == "k":
                return "up"
            return ch
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            rest = sys.stdin.read(1)
            if rest != "[":
                return "q"
            arrow = sys.stdin.read(1)
            mapping = {"A": "up", "B": "down", "5": "pageup", "6": "pagedown"}
            if arrow in {"5", "6"}:
                extra = sys.stdin.read(1)
                if extra != "~":
                    pass
            return mapping.get(arrow, "")
        if ch in ("\r", "\n"):
            return "enter"
        if ch.lower() == "q":
            return "q"
        if ch.lower() == "j":
            return "down"
        if ch.lower() == "k":
            return "up"
        return ch


def write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def draw_bar(width: int, left: str, right: str = "") -> str:
    space = max(0, width - len(left) - len(right))
    return f"{ANSI_BOLD}{left}{' ' * space}{right}{ANSI_RESET}"


def run_picker(repos: list[Repo]) -> Repo | None:
    index = 0
    scroll = 0
    keys = KeyReader()
    try:
        write(ALT_ON + ANSI_HIDE)
        while True:
            cols, rows = term_size()
            header = 2
            footer = 2
            body = max(1, rows - header - footer)
            if index < scroll:
                scroll = index
            if index >= scroll + body:
                scroll = index - body + 1
            chunks = [CLEAR, draw_bar(cols, " git graph ", "pick a repo") + "\n"]
            chunks.append(
                f"{ANSI_DIM}  {len(repos)} git roots  ·  Enter open  ·  q quit{ANSI_RESET}\n"
            )
            view = repos[scroll : scroll + body]
            for offset, repo in enumerate(view):
                i = scroll + offset
                mark = ">" if i == index else " "
                line = f" {mark} {repo.name}  {ANSI_DIM}{repo.path}{ANSI_RESET}"
                if i == index:
                    line = f"{ANSI_REVERSE} {mark} {repo.name}  {repo.path}{ANSI_RESET}"
                chunks.append(clip_ansi(line, cols).ljust(cols)[: cols + 32] + "\n")
            chunks.append(
                f"{ANSI_DIM}↑↓ j/k  ·  Enter  ·  q{ANSI_RESET}".ljust(cols)
            )
            write("".join(chunks))
            key = keys.read()
            if key == "q":
                return None
            if key == "up":
                index = max(0, index - 1)
            elif key == "down":
                index = min(len(repos) - 1, index + 1)
            elif key == "pageup":
                index = max(0, index - body)
            elif key == "pagedown":
                index = min(len(repos) - 1, index + body)
            elif key == "enter":
                return repos[index]
    finally:
        keys.close()
        write(ANSI_SHOW + ALT_OFF)


def run_graph(repo: Repo, limit: int) -> None:
    try:
        lines = load_graph(repo.path, limit)
    except RuntimeError as error:
        sys.stderr.write(f"git log failed: {error}\n")
        return
    if not lines:
        sys.stderr.write(f"No commits in {repo.path}\n")
        return

    cursor = first_commit_index(lines)
    scroll = 0
    detail_cache: dict[str, str] = {}
    keys = KeyReader()
    try:
        write(ALT_ON + ANSI_HIDE)
        while True:
            cols, rows = term_size()
            detail_h = min(8, max(5, rows // 4))
            header = 2
            body = max(3, rows - header - 1 - detail_h)
            if cursor < scroll:
                scroll = cursor
            if cursor >= scroll + body:
                scroll = cursor - body + 1

            selected = lines[cursor]
            if selected.full_hash and selected.full_hash not in detail_cache:
                detail_cache[selected.full_hash] = load_commit_detail(
                    repo.path, selected.full_hash
                )

            chunks = [
                CLEAR,
                draw_bar(cols, f" {repo.name} ", "git log --graph --all") + "\n",
                f"{ANSI_DIM}  {repo.path}  ·  {len(lines)} lines (cap {limit})  ·  q quit{ANSI_RESET}\n",
            ]
            window = lines[scroll : scroll + body]
            for offset, line in enumerate(window):
                chunks.append(
                    paint_graph_line(line, cols, scroll + offset == cursor) + "\n"
                )
            chunks.append(f"{ANSI_DIM}{'\u2500' * cols}{ANSI_RESET}\n")
            if selected.full_hash:
                title = f"{selected.short_hash}  {selected.date}  {selected.subject or ''}"
                chunks.append(f"{ANSI_BOLD}{title[:cols]}{ANSI_RESET}\n")
                if selected.refs:
                    chunks.append(f"{ANSI_MAGENTA}{selected.refs[:cols]}{ANSI_RESET}\n")
                remain = detail_h - 3
                for detail_line in detail_cache.get(selected.full_hash, "").splitlines()[
                    : max(1, remain)
                ]:
                    chunks.append(detail_line[:cols] + "\n")
            else:
                chunks.append(
                    f"{ANSI_DIM}Graph connector — move to a * commit.{ANSI_RESET}\n"
                )
            write("".join(chunks))
            key = keys.read()
            if key == "q":
                return
            if key == "up":
                cursor = max(0, cursor - 1)
            elif key == "down":
                cursor = min(len(lines) - 1, cursor + 1)
            elif key == "pageup":
                cursor = max(0, cursor - body)
            elif key == "pagedown":
                cursor = min(len(lines) - 1, cursor + body)
    finally:
        keys.close()
        write(ANSI_SHOW + ALT_OFF)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pick a git repo under a folder and browse git log --graph --all.",
    )
    parser.add_argument(
        "dir",
        nargs="?",
        default=".",
        help="Folder to scan for git roots (default: current directory)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print git roots and exit (no TUI)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=COMMIT_LIMIT,
        help=f"Max commits in the graph (default {COMMIT_LIMIT})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    limit = max(20, args.limit)
    root = Path(args.dir).expanduser()
    if not root.exists() or not root.is_dir():
        sys.stderr.write(f"Not a directory: {root}\n")
        return 2
    if shutil.which("git") is None:
        sys.stderr.write("git is not on PATH.\n")
        return 2

    repos = discover_repos(root)
    if args.list:
        if not repos:
            sys.stderr.write(f"No git repos under {root.resolve()}\n")
            return 1
        for repo in repos:
            sys.stdout.write(f"{repo.path}\n")
        return 0

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        sys.stderr.write(
            "Need a real terminal. In PowerShell: python gitgraph.py [dir]\n"
        )
        return 2

    enable_windows_vt()
    if not repos:
        sys.stderr.write(f"No git repos under {root.resolve()}\n")
        return 1
    chosen = repos[0] if len(repos) == 1 else run_picker(repos)
    if chosen is None:
        return 0
    run_graph(chosen, limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
