import os
from pathlib import Path

ANNA_MIRRORS = ['annas-archive.gl', 'annas-archive.pk', 'annas-archive.gd', 'annas-archive.vg']
LIBGEN_MIRRORS = ['libgen.la', 'libgen.gl', 'libgen.vg', 'libgen.is', 'libgen.rs']
LIBGEN_SEARCH_HOST = 'libgen.li'
LIBGEN_SEARCH = f'https://{LIBGEN_SEARCH_HOST}'
DEFAULT_QUEUE_FILE = './books_queue.json'
DEFAULT_LOG_FILE = './download_log.json'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'
}
MIN_FILE_SIZE = 10000
MAX_FILE_SIZE = 500 * 1024 * 1024
VT_API_URL = 'https://www.virustotal.com/api/v3'
VT_MAX_DETECTIONS = 0
VT_SECONDS_BETWEEN_LOOKUPS = 16  # public API: 4 requests per minute

def default_output_dir() -> Path:
    """
    The quarantine folder: `$XDG_DATA_HOME/bookdl/quarantine` (default `~/.local/share/bookdl/quarantine`).
    It is outside the folders that desktop file indexers scan by default.
    """
    base = os.environ.get('XDG_DATA_HOME') or str(Path.home() / '.local' / 'share')
    return Path(base) / 'bookdl' / 'quarantine'

def prepare_quarantine(path: Path) -> None:
    """
    Creates the quarantine folder with mode 0700 and adds marker files that tell indexers to skip it.
    """
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    for marker in ('.trackerignore', '.nomedia'):
        (path / marker).touch(exist_ok=True)

def default_library_dir() -> Path:
    """
    The library folder for books that passed the checks: `~/Books`. It is outside the bookdl data folder.
    """
    return Path.home() / 'Books'
