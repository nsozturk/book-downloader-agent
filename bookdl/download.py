import hashlib
import os
import requests
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from bookdl import release
from bookdl.utils import build_queries, sanitize_filename, save_json, load_json, safe_text, book_id
from bookdl.net import https_get
from bookdl.match import rank_candidates
from bookdl.search import search_candidates, get_direct_download_url, get_working_mirror
from bookdl.config import VT_SECONDS_BETWEEN_LOOKUPS, HEADERS, LIBGEN_MIRRORS, MIN_FILE_SIZE, MAX_FILE_SIZE, ANNA_MIRRORS

_path_lock = threading.Lock()
_vt_lock = threading.Lock()
_vt_last_check = 0.0
DONE_STATUSES = ('RELEASED', 'QUARANTINED', 'SUCCESS')

def detect_book_type(head: bytes) -> Optional[str]:
    """
    Detects the book format from the first bytes of the file. Returns the extension or None.
    """
    if head[:5] == b'%PDF-':
        return 'pdf'
    if head[:4] == b'PK\x03\x04' and head[30:58] == b'mimetypeapplication/epub+zip':
        return 'epub'
    if head[:8] == b'AT&TFORM':
        return 'djvu'
    if head[60:68] in (b'BOOKMOBI', b'TEXtREAd'):
        return 'mobi'
    return None

def unique_path(output_dir: Path, base_name: str, ext: str) -> Path:
    """
    Returns a path that does not exist yet: `base_name.ext`, then `base_name (1).ext`, etc.
    """
    candidate = output_dir / f"{base_name}.{ext}"
    n = 1
    while candidate.exists():
        candidate = output_dir / f"{base_name} ({n}).{ext}"
        n += 1
    return candidate

def download_file(url: str, referer: str, expected_md5: str, output_dir: Path, base_name: str,
                  min_size: int = MIN_FILE_SIZE, max_size: int = MAX_FILE_SIZE) -> Optional[Path]:
    """
    Streams the file into a temp `.part` file, verifies HTTPS, size, MD5 and file type,
    then moves it to a new unique path. Returns the final path, or None on any failure.
    """
    headers = HEADERS.copy()
    if referer:
        headers['Referer'] = referer

    fd, tmp_name = tempfile.mkstemp(prefix='.bookdl-', suffix='.part', dir=output_dir)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, 'wb') as f:
            with https_get(url, headers=headers, stream=True, timeout=20) as r:
                r.raise_for_status()
                length = r.headers.get('Content-Length')
                if length and length.isdigit() and int(length) > max_size:
                    print(f"Rejected: Content-Length exceeds {max_size} bytes")
                    return None

                md5 = hashlib.md5()
                head = b''
                total = 0
                for chunk in r.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_size:
                        print(f"Rejected: download exceeds {max_size} bytes")
                        return None
                    if len(head) < 1024:
                        head += chunk[:1024 - len(head)]
                    md5.update(chunk)
                    f.write(chunk)

        if total < min_size:
            print(f"Rejected: file too small ({total} bytes)")
            return None
        if md5.hexdigest() != expected_md5.lower():
            print(f"Rejected: MD5 mismatch (expected {expected_md5.lower()}, got {md5.hexdigest()})")
            return None
        ext = detect_book_type(head)
        if not ext:
            print("Rejected: unknown file type")
            return None

        with _path_lock:
            dest_path = unique_path(output_dir, base_name, ext)
            os.replace(tmp_path, dest_path)
        return dest_path
    except (requests.RequestException, OSError) as e:
        print(f"Download error: {type(e).__name__}")
        return None
    finally:
        if tmp_path.exists():
            try:
                os.remove(tmp_path)
            except OSError:
                pass

def is_done(log_data: Dict[str, Any], book: Dict[str, Any]) -> bool:
    """
    True if the log says this book is already released or quarantined (the old SUCCESS counts too).
    """
    return log_data.get(book_id(book), {}).get('status') in DONE_STATUSES

def _check_rate_limited(path: Path) -> List[str]:
    """
    Runs release.check_book, at most one lookup per VT_SECONDS_BETWEEN_LOOKUPS when VT_API_KEY is set.
    """
    global _vt_last_check
    with _vt_lock:
        if os.environ.get('VT_API_KEY'):
            wait = _vt_last_check + VT_SECONDS_BETWEEN_LOOKUPS - time.monotonic()
            if wait > 0:
                time.sleep(wait)
        try:
            return release.check_book(path)
        finally:
            _vt_last_check = time.monotonic()

def _release_or_quarantine(path: Path, library_dir: Optional[Path]) -> Dict[str, Any]:
    """
    Runs the safety checks on a downloaded file and moves it to the library if it passes.
    Fail-closed: any error leaves the file in quarantine.
    """
    if library_dir is None:
        return {'status': 'QUARANTINED', 'file': str(path), 'reasons': ['release skipped']}
    try:
        reasons = _check_rate_limited(path)
        if not reasons:
            library_dir.mkdir(parents=True, exist_ok=True)
            destination = release.move_to_library(path, library_dir)
            return {'status': 'RELEASED', 'file': str(destination)}
    except Exception:
        reasons = ['check failed with an internal error']
    return {'status': 'QUARANTINED', 'file': str(path), 'reasons': reasons}

def process_book(book: Dict[str, Any], anna_mirror: str, output_dir: Path, library_dir: Optional[Path]) -> Dict[str, Any]:
    """
    Finds, downloads and checks one book. Returns the log entry:
    RELEASED, QUARANTINED (with reasons), NOT_FOUND or FAILED.
    """
    queries = build_queries(book.get('title', ''), book.get('author', ''), book.get('search_query', ''))
    formats = [f.lower().lstrip('.') for f in book.get('formats') or []]
    base_name = sanitize_filename(f"{book.get('title', 'Unknown')} - {book.get('author', 'Unknown')}")
    seen = set()
    found_any = False

    for query in queries:
        print(f"Searching: {safe_text(query)}")
        try:
            candidates = rank_candidates(search_candidates(query, anna_mirror), book)
        except Exception as e:
            print(f"Search error: {type(e).__name__}")
            continue
        for candidate in candidates:
            if candidate.md5 in seen:
                continue
            seen.add(candidate.md5)
            found_any = True
            url, referer = get_direct_download_url(candidate.md5, LIBGEN_MIRRORS)
            if not url:
                continue
            print(f"Downloading {safe_text(base_name)} (md5 {safe_text(candidate.md5, 32)})...")
            dest_path = download_file(url, referer or '', candidate.md5, output_dir, base_name)
            if not dest_path:
                continue
            real_ext = Path(dest_path).suffix.lower().lstrip('.')
            if formats and real_ext not in formats:
                print(f"Rejected: file type {safe_text(real_ext, 10)} is not in the wanted formats")
                Path(dest_path).unlink(missing_ok=True)
                continue
            print(f"Download successful: {safe_text(dest_path, 400)}")
            return _release_or_quarantine(Path(dest_path), library_dir)

    return {'status': 'FAILED'} if found_any else {'status': 'NOT_FOUND'}

def report_lines(results: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> List[str]:
    """
    Builds the final report: one line per processed book, then the SUMMARY line.
    """
    lines = []
    counts = {'RELEASED': 0, 'QUARANTINED': 0, 'NOT_FOUND': 0, 'FAILED': 0}
    for book, entry in results:
        status = entry.get('status')
        title = safe_text(book.get('title', 'Unknown'), 200)
        if status == 'RELEASED':
            lines.append(f"IN LIBRARY: {title} -> {safe_text(entry.get('file', ''), 400)}")
        elif status == 'QUARANTINED':
            lines.append(f"IN QUARANTINE: {title}: {safe_text('; '.join(entry.get('reasons', [])), 400)}")
        elif status == 'NOT_FOUND':
            lines.append(f"NOT FOUND: {title}")
        else:
            status = 'FAILED'
            lines.append(f"FAILED: {title}")
        counts[status] += 1
    lines.append(f"SUMMARY: library={counts['RELEASED']} quarantine={counts['QUARANTINED']} "
                 f"not_found={counts['NOT_FOUND']} failed={counts['FAILED']}")
    return lines

def print_report(results: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> None:
    """
    Prints the final report of a download run.
    """
    for line in report_lines(results):
        print(line)

def download_batch(books: List[Dict[str, Any]], output_dir: Path, queue_file: Path, log_file: Path, limit: int = 0,
                   categories: str = '', library_dir: Optional[Path] = None) -> None:
    """
    Sequential batch download with category filtering, safety checks and a final report.
    """
    anna_mirror = get_working_mirror(ANNA_MIRRORS, HEADERS)
    log_data = load_json(log_file, default={})
    cats = [c.strip() for c in categories.split(',')] if categories else []

    results = []
    for book in books:
        if limit > 0 and len(results) >= limit:
            break
        if cats and book.get('category') not in cats:
            continue
        if is_done(log_data, book):
            continue

        entry = process_book(book, anna_mirror, output_dir, library_dir)
        log_data[book_id(book)] = entry
        save_json(log_file, log_data)
        results.append((book, entry))

    print_report(results)

def download_parallel(books: List[Dict[str, Any]], output_dir: Path, log_file: Path, categories: str = '',
                      max_workers: int = 4, library_dir: Optional[Path] = None) -> None:
    """
    Parallel batch download using ThreadPoolExecutor, with safety checks and a final report.
    """
    anna_mirror = get_working_mirror(ANNA_MIRRORS, HEADERS)
    log_data = load_json(log_file, default={})
    lock = threading.Lock()
    cats = [c.strip() for c in categories.split(',')] if categories else []

    books_to_download = []
    seen_ids = set()
    for b in books:
        if (cats and b.get('category') not in cats) or is_done(log_data, b) or book_id(b) in seen_ids:
            continue
        seen_ids.add(book_id(b))
        books_to_download.append(b)

    def worker(book):
        entry = process_book(book, anna_mirror, output_dir, library_dir)
        with lock:
            log_data[book_id(book)] = entry
            save_json(log_file, log_data)
        return book, entry

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(worker, books_to_download))

    print_report(results)
