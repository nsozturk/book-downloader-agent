import os
from pathlib import Path
from typing import Dict, Any
from bookdl.utils import load_json, save_json, sanitize_filename

def sync_log_from_disk(output_dir: Path, queue_file: Path, log_file: Path) -> Dict[str, Any]:
    """
    Scan .pdf/.epub/.djvu/.mobi files in output_dir, match against queue entries, update log with SUCCESS.
    Returns stats dict.
    """
    queue = load_json(queue_file, default=[])
    log_data = load_json(log_file, default={})
    
    disk_files = []
    if output_dir.exists():
        for file in os.listdir(output_dir):
            if file.endswith(('.pdf', '.epub', '.djvu', '.mobi')):
                disk_files.append(file)
                
    synced = 0
    success = 0
    failed = 0
    
    for book in queue:
        book_id = book.get('id')
        if not book_id:
            continue
            
        title = book.get('title', '')
        author = book.get('author', '')
        
        base_name = sanitize_filename(f"{title} - {author}")
        found = False
        
        for f in disk_files:
            if f.startswith(base_name):
                found = True
                log_data[book_id] = {'status': 'SUCCESS', 'file': str(output_dir / f)}
                synced += 1
                success += 1
                break
                
        if not found:
            if log_data.get(book_id, {}).get('status') == 'SUCCESS':
                log_data[book_id] = {'status': 'FAILED'}
            if log_data.get(book_id, {}).get('status') == 'FAILED':
                failed += 1
                
    save_json(log_file, log_data)
    
    total = len(queue)
    not_found = total - success - failed
    
    return {
        'total': total,
        'success': success,
        'failed': failed,
        'not_found': not_found,
        'remaining': total - success,
        'synced': synced
    }
