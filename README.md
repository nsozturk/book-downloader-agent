<div align="center">
  <img src="header.jpg" alt="Book Downloader Agent Header" width="100%">
</div>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&style=flat-square" alt="Python Version">
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License: MIT">
  <img src="https://img.shields.io/badge/Source-Anna's%20Archive-e74c3c?style=flat-square&logo=bookstack" alt="Source: Anna's Archive">
  <img src="https://img.shields.io/badge/Books%20Downloaded-1400%2B-blueviolet?style=flat-square" alt="Books Downloaded: 1400+">
  <img src="https://img.shields.io/badge/Success%20Rate-99%25-brightgreen?style=flat-square" alt="Success Rate: 99%">
</p>

# Book Downloader Agent

> 📚 An AI agent system that bulk-downloads books from **[Anna's Archive](https://annas-archive.org)** and shadow library mirrors (LibGen, IPFS) — no API keys, no paid accounts. Battle-tested on **1,400+ academic books** with a **99% success rate**.

## Features & Proven Methods

This agent achieves an extremely high success rate (99%+) for mass downloads by utilizing several robust fallback strategies:

1. **Live Mirror Probing** — Dynamically searches active Anna's Archive mirrors (`annas-archive.gl`, `.pk`, `.gd`, `.vg`) and LibGen mirrors (`libgen.la`, `.gl`, `.vg`, `.is`, `.rs`).

2. **Multi-Candidate MD5 Loop (up to 10)** — Instead of relying on a single result, it extracts the top 10 MD5 candidates and tries each until a working download link is found.

3. **Niche Author & Short Title Fallback** — If a full title search fails, it sanitizes the title (strips parentheticals, subtitles, editions) and searches using: `Author Last Name + 2-3 Niche Keywords`.

4. **Direct GET Link Extraction** — Bypasses ad pages by fetching `ads.php?md5={md5}` with a fake Referer, extracting the actual `get.php?md5=...&key=...` download token, and streaming the file directly to disk.

5. **Automatic Category Sorting** — Organizes downloaded files into clean directories: `downloads/<category>/<subcategory>/<Title> - <Author>.<ext>`

6. **DNS Bypass** — Optional. Resolves the exact LibGen hosts to an IP that you supply, to work around ISP-level DNS blocks. No IP is hardcoded.

## Quick Start

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/book-downloader-agent.git
cd book-downloader-agent

# Set up virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### CLI Commands

```bash
# Download all books from your queue
python -m bookdl download

# Download with parallel workers (4 concurrent category threads)
python -m bookdl download --parallel --workers 4

# Download specific categories only
python -m bookdl download --categories 01,02,03

# Retry all failed/missing books
python -m bookdl retry

# Extract books from markdown lists into a JSON queue
python -m bookdl extract --docs-dir ./my_book_lists/

# Sync download log with files actually on disk
python -m bookdl sync

# Check current download progress
python -m bookdl status
```

### Global Options

| Option | Description | Default |
|---|---|---|
| `--output-dir PATH` | Download directory | `./downloads` |
| `--queue-file PATH` | Books queue JSON file | `./books_queue.json` |
| `--log-file PATH` | Download log JSON file | `./download_log.json` |
| `--bypass-dns IP` | Resolve the LibGen hosts to this IP (supply an IP you trust) | Off |
| `--limit N` | Limit number of books to process | `0` (all) |
| `--categories IDS` | Comma-separated category IDs to filter | All |

### Input Format (`books_queue.json`)

Create a JSON file with an array of book objects. See [`examples/books_queue.example.json`](examples/books_queue.example.json) for a full example:

```json
[
  {
    "category_group": "01_psychology_fundamentals",
    "subcategory": "Cognitive Behavioral Therapy",
    "title": "Feeling Good: The New Mood Therapy",
    "author": "David D. Burns",
    "year": "1980",
    "search_query": "Feeling Good David Burns"
  }
]
```

| Field | Required | Description |
|---|---|---|
| `category_group` | ✅ | Top-level directory name for organizing downloads |
| `subcategory` | ✅ | Subdirectory name within the category |
| `title` | ✅ | Full book title |
| `author` | ✅ | Author name(s) |
| `year` | ❌ | Publication year |
| `search_query` | ❌ | Custom search query override |

### AI Agent Setup

If you're using an agentic AI framework (Claude Code, Gemini, AutoGPT, etc.), provide [`system_prompt.md`](system_prompt.md) as the agent's system instructions. The agent will automatically understand how to use the CLI to search and download books.

## Architecture

```
book-downloader-agent/
├── bookdl/                     # Core Python package
│   ├── cli.py                  # CLI entry point with subcommands
│   ├── config.py               # Mirror URLs, headers, DNS bypass
│   ├── search.py               # Anna's Archive + LibGen search
│   ├── download.py             # File download + batch processing
│   ├── extract.py              # Markdown → JSON queue parser
│   ├── sync.py                 # Disk-to-log reconciliation
│   └── utils.py                # Shared utilities
├── examples/
│   └── books_queue.example.json
├── system_prompt.md            # AI agent instructions
├── requirements.txt
├── LICENSE
└── README.md
```

## Anti-Blocking Features

If your ISP blocks the DNS of the LibGen domains, pass an IP that you trust to the `--bypass-dns` flag:

```bash
python -m bookdl download --bypass-dns 203.0.113.10
```

This monkey-patches Python's `socket.getaddrinfo` so that only the exact hosts in `LIBGEN_MIRRORS` and `LIBGEN_SEARCH_HOST` (in `bookdl/config.py`) resolve to that IP. No IP is hardcoded. TLS still verifies the certificate against the original hostname, so a wrong IP gives a certificate error, not a swapped file.

## Security

- All search and download requests use HTTPS. A download whose final URL is not HTTPS is rejected.
- Each file must match the MD5 hash that it was found under. A file with a different hash is deleted.
- The file type comes from the content (magic bytes), not from the link. Only PDF, EPUB, DjVu and MOBI/AZW are accepted.
- Downloads larger than `MAX_FILE_SIZE` (500 MB, in `bookdl/config.py`) are aborted.
- Existing files are never overwritten. A second copy gets the name `Title - Author (1).ext`.
- Files from shadow libraries are untrusted. Open them in a sandboxed reader with JavaScript turned off.

## License

MIT License — see [LICENSE](LICENSE) for details.

*Disclaimer: This tool is intended for research and archival purposes.*
