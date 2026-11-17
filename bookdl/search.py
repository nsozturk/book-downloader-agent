import html
import re
import requests
from urllib.parse import urljoin, urlsplit, urlunsplit
from typing import List, Tuple, Optional
from bookdl.config import LIBGEN_SEARCH

def get_working_mirror(mirrors: List[str], headers: dict) -> str:
    """
    Probes mirrors with /search?q=test and returns the first working one.
    """
    for mirror in mirrors:
        url = f"https://{mirror}/search?q=test"
        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                return mirror
        except requests.RequestException:
            continue
    return mirrors[0] if mirrors else ""

def search_md5_candidates(query: str, anna_mirror: str, max_candidates: int = 10) -> List[str]:
    """
    Searches for MD5 hashes using libgen.li and Anna's Archive.
    """
    md5_list = []
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        resp = requests.get(f"{LIBGEN_SEARCH}/index.php", params={'req': query}, headers=headers, timeout=10)
        if resp.status_code == 200:
            md5_list.extend(re.findall(r'md5=([a-fA-F0-9]{32})', resp.text, re.IGNORECASE))
    except requests.RequestException:
        pass

    if len(md5_list) < max_candidates and anna_mirror:
        try:
            resp = requests.get(f"https://{anna_mirror}/search", params={'q': query}, headers=headers, timeout=10)
            if resp.status_code == 200:
                md5_list.extend(re.findall(r'md5/([a-fA-F0-9]{32})', resp.text, re.IGNORECASE))
        except requests.RequestException:
            pass

    unique = []
    for md5 in md5_list:
        md5_lower = md5.lower()
        if md5_lower not in unique:
            unique.append(md5_lower)
            if len(unique) >= max_candidates:
                break
    return unique

def _safe_https_url(base: str, link: str) -> Optional[str]:
    """
    Resolves `link` against `base`, upgrades http:// to https:// and rejects any other scheme.
    """
    absolute = urljoin(base, html.unescape(link))
    parts = urlsplit(absolute)
    if parts.scheme == 'http':
        parts = parts._replace(scheme='https')
    elif parts.scheme != 'https':
        return None
    if not parts.netloc:
        return None
    return urlunsplit(parts)

def get_direct_download_url(md5: str, libgen_mirrors: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Fetches the download URL for an MD5 hash from libgen mirrors over HTTPS.
    Returns (download_url, referer). The file type is detected later from the content.
    """
    headers = {'User-Agent': 'Mozilla/5.0'}
    for mirror in libgen_mirrors:
        try:
            url = f"https://{mirror}/ads.php?md5={md5}"
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200 and resp.url.startswith('https://'):
                match = re.search(r'href="(get\.php\?md5=[^"]+)"', resp.text)
                if not match:
                    match = re.search(r'href="([^"]+\.(?:pdf|epub))"', resp.text, re.IGNORECASE)
                if match:
                    link = _safe_https_url(resp.url, match.group(1))
                    if link:
                        return link, url
        except requests.RequestException:
            continue
    return None, None
