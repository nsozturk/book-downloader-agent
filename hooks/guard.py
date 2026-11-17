#!/usr/bin/env python3
"""
PreToolUse guard of the book-downloader plugin.

Every session:
- file tools cannot touch the bookdl data folder (quarantine and virtual environment),
- a Bash command that names that folder is denied, unless it is a plain `bookdl ...` command.

The `bookdl-runner` subagent, in addition:
- Bash runs only plain `bookdl ...` commands, with relative paths, without `--output-dir` and `--library-dir`,
- file tools work only inside the working directory.

Downloaded books are untrusted. Their text must not reach an agent that can run commands.
"""
import json
import os
import re
import sys
from pathlib import Path

RUNNER_AGENTS = {'bookdl-runner', 'book-downloader:bookdl-runner'}
FILE_TOOLS = {'Read': 'file_path', 'Edit': 'file_path', 'Write': 'file_path',
              'NotebookEdit': 'notebook_path', 'Grep': 'path', 'Glob': 'path'}
PLAIN_BOOKDL = re.compile(r'[ \t]*bookdl([ \t]+[A-Za-z0-9_./,=:@%+~-]+)*[ \t]*')
RUNNER_BANNED = re.compile(r'(^|[\s=])[/~]|\.\.|--output-dir|--library-dir')


def data_dir() -> Path:
    base = os.environ.get('XDG_DATA_HOME') or str(Path.home() / '.local' / 'share')
    return Path(os.path.realpath(Path(base) / 'bookdl'))


def resolve(path: str, cwd: str) -> Path:
    return Path(os.path.realpath(os.path.join(cwd, os.path.expanduser(path))))


def is_inside(path: Path, folder: Path) -> bool:
    return path == folder or folder in path.parents


def deny(reason: str) -> None:
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': 'PreToolUse',
        'permissionDecision': 'deny',
        'permissionDecisionReason': reason,
    }}))
    sys.exit(0)


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        sys.exit(0)

    tool = event.get('tool_name', '')
    tool_input = event.get('tool_input') or {}
    cwd = event.get('cwd') or os.getcwd()
    is_runner = event.get('agent_type') in RUNNER_AGENTS
    protected = data_dir()

    if tool == 'Bash':
        command = str(tool_input.get('command', ''))
        plain = bool(PLAIN_BOOKDL.fullmatch(command))
        if is_runner and (not plain or RUNNER_BANNED.search(command)):
            deny("bookdl-runner can run only plain `bookdl ...` commands with relative paths "
                 "and without --output-dir or --library-dir.")
        names_protected = 'share/bookdl' in command or str(protected) in command
        if names_protected and not plain:
            deny("The bookdl data folder holds untrusted downloads. Use `bookdl status` or "
                 "`bookdl open <number>` instead of other commands on that folder.")
        sys.exit(0)

    if tool in FILE_TOOLS:
        raw = tool_input.get(FILE_TOOLS[tool]) or ''
        pattern = str(tool_input.get('pattern', '')) if tool == 'Glob' else ''
        target = resolve(str(raw), cwd)
        if is_inside(target, protected) or 'share/bookdl' in pattern or str(protected) in pattern:
            deny("Downloaded books are untrusted and can hold prompt injection. An agent must not "
                 "read or change the bookdl data folder. The user opens a book with `bookdl open`.")
        if is_runner and not is_inside(target, Path(os.path.realpath(cwd))):
            deny("bookdl-runner can use files only inside the working directory.")
        sys.exit(0)

    if is_runner:
        deny("bookdl-runner can use only Bash (`bookdl ...`), Read, Write, Edit, Grep and Glob.")
    sys.exit(0)


if __name__ == '__main__':
    main()
