import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from bookdl.utils import load_json, save_json, sanitize_filename, book_id

BOOK_SUFFIXES = ('.pdf', '.epub', '.djvu', '.mobi')

def _list_book_files(folder: Optional[Path]) -> List[str]:
    """
    Names of the book files directly inside `folder` (empty list if it does not exist).
    """
    if folder is None or not folder.exists():
        return []
    return [f for f in os.listdir(folder) if f.endswith(BOOK_SUFFIXES)]

def sync_log_from_disk(output_dir: Path, queue_file: Path, log_file: Path, library_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Scan the quarantine folder (output_dir) and the library folder for book files, match them against
    queue entries by book_id, and update the log: RELEASED for a match in the library, QUARANTINED for a
    match in quarantine. A RELEASED entry whose file still exists is never downgraded. Returns stats dict.
    """
    queue = load_json(queue_file, default=[])
    log_data = load_json(log_file, default={})

    quarantine_files = _list_book_files(output_dir)
    library_files = _list_book_files(library_dir)

    synced = 0
    released = 0
    quarantined = 0
    failed = 0

    for book in queue:
        bid = book_id(book)
        base_name = sanitize_filename(f"{book.get('title', '')} - {book.get('author', '')}")
        entry = log_data.get(bid, {})

        in_library = next((f for f in library_files if f.startswith(base_name)), None)
        in_quarantine = next((f for f in quarantine_files if f.startswith(base_name)), None)

        if in_library:
            log_data[bid] = {'status': 'RELEASED', 'file': str(library_dir / in_library)}
            released += 1
            synced += 1
        elif entry.get('status') == 'RELEASED' and entry.get('file') and Path(entry['file']).exists():
            released += 1
        elif in_quarantine:
            log_data[bid] = {'status': 'QUARANTINED', 'file': str(output_dir / in_quarantine),
                             'reasons': entry.get('reasons', [])}
            quarantined += 1
            synced += 1
        else:
            if entry.get('status') in ('RELEASED', 'QUARANTINED', 'SUCCESS'):
                log_data[bid] = {'status': 'FAILED'}
            if log_data.get(bid, {}).get('status') == 'FAILED':
                failed += 1

    save_json(log_file, log_data)

    total = len(queue)
    done = released + quarantined
    not_found = total - done - failed

    return {
        'total': total,
        'released': released,
        'quarantined': quarantined,
        'failed': failed,
        'not_found': not_found,
        'remaining': total - done,
        'synced': synced
    }
