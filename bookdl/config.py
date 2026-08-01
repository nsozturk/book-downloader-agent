import socket

ANNA_MIRRORS = ['annas-archive.gl', 'annas-archive.pk', 'annas-archive.gd', 'annas-archive.vg']
LIBGEN_MIRRORS = ['libgen.la', 'libgen.gl', 'libgen.vg', 'libgen.is', 'libgen.rs']
LIBGEN_SEARCH = 'http://libgen.li'
DEFAULT_OUTPUT_DIR = './downloads'
DEFAULT_QUEUE_FILE = './books_queue.json'
DEFAULT_LOG_FILE = './download_log.json'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'
}
MIN_FILE_SIZE = 10000

def enable_dns_bypass(ip: str = '104.21.34.70') -> None:
    """
    Monkey-patches socket.getaddrinfo to bypass DNS for libgen and booksdl domains.
    """
    print(f"WARNING: DNS bypass enabled using IP {ip}")
    _original_getaddrinfo = socket.getaddrinfo

    def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if 'booksdl' in host or 'libgen' in host:
            return _original_getaddrinfo(ip, port, family, type, proto, flags)
        return _original_getaddrinfo(host, port, family, type, proto, flags)

    socket.getaddrinfo = _patched_getaddrinfo
