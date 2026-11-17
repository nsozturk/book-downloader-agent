import html
import ipaddress
import socket
from typing import Dict, Iterable, Optional, Set
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import getproxies

import requests

MAX_REDIRECTS = 5

_pinned: Dict[str, str] = {}
_proxy_hosts: Set[str] = set()
_guard_installed = False


class BlockedAddressError(OSError):
    """A host resolved to an address that is not on the public internet."""


class UnsafeURLError(requests.RequestException):
    """A URL or a redirect target is not HTTPS, or it points at a local address."""


def is_public_ip(addr: str) -> bool:
    """
    True only for a globally routable address. Loopback, private, link-local and reserved ranges give False.
    """
    try:
        ip = ipaddress.ip_address(addr.split('%')[0])
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global


def install_network_guard(bypass_ip: str = '', bypass_hosts: Iterable[str] = ()) -> None:
    """
    Monkey-patches socket.getaddrinfo for the whole process:

    - a host that resolves to a non-public address raises BlockedAddressError. The check runs at
      connect time, so it also covers redirects and DNS rebinding.
    - if `bypass_ip` is given, only the exact `bypass_hosts` resolve to it. The IP must come from
      the user. TLS still verifies the certificate against the original hostname.

    The hosts of the proxies from the environment are exempt, because a local proxy is the user's choice.
    """
    global _guard_installed

    for proxy_url in getproxies().values():
        proxy_host = urlsplit(proxy_url if '://' in proxy_url else f'//{proxy_url}').hostname
        if proxy_host:
            _proxy_hosts.add(proxy_host.lower())

    if bypass_ip:
        ipaddress.ip_address(bypass_ip)
        for host in bypass_hosts:
            _pinned[host.lower()] = bypass_ip
        print(f"WARNING: DNS bypass enabled: {', '.join(sorted(_pinned))} -> {bypass_ip}")

    if _guard_installed:
        return
    _guard_installed = True
    _original_getaddrinfo = socket.getaddrinfo

    def _guarded_getaddrinfo(host, port, *args, **kwargs):
        key = host.lower() if isinstance(host, str) else host
        if key in _pinned:
            return _original_getaddrinfo(_pinned[key], port, *args, **kwargs)
        results = _original_getaddrinfo(host, port, *args, **kwargs)
        if key in _proxy_hosts:
            return results
        for result in results:
            if not is_public_ip(str(result[4][0])):
                raise BlockedAddressError("host resolves to a non-public address")
        return results

    socket.getaddrinfo = _guarded_getaddrinfo


def safe_https_url(base: str, link: str) -> Optional[str]:
    """
    Resolves `link` against `base`, upgrades http:// to https:// and rejects any other scheme.
    Also rejects `localhost` and any IP literal that is not public.
    """
    absolute = urljoin(base, html.unescape(link))
    parts = urlsplit(absolute)
    if parts.scheme == 'http':
        parts = parts._replace(scheme='https')
    elif parts.scheme != 'https':
        return None
    host = (parts.hostname or '').lower()
    if not host or host == 'localhost' or host.endswith('.localhost'):
        return None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not is_public_ip(host):
            return None
    return urlunsplit(parts)


def https_get(url: str, headers: Optional[dict] = None, params: Optional[dict] = None,
              timeout: float = 10, stream: bool = False) -> requests.Response:
    """
    GET over HTTPS only. Follows redirects itself, so that every hop passes `safe_https_url`.
    Raises UnsafeURLError for an unsafe URL and requests.TooManyRedirects after MAX_REDIRECTS hops.
    """
    current = safe_https_url(url, '')
    if not current:
        raise UnsafeURLError("URL is not HTTPS or points at a local address")

    for _ in range(MAX_REDIRECTS + 1):
        response = requests.get(current, headers=headers, params=params, timeout=timeout,
                                stream=stream, allow_redirects=False)
        if not response.is_redirect:
            return response
        location = response.headers.get('Location', '')
        response.close()
        current = safe_https_url(response.url, location)
        if not current:
            raise UnsafeURLError("redirect target is not HTTPS or points at a local address")
        params = None

    raise requests.TooManyRedirects(f"more than {MAX_REDIRECTS} redirects")
