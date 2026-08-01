import os
import requests
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict, Any

from bookdl.utils import build_queries, sanitize_filename, save_json, load_json
from bookdl.search import search_md5_candidates, get_direct_download_url, get_working_mirror
from bookdl.config import HEADERS, LIBGEN_MIRRORS, MIN_FILE_SIZE, ANNA_MIRRORS

def download_file(url: str, referer: str, dest_path: Path, min_size: int = MIN_FILE_SIZE) -> bool:
    """
    Streaming download with size validation and proper error handling.
    """
    headers = HEADERS.copy()
    if referer:
        headers['Referer'] = referer

    try:
        with requests.get(url, headers=headers, stream=True, timeout=20) as r:
            r.raise_for_status()
            with open(dest_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        if os.path.getsize(dest_path) < min_size:
            os.remove(dest_path)
            return False
        return True
    except Exception:
        if dest_path.exists():
            try:
                os.remove(dest_path)
            except OSError:
                pass
        return False

def download_book(book: Dict[str, Any], anna_mirror: str, output_dir: Path, log_data: Dict[str, Any], log_file: Path) -> bool:
    """
    Full pipeline for downloading a single book.
    """
    queries = build_queries(book.get('title', ''), book.get('author', ''), book.get('search_query', ''))
    
    for query in queries:
        print(f"Searching: {query}")
        md5_candidates = search_md5_candidates(query, anna_mirror)
        for md5 in md5_candidates:
            url, ext, referer = get_direct_download_url(md5, LIBGEN_MIRRORS)
            if url and ext:
                filename = sanitize_filename(f"{book.get('title', 'Unknown')} - {book.get('author', 'Unknown')}.{ext}")
                dest_path = output_dir / filename
                print(f"Downloading {filename}...")
                if download_file(url, referer or '', dest_path):
                    print("Download successful!")
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
                url, ext, referer = get_direct_download_url(md5, LIBGEN_MIRRORS)
                if url and ext:
                    filename = sanitize_filename(f"{book.get('title', 'Unknown')} - {book.get('author', 'Unknown')}.{ext}")
                    dest_path = output_dir / filename
                    if download_file(url, referer or '', dest_path):
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
