<div align="center">
  <img src="header.jpg" alt="Book Downloader Agent Header" width="100%">
</div>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&style=flat-square" alt="Python Version">
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

5. **Quarantine Folder** — Saves every file as `~/.local/share/bookdl/quarantine/<Title> - <Author>.<ext>`, away from desktop indexers. `bookdl open` shows a book in a sandboxed reader.

6. **DNS Bypass** — Optional. Resolves the exact LibGen hosts to an IP that you supply, to work around ISP-level DNS blocks. No IP is hardcoded.

## Quick Start

### As a Claude Code plugin (recommended)

```bash
claude plugin marketplace add Michota/book-downloader-agent
claude plugin install book-downloader@book-downloader-agent
```

The plugin needs Python 3.10 or later. It gives you:

- the command `bookdl` in the Bash tool. The first run creates a private virtual environment and installs the dependencies from `requirements.lock` with hash verification.
- the skill `book-downloader` and the subagent `bookdl-runner`, which run the downloads.
- a hook that enforces the safety rules. See [Security](#security).

### Manual setup

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/book-downloader-agent.git
cd book-downloader-agent

# Set up virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install --require-hashes -r requirements.lock
```

In a manual setup, type `python -m bookdl` where this README says `bookdl`.

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

# List the downloaded books, then open one in a sandboxed reader
python -m bookdl open
python -m bookdl open 3
```

### Global Options

| Option | Description | Default |
|---|---|---|
| `--output-dir PATH` | Download directory | `~/.local/share/bookdl/quarantine` |
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

In Claude Code, install the plugin: the skill and the hook replace the system prompt. For another agentic AI framework (Gemini, AutoGPT, etc.), provide [`system_prompt.md`](system_prompt.md) as the agent's system instructions. The agent will automatically understand how to use the CLI to search and download books.

## Architecture

```
book-downloader-agent/
├── bookdl/                     # Core Python package
│   ├── cli.py                  # CLI entry point with subcommands
│   ├── config.py               # Mirror URLs, headers, DNS bypass
│   ├── net.py                  # HTTPS-only requests, block on local addresses
│   ├── search.py               # Anna's Archive + LibGen search
│   ├── download.py             # File download + batch processing
│   ├── extract.py              # Markdown → JSON queue parser
│   ├── sync.py                 # Disk-to-log reconciliation
│   ├── viewer.py               # Opens a book in a bubblewrap sandbox
│   └── utils.py                # Shared utilities
├── .claude-plugin/             # Plugin and marketplace manifests
├── bin/bookdl                  # Wrapper: private venv + hash-pinned install
├── hooks/                      # PreToolUse guard for Claude Code
├── skills/book-downloader/     # Skill for Claude Code
├── agents/bookdl-runner.md     # Restricted download subagent
├── examples/
│   └── books_queue.example.json
├── system_prompt.md            # AI agent instructions
├── requirements.txt
├── requirements.lock
├── LICENSE
└── README.md
```

## Anti-Blocking Features

If your ISP blocks the DNS of the LibGen domains, pass an IP that you trust to the `--bypass-dns` flag:

```bash
python -m bookdl download --bypass-dns 203.0.113.10
```

This uses the patch of Python's `socket.getaddrinfo` in `bookdl/net.py`, so that only the exact hosts in `LIBGEN_MIRRORS` and `LIBGEN_SEARCH_HOST` (in `bookdl/config.py`) resolve to that IP. No IP is hardcoded. TLS still verifies the certificate against the original hostname, so a wrong IP gives a certificate error, not a swapped file.

## Security

Checks in the downloader:

- All search and download requests use HTTPS. The downloader follows redirects itself and rejects a hop that is not HTTPS.
- A host that resolves to a loopback, private or link-local address is blocked at connect time. A mirror cannot make your computer call your router or a local service.
- Each file must match the MD5 hash that it was found under. A file with a different hash is deleted.
- The file type comes from the content (magic bytes at the start of the file), not from the link. Only PDF, EPUB, DjVu and MOBI/AZW are accepted.
- Downloads larger than `MAX_FILE_SIZE` (500 MB, in `bookdl/config.py`) are aborted.
- Existing files are never overwritten. A second copy gets the name `Title - Author (1).ext`.
- The downloader prints no text that a server controls. An AI agent reads the output, so raw server text is a prompt injection channel.
- `requirements.lock` pins every dependency with hashes.

Handling of the downloaded files:

- Files go to the quarantine folder `~/.local/share/bookdl/quarantine` (mode `0700`). The folder is outside the folders that desktop indexers scan by default, and it holds `.trackerignore` and `.nomedia` markers.
- `bookdl open` starts the reader (`okular`, `zathura`, `evince`, `papers` or `mupdf`, or the one in `BOOKDL_READER`) inside a [bubblewrap](https://github.com/containers/bubblewrap) sandbox: no network, read-only system, empty home folder, one read-only book. It needs a Wayland session and refuses to open a book without the sandbox.

Rules that the plugin hook (`hooks/guard.py`) enforces in Claude Code:

- No agent can read, search or change the bookdl data folder with the file tools. A Bash command that names the folder is denied, unless it is a plain `bookdl ...` command.
- The subagent `bookdl-runner` can run only plain `bookdl ...` commands with relative paths, and can use files only inside the working directory.

Limits that you must know:

- The MD5 check proves that the file is the one that the library lists. It does not prove that the file is harmless. Open books only with `bookdl open`.
- The check of Bash commands is a text match. It stops an agent that follows an injected instruction in the obvious way. It is not a sandbox for Bash.
- If you pass `--output-dir`, the files are outside the quarantine folder and outside the hook.
- Do not browse the quarantine folder in a file manager with previews turned on. A thumbnailer parses the files without a sandbox.

## License

MIT License — see [LICENSE](LICENSE) for details.

*Disclaimer: This tool is intended for research and archival purposes.*
