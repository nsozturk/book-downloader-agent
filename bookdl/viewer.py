import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from bookdl.utils import safe_text

BOOK_SUFFIXES = ('.pdf', '.epub', '.djvu', '.mobi')
READERS = ['okular', 'zathura', 'evince', 'papers', 'mupdf']
HOST_DIRS = ['/bin', '/sbin', '/lib', '/lib64', '/lib32']
HOST_ETC = ['/etc/fonts', '/etc/ld.so.cache', '/etc/alternatives']
SANDBOX_HOME = '/home/reader'


def list_books(output_dir: Path) -> List[Path]:
    """
    Returns the book files in `output_dir`, sorted by name.
    """
    if not output_dir.is_dir():
        return []
    return sorted(p for p in output_dir.iterdir() if p.is_file() and p.name.lower().endswith(BOOK_SUFFIXES))


def find_book(output_dir: Path, target: str) -> Optional[Path]:
    """
    Finds one book by its list number or by a part of its name. Prints the list if there is no single match.
    """
    books = list_books(output_dir)
    if target.isdigit() and 1 <= int(target) <= len(books):
        return books[int(target) - 1]
    matches = [b for b in books if target and target.lower() in b.name.lower()]
    if len(matches) == 1:
        return matches[0]

    shown = matches or books
    print("No books yet." if not shown else "Pick one book by its number or by a part of its name:")
    for book in shown:
        print(f"  {books.index(book) + 1}. {safe_text(book.name, 200)}")
    return None


def find_reader() -> Optional[str]:
    """
    Returns the reader from the `BOOKDL_READER` environment variable, or the first installed reader in READERS.
    """
    candidates = [os.environ['BOOKDL_READER']] if os.environ.get('BOOKDL_READER') else READERS
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    return None


def _base_bind(bwrap: str) -> List[str]:
    """
    The bubblewrap arguments that both sandboxes share: no namespaces shared, a read-only system,
    an empty home folder and an empty /tmp.
    """
    cmd = [bwrap, '--unshare-all', '--die-with-parent', '--new-session', '--clearenv',
           '--ro-bind', '/usr', '/usr']
    for host_dir in HOST_DIRS:
        if os.path.islink(host_dir):
            cmd += ['--symlink', os.readlink(host_dir), host_dir]
        elif os.path.isdir(host_dir):
            cmd += ['--ro-bind', host_dir, host_dir]
    for etc_path in HOST_ETC:
        if os.path.exists(etc_path):
            cmd += ['--ro-bind', etc_path, etc_path]
    cmd += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--tmpfs', SANDBOX_HOME]
    return cmd


def sandbox_command(book: Path, reader: str, bwrap: str, wayland_socket: Path) -> List[str]:
    """
    Builds the bubblewrap command. Inside the sandbox the reader has:

    - no network and no access to the session D-Bus,
    - a read-only system, an empty home folder and an empty /tmp,
    - one book, read-only, and the Wayland socket to show its window.
    """
    runtime = f'/run/user/{os.getuid()}'
    cmd = _base_bind(bwrap)
    cmd += ['--dir', runtime, '--ro-bind', str(wayland_socket), f'{runtime}/wayland-0',
            '--ro-bind', str(book), f'/book/{book.name}',
            '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'HOME', SANDBOX_HOME,
            '--setenv', 'XDG_RUNTIME_DIR', runtime, '--setenv', 'WAYLAND_DISPLAY', 'wayland-0',
            '--setenv', 'QT_QPA_PLATFORM', 'wayland', '--setenv', 'GDK_BACKEND', 'wayland',
            '--setenv', 'LANG', 'C.UTF-8',
            '--chdir', '/book', reader, f'/book/{book.name}']
    return cmd


def tool_command(book: Path, argv: List[str], bwrap: str) -> List[str]:
    """
    Builds the bubblewrap command for a tool that parses an untrusted book (qpdf).
    The tool has no network, no display, and the book read-only at /book/<name>.
    """
    cmd = _base_bind(bwrap)
    cmd += ['--ro-bind', str(book), f'/book/{book.name}',
            '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'HOME', SANDBOX_HOME,
            '--setenv', 'LANG', 'C.UTF-8',
            '--chdir', '/book'] + list(argv)
    return cmd


def open_sandboxed(book: Path) -> int:
    """
    Opens one book in a reader inside a bubblewrap sandbox. Returns the exit code.
    Refuses to open the book without the sandbox.
    """
    bwrap = shutil.which('bwrap')
    if not bwrap:
        print("Error: bubblewrap (`bwrap`) is not installed. The book stays closed.")
        return 1
    reader = find_reader()
    if not reader:
        print(f"Error: no reader found. Install one of: {', '.join(READERS)}, or set BOOKDL_READER.")
        return 1

    display = os.environ.get('WAYLAND_DISPLAY', '')
    runtime_dir = os.environ.get('XDG_RUNTIME_DIR', '')
    wayland_socket = Path(display) if os.path.isabs(display) else Path(runtime_dir) / display
    if not display or not wayland_socket.exists():
        print("Error: a Wayland session is required. On X11 a window can read the keyboard of other windows.")
        return 1

    print(f"Opening in a sandbox with no network: {safe_text(book.name, 200)}")
    return subprocess.run(sandbox_command(book.resolve(), reader, bwrap, wayland_socket)).returncode
