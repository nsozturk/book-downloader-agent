import re
import requests
from html.parser import HTMLParser
from typing import List, Tuple, Optional
from bookdl.config import LIBGEN_SEARCH
from bookdl.match import Candidate
from bookdl.net import https_get, safe_https_url

FIELD_LIMIT = 300
_MD5_LINK = re.compile(r'md5=([a-fA-F0-9]{32})(?![a-fA-F0-9])', re.IGNORECASE)


def _clean(text: str) -> str:
    """Normalizes whitespace and cuts the text to FIELD_LIMIT characters."""
    return ' '.join(text.split())[:FIELD_LIMIT]


class _ResultParser(HTMLParser):
    """
    Collects the rows of the libgen.li result table. A data row has 9 cells:
    title, author(s), publisher, year, language, pages, size, ext, mirrors.
    In the title cell only the text of the first link counts (the second link holds ISBNs).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: List[Candidate] = []
        self._cells: Optional[List[str]] = None
        self._md5 = ''
        self._cell: Optional[List[str]] = None
        self._links_seen = 0
        self._in_first_link = False

    def _end_cell(self) -> None:
        if self._cell is not None and self._cells is not None:
            self._cells.append(_clean(''.join(self._cell)))
        self._cell = None
        self._in_first_link = False

    def _end_row(self) -> None:
        self._end_cell()
        cells, md5 = self._cells, self._md5
        self._cells, self._md5 = None, ''
        if cells is None or len(cells) < 9 or not md5:
            return
        self.rows.append(Candidate(md5=md5.lower(), title=cells[0], author=cells[1], publisher=cells[2],
                                   year=cells[3], language=cells[4], ext=cells[7].lower()))

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self._end_row()
            self._cells, self._md5 = [], ''
        elif tag == 'td' and self._cells is not None:
            self._end_cell()
            self._cell = []
            self._links_seen = 0
        elif tag == 'a' and self._cells is not None:
            href = dict(attrs).get('href') or ''
            if not self._md5:
                found = _MD5_LINK.search(href)
                if found:
                    self._md5 = found.group(1)
            if self._cell is not None and len(self._cells) == 0:
                self._links_seen += 1
                self._in_first_link = self._links_seen == 1
        elif tag == 'br' and self._cell is not None and len(self._cells or []) != 0:
            self._cell.append(' ')

    def handle_endtag(self, tag):
        if tag == 'tr':
            self._end_row()
        elif tag == 'td':
            self._end_cell()
        elif tag == 'a':
            self._in_first_link = False

    def handle_data(self, data):
        if self._cell is None or self._cells is None:
            return
        if len(self._cells) == 0 and not self._in_first_link:
            return
        self._cell.append(data)

    def close(self):
        super().close()
        self._end_row()


def parse_libgen_rows(page: str) -> List[Candidate]:
    """Parses a libgen.li result page. Rows that are broken or have no md5 link are skipped."""
    parser = _ResultParser()
    try:
        parser.feed(page)
        parser.close()
    except Exception:
        pass
    return parser.rows


def get_working_mirror(mirrors: List[str], headers: dict) -> str:
    """
    Probes mirrors with /search?q=test and returns the first working one.
    """
    for mirror in mirrors:
        url = f"https://{mirror}/search?q=test"
        try:
            response = https_get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                return mirror
        except requests.RequestException:
            continue
    return mirrors[0] if mirrors else ""

def search_candidates(query: str, anna_mirror: str, max_candidates: int = 10) -> List[Candidate]:
    """
    Searches libgen.li (parsed result rows) and, when it gives too few, Anna's Archive (md5 only).
    Returns at most max_candidates, deduplicated by md5. A network error keeps what was gathered so far.
    """
    found: List[Candidate] = []
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        resp = https_get(f"{LIBGEN_SEARCH}/index.php", params={'req': query}, headers=headers, timeout=10)
        if resp.status_code == 200:
            found.extend(parse_libgen_rows(resp.text))
    except requests.RequestException:
        pass

    if len(found) < max_candidates and anna_mirror:
        try:
            resp = https_get(f"https://{anna_mirror}/search", params={'q': query}, headers=headers, timeout=10)
            if resp.status_code == 200:
                for md5 in re.findall(r'md5/([a-fA-F0-9]{32})', resp.text, re.IGNORECASE):
                    found.append(Candidate(md5=md5.lower()))
        except requests.RequestException:
            pass

    unique: List[Candidate] = []
    seen = set()
    for candidate in found:
        if candidate.md5 in seen:
            continue
        seen.add(candidate.md5)
        unique.append(candidate)
        if len(unique) >= max_candidates:
            break
    return unique

def search_md5_candidates(query: str, anna_mirror: str, max_candidates: int = 10) -> List[str]:
    """
    Searches for MD5 hashes using libgen.li and Anna's Archive.
    """
    return [c.md5 for c in search_candidates(query, anna_mirror, max_candidates)]

def get_direct_download_url(md5: str, libgen_mirrors: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Fetches the download URL for an MD5 hash from libgen mirrors over HTTPS.
    Returns (download_url, referer). The file type is detected later from the content.
    """
    headers = {'User-Agent': 'Mozilla/5.0'}
    for mirror in libgen_mirrors:
        try:
            url = f"https://{mirror}/ads.php?md5={md5}"
            resp = https_get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                match = re.search(r'href="(get\.php\?md5=[^"]+)"', resp.text)
                if not match:
                    match = re.search(r'href="([^"]+\.(?:pdf|epub))"', resp.text, re.IGNORECASE)
                if match:
                    link = safe_https_url(resp.url, match.group(1))
                    if link:
                        return link, url
        except requests.RequestException:
            continue
    return None, None
