import re
from dataclasses import dataclass
from typing import List, Optional

_ORDINALS = {1: ('1st', 'first'), 2: ('2nd', 'second'), 3: ('3rd', 'third'), 4: ('4th', 'fourth'),
             5: ('5th', 'fifth'), 6: ('6th', 'sixth'), 7: ('7th', 'seventh'), 8: ('8th', 'eighth'),
             9: ('9th', 'ninth'), 10: ('10th', 'tenth'), 11: ('11th', 'eleventh'), 12: ('12th', 'twelfth')}


@dataclass
class Candidate:
    md5: str
    title: str = ''
    author: str = ''
    publisher: str = ''
    year: str = ''
    language: str = ''
    ext: str = ''


def _language_matches(field: str, wanted: str) -> bool:
    """True if any language in a ';' or ',' separated field equals the wanted one, case-insensitive."""
    wanted = wanted.strip().lower()
    return any(part.strip().lower() == wanted for part in re.split(r'[;,]', field))


def _edition_matches(title: str, edition) -> bool:
    """Approximate: '6' matches '6th edition', '6th ed', 'sixth edition', 'edition 6', '6e'."""
    text = str(edition).strip().lower()
    number = int(text) if text.isdigit() else None
    if number is None:
        found = re.match(r'(\d+)', text)
        number = int(found.group(1)) if found else None
    lowered = title.lower()
    if number is None or number not in _ORDINALS:
        return bool(text) and text in lowered
    short, word = _ORDINALS[number]
    patterns = [
        rf'(?<![\w]){short}\s+ed(?:ition)?\b',
        rf'(?<![\w]){word}\s+ed(?:ition)?\b',
        rf'\bedition\s*(?:no\.?\s*|#\s*)?{number}(?!\d)',
        rf'(?<![\w]){number}e\b',
        rf'(?<![\w]){short}(?![\w])',
    ]
    return any(re.search(p, lowered) for p in patterns)


def rank_candidates(candidates: List[Candidate], book: dict) -> List[Candidate]:
    """
    Drops candidates with a known wrong extension. If the book names a language, also drops every
    candidate whose language is wrong or unknown. Then orders the rest:
    preferred format first, then year match, then edition match, then the original order.
    An empty result means the book is not found. Never fall back to a dropped candidate.
    """
    language = str(book.get('language') or '').strip()
    formats = [str(f).lower().lstrip('.') for f in (book.get('formats') or [])]
    year = str(book.get('year') or '').strip()
    edition = book.get('edition')
    edition = '' if edition is None else str(edition).strip()

    kept = []
    for candidate in candidates:
        if language and not _language_matches(candidate.language, language):
            continue
        ext = candidate.ext.strip().lower().lstrip('.')
        if formats and ext and ext not in formats:
            continue
        kept.append(candidate)

    def key(item):
        index, candidate = item
        ext = candidate.ext.strip().lower().lstrip('.')
        format_rank: Optional[int] = formats.index(ext) if formats and ext in formats else len(formats)
        year_rank = 0 if year and year in candidate.year else 1
        edition_rank = 0 if edition and _edition_matches(candidate.title, edition) else 1
        return (format_rank, year_rank, edition_rank, index)

    return [c for _, c in sorted(enumerate(kept), key=key)]
