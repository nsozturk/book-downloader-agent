import os
from pathlib import Path
from typing import List, Dict, Any
from bookdl.utils import save_json

def parse_markdown_file(category_prefix: str, filepath: Path) -> List[Dict[str, Any]]:
    """
    Parse markdown tables, extracting title, author, year from pipe-delimited rows.
    """
    books = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line.startswith('|') or not line.endswith('|'):
                continue
            
            if '---' in line:
                continue
                
            parts = [p.strip() for p in line.split('|')[1:-1]]
            
            if any(h.lower() in ['title', 'author', 'book', 'year'] for h in parts):
                continue
                
            if len(parts) >= 2:
                title = parts[0]
                author = parts[1]
                year = parts[2] if len(parts) > 2 else ''
                books.append({
                    'id': f"{category_prefix}_{hash(title + author)}",
                    'title': title,
                    'author': author,
                    'year': year,
                    'category': category_prefix
                })
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        
    return books

def extract_books(docs_dir: Path, output_file: Path) -> int:
    """
    Scan docs_dir for markdown files, parse them, and write combined JSON queue.
    """
    all_books = []
    
    if docs_dir.exists():
        for file in os.listdir(docs_dir):
            if file.endswith('.md'):
                filepath = docs_dir / file
                prefix = os.path.splitext(file)[0]
                books = parse_markdown_file(prefix, filepath)
                all_books.extend(books)
                
    if all_books:
        save_json(output_file, all_books)
        
    return len(all_books)
