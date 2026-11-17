import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, List, Set, Tuple

from bookdl import config
from bookdl.net import https_get
from bookdl.utils import safe_text
from bookdl.viewer import find_book, list_books, tool_command

PDF_BAD_KEYS = {'/JS': 'JavaScript', '/JavaScript': 'JavaScript', '/XFA': 'XFA',
                '/EmbeddedFiles': 'EmbeddedFiles', '/EF': 'EmbeddedFiles', '/RichMedia': 'RichMedia'}
PDF_BAD_ACTIONS = {'/JavaScript', '/Launch', '/SubmitForm', '/ImportData', '/GoToE', '/Rendition'}

EPUB_BAD_EXTENSIONS = ('.exe', '.dll', '.js', '.jar', '.sh', '.bat', '.cmd', '.scr', '.vbs', '.ps1',
                       '.apk', '.so', '.dylib', '.msi', '.com', '.py')
EPUB_BINARY_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.ttf', '.otf', '.woff', '.woff2', '.mp3', '.mp4')
EPUB_BAD_MARKUP = ('<script', 'javascript:', '<iframe', '<object', '<embed')
EPUB_EVENT_HANDLER = re.compile(r'<[^>]*\son[a-z]+\s*=')
EPUB_MAX_MEMBERS = 20000
EPUB_MAX_TOTAL = 2 * 1024 ** 3
EPUB_MAX_RATIO = 200
EPUB_RATIO_MIN_SIZE = 10 * 1024 ** 2
EPUB_MAX_READ = 20 * 1024 ** 2

TOOL_TIMEOUT = 300

_warned: Set[str] = set()


def _warn(key: str, message: str) -> None:
    """
    Prints a warning line once per run of `release_books`.
    """
    if key not in _warned:
        _warned.add(key)
        print(f"WARNING: {message}")


def file_sha256(path: Path) -> str:
    """
    Streams the file and returns its SHA-256 as lowercase hex.
    """
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def virustotal_check(sha256: str, api_key: str) -> Tuple[str, str]:
    """
    Looks the hash up on VirusTotal (API v3, "get a file report").
    Returns (status, detail). Status is 'clean', 'malicious', 'unknown' or 'error'.
    The detail never holds text from the server.
    """
    try:
        response = https_get(f'{config.VT_API_URL}/files/{sha256}', headers={'x-apikey': api_key}, timeout=20)
        code = response.status_code
        if code == 404:
            return 'unknown', 'hash not known to VirusTotal'
        if code == 429:
            return 'error', 'VirusTotal quota exceeded'
        if code != 200:
            return 'error', f'VirusTotal answered with status {int(code)}'
        stats = response.json()['data']['attributes']['last_analysis_stats']
        malicious = int(stats['malicious'])
        suspicious = int(stats['suspicious'])
    except Exception:
        return 'error', 'VirusTotal lookup failed'
    if malicious + suspicious > config.VT_MAX_DETECTIONS:
        return 'malicious', f'malicious={malicious} suspicious={suspicious}'
    return 'clean', 'no detections'


def pdf_active_content(qpdf_json: Any) -> List[str]:
    """
    Walks the qpdf JSON and returns sorted unique labels of active content in the PDF.
    A /GoTo destination in /OpenAction or /AA and /URI links are not findings.
    """
    found: Set[str] = set()
    stack = [qpdf_json]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if key in PDF_BAD_KEYS:
                    found.add(PDF_BAD_KEYS[key])
                if key == '/S' and isinstance(value, str) and value in PDF_BAD_ACTIONS:
                    found.add(value[1:])
                stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
    return sorted(found)


def inspect_pdf(path: Path) -> List[str]:
    """
    Inspects the PDF with `qpdf` inside a sandbox with no network. Fail-closed: if the file cannot be
    inspected (no qpdf, no bwrap, encrypted, qpdf error) the answer is one finding.
    """
    cannot = ['cannot inspect PDF']
    qpdf = shutil.which('qpdf')
    bwrap = shutil.which('bwrap')
    if not qpdf or not bwrap:
        return cannot
    book = path.resolve()
    inner = f'/book/{book.name}'
    try:
        encrypted = subprocess.run(tool_command(book, [qpdf, '--is-encrypted', inner], bwrap),
                                   stdin=subprocess.DEVNULL, capture_output=True, timeout=TOOL_TIMEOUT)
        if encrypted.returncode != 2:
            return cannot
        result = subprocess.run(
            tool_command(book, [qpdf, '--json-output', '--json-stream-data=none', inner], bwrap),
            stdin=subprocess.DEVNULL, capture_output=True, timeout=TOOL_TIMEOUT)
        if result.returncode not in (0, 3):
            return cannot
        return pdf_active_content(json.loads(result.stdout))
    except (OSError, subprocess.SubprocessError, ValueError, MemoryError, RecursionError):
        return cannot


def _bad_member_name(name: str) -> bool:
    normalized = name.replace('\\', '/')
    return normalized.startswith('/') or ':' in normalized.split('/')[0] or '..' in PurePosixPath(normalized).parts


def _bad_markup(data: bytes) -> bool:
    """
    True if the bytes hold a script, an embedded object or an event handler, in UTF-8 or UTF-16.
    Character references such as `&#115;` are decoded first.
    """
    for encoding in ('utf-8', 'utf-16'):
        text = html.unescape(data.decode(encoding, errors='ignore')).lower()
        if any(marker in text for marker in EPUB_BAD_MARKUP) or EPUB_EVENT_HANDLER.search(text):
            return True
    return False


def inspect_epub(path: Path) -> List[str]:
    """
    Inspects the EPUB (a zip file) with `zipfile` only. Returns sorted unique findings.
    """
    found: Set[str] = set()
    try:
        with zipfile.ZipFile(path) as zf:
            members = zf.infolist()
            if len(members) > EPUB_MAX_MEMBERS:
                found.add('too many members')
            if sum(m.file_size for m in members) > EPUB_MAX_TOTAL:
                found.add('uncompressed size over 2 GiB')
            for member in members:
                name = member.filename
                lower = name.lower()
                if _bad_member_name(name):
                    found.add('unsafe member path')
                if lower.endswith(EPUB_BAD_EXTENSIONS):
                    found.add('executable or script member')
                if member.file_size > EPUB_RATIO_MIN_SIZE and \
                        member.file_size > EPUB_MAX_RATIO * max(member.compress_size, 1):
                    found.add('suspicious compression ratio')
                if member.is_dir() or lower.endswith(EPUB_BINARY_EXTENSIONS):
                    continue
                if member.file_size > EPUB_MAX_READ:
                    found.add('text member too large to inspect')
                    continue
                with zf.open(member) as f:
                    if _bad_markup(f.read(EPUB_MAX_READ + 1)):
                        found.add('active content in markup')
    except Exception:
        return ['cannot inspect EPUB']
    return sorted(found)


def check_book(path: Path) -> List[str]:
    """
    Runs the checks in order (VirusTotal, active content) and returns the failure reasons.
    An empty list means the book passed. Prints a warning line for each check that did not run.
    A file type with no content check (DjVu, MOBI) passes only with a clean VirusTotal verdict.
    """
    reasons: List[str] = []

    vt_clean = False
    api_key = os.environ.get('VT_API_KEY', '')
    if api_key:
        status, detail = virustotal_check(file_sha256(path), api_key)
        vt_clean = status == 'clean'
        if status in ('malicious', 'error'):
            reasons.append(f'VirusTotal: {detail}')
        elif status == 'unknown':
            _warn('vt-unknown', 'a hash is not known to VirusTotal, so that file was not checked there')
    else:
        _warn('vt-key', 'VT_API_KEY is not set, VirusTotal check skipped')

    suffix = path.suffix.lower()
    if suffix == '.pdf':
        reasons += [f'PDF: {finding}' for finding in inspect_pdf(path)]
    elif suffix == '.epub':
        reasons += [f'EPUB: {finding}' for finding in inspect_epub(path)]
    elif not vt_clean:
        reasons.append(f'{suffix} files have no content check, and there is no VirusTotal verdict')
    return reasons


def move_to_library(book: Path, library_dir: Path) -> Path:
    """
    Copies the book to a temp file in the library folder, verifies the copy, gives it a name that
    does not exist yet, then deletes the original. Never overwrites a file and never leaves a partial one.
    """
    fd, tmp_name = tempfile.mkstemp(prefix='.bookdl-', suffix='.part', dir=library_dir)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        shutil.copyfile(book, tmp_path)
        if file_sha256(tmp_path) != file_sha256(book):
            raise OSError("copy does not match the original")
        n = 0
        while True:
            suffix = f" ({n})" if n else ""
            destination = library_dir / f"{book.stem}{suffix}{book.suffix}"
            try:
                os.link(tmp_path, destination)
                break
            except FileExistsError:
                n += 1
    finally:
        tmp_path.unlink(missing_ok=True)
    book.unlink()
    return destination


def release_books(output_dir: Path, library_dir: Path, target: str, release_all: bool) -> int:
    """
    Checks books in the quarantine folder and moves each book that passes to the library folder.
    Returns 0 if every processed book was released, otherwise 1.
    """
    _warned.clear()
    if release_all:
        books = list_books(output_dir)
        if not books:
            print("No books yet.")
            return 1
    else:
        book = find_book(output_dir, target)
        if not book:
            return 1
        books = [book]

    library_dir.mkdir(parents=True, exist_ok=True)
    exit_code = 0
    for index, book in enumerate(books):
        if index and os.environ.get('VT_API_KEY'):
            time.sleep(config.VT_SECONDS_BETWEEN_LOOKUPS)
        name = safe_text(book.name, 200)
        try:
            reasons = check_book(book)
            if not reasons:
                destination = move_to_library(book, library_dir)
                print(f"RELEASED: {name} -> {safe_text(destination, 300)}")
                continue
        except OSError:
            reasons = ['file could not be read or moved']
        except Exception:
            reasons = ['check failed with an internal error']
        print(f"KEPT IN QUARANTINE: {name}: {safe_text('; '.join(reasons), 300)}")
        exit_code = 1
    return exit_code
