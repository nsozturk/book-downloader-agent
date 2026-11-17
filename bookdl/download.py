import hashlib
import os
import requests
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict, Any, Optional

from bookdl.utils import build_queries, sanitize_filename, save_json, load_json, safe_text
from bookdl.net import https_get
from bookdl.search import search_md5_candidates, get_direct_download_url, get_working_mirror
from bookdl.config import HEADERS, LIBGEN_MIRRORS, MIN_FILE_SIZE, MAX_FILE_SIZE, ANNA_MIRRORS

_path_lock = threading.Lock()

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

def download_book(book: Dict[str, Any], anna_mirror: str, output_dir: Path, log_data: Dict[str, Any], log_file: Path) -> bool:
    """
    Full pipeline for downloading a single book.
    """
    queries = build_queries(book.get('title', ''), book.get('author', ''), book.get('search_query', ''))
    
    for query in queries:
        print(f"Searching: {safe_text(query)}")
        md5_candidates = search_md5_candidates(query, anna_mirror)
        for md5 in md5_candidates:
            url, referer = get_direct_download_url(md5, LIBGEN_MIRRORS)
            if url:
                base_name = sanitize_filename(f"{book.get('title', 'Unknown')} - {book.get('author', 'Unknown')}")
                print(f"Downloading {safe_text(base_name)} (md5 {md5})...")
                dest_path = download_file(url, referer or '', md5, output_dir, base_name)
                if dest_path:
                    print(f"Download successful: {safe_text(dest_path, 400)}")
                    book_id = book.get('id', str(hash(book.get('title'))))
                    log_data[book_id] = {'status': 'SUCCESS', 'file': str(dest_path)}
                    save_json(log_file, log_data)
                    return True
    
    print("Download failed.")
    book_id = book.get('id', str(hash(book.get('title'))))
    log_data[book_id] = {'status': 'FAILED'}
    save_json(log_file, log_data)
    return False

def download_batch(books: List[Dict[str, Any]], output_dir: Path, queue_file: Path, log_file: Path, limit: int = 0, categories: str = '') -> None:
    """
    Sequential batch download with category filtering and progress reporting.
    """
    anna_mirror = get_working_mirror(ANNA_MIRRORS, HEADERS)
    log_data = load_json(log_file, default={})
    cats = [c.strip() for c in categories.split(',')] if categories else []

    count = 0
    for book in books:
        if limit > 0 and count >= limit:
            break
        if cats and book.get('category') not in cats:
            continue
            
        book_id = book.get('id', str(hash(book.get('title'))))
        if log_data.get(book_id, {}).get('status') == 'SUCCESS':
            continue
            
        download_book(book, anna_mirror, output_dir, log_data, log_file)
        count += 1

def download_parallel(books: List[Dict[str, Any]], output_dir: Path, log_file: Path, categories: str = '', max_workers: int = 4) -> None:
    """
    Parallel batch download grouped by category_group using ThreadPoolExecutor.
    """
    anna_mirror = get_working_mirror(ANNA_MIRRORS, HEADERS)
    log_data = load_json(log_file, default={})
    lock = threading.Lock()
    cats = [c.strip() for c in categories.split(',')] if categories else []

    books_to_download = []
    for book in books:
        if cats and book.get('category') not in cats:
            continue
        book_id = book.get('id', str(hash(book.get('title'))))
        if log_data.get(book_id, {}).get('status') == 'SUCCESS':
            continue
        books_to_download.append(book)

    def worker(book):
        book_id = book.get('id', str(hash(book.get('title'))))
        queries = build_queries(book.get('title', ''), book.get('author', ''), book.get('search_query', ''))
        
        for query in queries:
            md5_candidates = search_md5_candidates(query, anna_mirror)
            for md5 in md5_candidates:
                url, referer = get_direct_download_url(md5, LIBGEN_MIRRORS)
                if url:
                    base_name = sanitize_filename(f"{book.get('title', 'Unknown')} - {book.get('author', 'Unknown')}")
                    dest_path = download_file(url, referer or '', md5, output_dir, base_name)
                    if dest_path:
                        print(f"Download successful: {safe_text(dest_path, 400)}")
                        with lock:
                            log_data[book_id] = {'status': 'SUCCESS', 'file': str(dest_path)}
                            save_json(log_file, log_data)
                        return True
        with lock:
            log_data[book_id] = {'status': 'FAILED'}
            save_json(log_file, log_data)
        return False

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for _ in executor.map(worker, books_to_download):
            pass
