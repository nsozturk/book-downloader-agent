import socket
from typing import Iterable

ANNA_MIRRORS = ['annas-archive.gl', 'annas-archive.pk', 'annas-archive.gd', 'annas-archive.vg']
LIBGEN_MIRRORS = ['libgen.la', 'libgen.gl', 'libgen.vg', 'libgen.is', 'libgen.rs']
LIBGEN_SEARCH_HOST = 'libgen.li'
LIBGEN_SEARCH = f'https://{LIBGEN_SEARCH_HOST}'
DEFAULT_OUTPUT_DIR = './downloads'
DEFAULT_QUEUE_FILE = './books_queue.json'
DEFAULT_LOG_FILE = './download_log.json'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'
}
MIN_FILE_SIZE = 10000
MAX_FILE_SIZE = 500 * 1024 * 1024

def enable_dns_bypass(ip: str, hosts: Iterable[str]) -> None:
    """
    Monkey-patches socket.getaddrinfo so that only the exact hosts given resolve to `ip`.

    The IP must come from the user. TLS still verifies the certificate against the
    original hostname, so a wrong IP produces a certificate error, not a swapped file.
    """
    pinned = {h.lower() for h in hosts}
    print(f"WARNING: DNS bypass enabled: {', '.join(sorted(pinned))} -> {ip}")
    _original_getaddrinfo = socket.getaddrinfo

    def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if isinstance(host, str) and host.lower() in pinned:
            return _original_getaddrinfo(ip, port, family, type, proto, flags)
        return _original_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = _patched_getaddrinfo
