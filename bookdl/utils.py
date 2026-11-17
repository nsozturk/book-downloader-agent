import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, List

def sanitize_filename(name: str) -> str:
    """
    Strips illegal characters and limits the filename to 150 chars.
    """
    name = re.sub(r'[\\/*?:"<>|]', '', name)
    return name.strip()[:150]

def safe_text(text: Any, limit: int = 120) -> str:
    """
    Makes a string safe to print: one line, printable characters only, at most `limit` characters.
    An AI agent reads the output, so text from a server or from a book list must not reach it raw.
    """
    return ''.join(c if c.isprintable() else ' ' for c in str(text))[:limit]

def clean_query_text(text: str) -> str:
    """
    Removes parentheticals, brackets, and academic abbreviations.
    """
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\b(ed\.|eds\.|vol\.|rev\.|2nd|3rd)\b', '', text, flags=re.IGNORECASE)
    return text.strip()

def build_queries(title: str, author: str, search_query: str = '') -> List[str]:
    """
    Generates ordered fallback search queries based on title and author.
    """
    queries = []
    if search_query:
        queries.append(search_query)

    clean_title = clean_query_text(title)
    clean_author = clean_query_text(author)
    primary_author = clean_author.split(',')[0].strip() if clean_author else ''
    last_name = primary_author.split()[-1] if primary_author else ''

    queries.append(f"{clean_title} {primary_author}".strip())
    
    short_title = re.split(r'[:\-]', clean_title)[0].strip()
    queries.append(f"{short_title} {last_name}".strip())

    stopwords = {'with', 'from', 'this', 'that', 'then', 'than', 'into', 'upon', 'over', 'some', 'such'}
    words = [w for w in re.findall(r'\b\w{4,}\b', clean_title.lower()) if w not in stopwords]
    niche_keywords = " ".join(words)
    queries.append(f"{niche_keywords} {last_name}".strip())

    queries.append(short_title)

    deduped = []
    for q in queries:
        q = q.strip()
        if q and q not in deduped:
            deduped.append(q)

    return deduped

def load_json(filepath: Path, default: Any = None) -> Any:
    """
    Safe JSON read with try/except for FileNotFoundError and json.JSONDecodeError.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def save_json(filepath: Path, data: Any) -> None:
    """
    Atomic write using tempfile + os.replace.
    """
    filepath = Path(filepath)
    dir_name = filepath.parent
    dir_name.mkdir(parents=True, exist_ok=True)
    
    fd, temp_path = tempfile.mkstemp(dir=dir_name, text=True)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    os.replace(temp_path, filepath)
