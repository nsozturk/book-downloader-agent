<div align="center">
  <img src="header.jpg" alt="Book Downloader Agent Header" width="100%">
</div>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&style=flat-square" alt="Python Version">
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License: MIT">
  <img src="https://img.shields.io/badge/Source-private user's library%20Archive-e74c3c?style=flat-square&logo=bookstack" alt="Source: private user's library Archive">
  <img src="https://img.shields.io/badge/Books%20Downloaded-1400%2B-blueviolet?style=flat-square" alt="Books Downloaded: 1400+">
  <img src="https://img.shields.io/badge/Success%20Rate-99%25-brightgreen?style=flat-square" alt="Success Rate: 99%">
</p>

# Book Downloader Agent

> 📚 An AI agent system that bulk-downloads books private User's collection.

## Features & Proven Methods

This agent achieves an extremely high success rate (99%+) for mass downloads by utilizing several robust fallback strategies:

1. Nothing cool.

2. **Multi-Candidate MD5 Loop (up to 10)** — Instead of relying on a single result, it extracts the top 10 MD5 candidates and tries each until a working download link is found.

3. **Niche Author & Short Title Fallback** — If a full title search fails, it sanitizes the title (strips parentheticals, subtitles, editions) and searches using: `Author Last Name + 2-3 Niche Keywords`.

4. **Direct GET Link Extraction** — Bypasses ad pages by fetching `ads.php?md5={md5}` with a fake Referer, extracting the actual `get.php?md5=...&key=...` download token, and streaming the file directly to disk.

5. **Quarantine Folder** — Saves every file as `~/.local/share/bookdl/quarantine/<Title> - <Author>.<ext>`, away from desktop indexers. `bookdl open` shows a book in a sandboxed reader.

6. **DNS Bypass** — Optional. Resolves the exact User_Library hosts to an IP that you supply, to work around ISP-level DNS blocks. No IP is hardcoded.

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

### In opencode

The Claude Code plugin does not load in opencode. The repo holds a separate subagent for it: `.opencode/agents/bookdl-runner.md`.

1. Put `bookdl` on your `PATH`: `ln -s "$PWD/bin/bookdl" ~/.local/bin/bookdl` (run it in the repo folder).
2. Start opencode in the repo folder, or copy the agent file to `~/.config/opencode/agents/` to have it in every project.
3. Ask for the books. The main agent passes the list to the subagent `bookdl-runner`.

The `permissions` list of the subagent replaces the Claude Code hook. It denies everything, then allows plain `bookdl ...` commands with relative paths and file access inside the project folder. A file path outside the project, such as the quarantine folder, is denied. The checks inside `bookdl` itself are the same in every agent.

## Usage

### CLI Commands

You give only a list of books. One `download` run finds the edition, downloads the file, runs the safety checks and moves each book that passes to `~/Books`. A book that fails a check stays in quarantine. You do not need a second command. `bookdl release` stays for files that are still in quarantine.

```bash
# Search, download, check and release: each book that passes goes to ~/Books
python -m bookdl download

# Download only. Keep every file in quarantine (skip the checks and the release)
python -m bookdl download --no-release

# Download with parallel workers (4 concurrent category threads)
python -m bookdl download --parallel --workers 4

# Download specific categories only
python -m bookdl download --categories 01,02,03

# Retry all failed books, with the same checks
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

# For files that are still in quarantine: list them, then check one and move it to ~/Books
python -m bookdl release
python -m bookdl release 3

# Check every book in quarantine and move the ones that pass
python -m bookdl release --all
```

### Global Options

| Option | Description | Default |
|---|---|---|
| `--output-dir PATH` | Download directory | `~/.local/share/bookdl/quarantine` |
| `--library-dir PATH` | Folder for books that pass the checks | `~/Books` |
| `--no-release` | `download` and `retry` only: keep every file in quarantine. A later `download` skips these books. Run `bookdl release --all` to check them | Off |
| `--queue-file PATH` | Books queue JSON file | `./books_queue.json` |
| `--log-file PATH` | Download log JSON file | `./download_log.json` |
| `--bypass-dns IP` | Resolve the User_Library hosts to this IP (supply an IP you trust) | Off |
| `--limit N` | Limit number of books to process | `0` (all) |
| `--categories IDS` | Comma-separated category IDs to filter | All |

### Input Format (`books_queue.json`)

Create a JSON file with an array of book objects. See [`examples/books_queue.example.json`](examples/books_queue.example.json) for a full example:

```json
[
  {
    "title": "Feeling Good: The New Mood Therapy",
    "author": "David D. Burns",
    "year": "1980",
    "language": "English",
    "formats": ["epub", "pdf"]
  }
]
```

| Field | Required | Description |
|---|---|---|
| `title` | ✅ | Full book title |
| `author` | ✅ | Author name(s) |
| `id` | ❌ | Stable unique string. If missing, `bookdl` makes one from title and author |
| `search_query` | ❌ | Custom search query override |
| `language` | ❌ | Language name in English, as the book mirror writes it, for example `"English"` |
| `formats` | ❌ | Ordered list of extensions without a dot, best first, for example `["epub", "pdf"]` |
| `year` | ❌ | Publication year. A result with this year ranks higher |
| `edition` | ❌ | Edition number, for example `"6"`. A result whose title names this edition ranks higher |
| `publisher` | ❌ | Publisher |

Edition matching is approximate: `"6"` matches title text such as "6th edition", "sixth edition", "edition 6" or "6e", and it can miss other spellings. A wrong language or a wrong format is never downloaded as a substitute. If you name a language, a search result with no language information is skipped too. If no result has the language and the format that you asked for, the book is reported as `NOT FOUND`.

### Report

`download` and `retry` print one line per processed book after the last book, then one line of counts:

```
IN LIBRARY: <title> -> <path>
IN QUARANTINE: <title>: <reasons joined with "; ">
NOT FOUND: <title>
FAILED: <title>
SUMMARY: library=<n> quarantine=<n> not_found=<n> failed=<n>
```

A book that is `IN LIBRARY` or `IN QUARANTINE` is done and is skipped by the next `download` and `retry`.

### AI Agent Setup

In Claude Code, install the plugin: the skill and the hook replace the system prompt. For another agentic AI framework (Gemini, AutoGPT, etc.), provide [`system_prompt.md`](system_prompt.md) as the agent's system instructions. The agent will automatically understand how to use the CLI to search and download books.

## Architecture

```
book-downloader-agent/
├── bookdl/                     # Core Python package
│   ├── cli.py                  # CLI entry point with subcommands
│   ├── config.py               # Mirror URLs, headers, DNS bypass
│   ├── net.py                  # HTTPS-only requests, block on local addresses
│   ├── search.py               # User_Library + private user's library Archive search, returns candidates
│   ├── match.py                # Ranks candidates by language, format, year, edition
│   ├── download.py             # File download + one pipeline per book (search, download, check, release)
│   ├── extract.py              # Markdown → JSON queue parser
│   ├── sync.py                 # Disk-to-log reconciliation
│   ├── viewer.py               # Opens a book in a bubblewrap sandbox
│   ├── release.py              # Checks quarantined books, moves passing ones to ~/Books
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

If your ISP blocks the DNS of the User_Library domains, pass an IP that you trust to the `--bypass-dns` flag:

```bash
python -m bookdl download --bypass-dns 203.0.113.10
```

This uses the patch of Python's `socket.getaddrinfo` in `bookdl/net.py`, so that only the exact hosts in `User_Library_MIRRORS` and `User_Library_SEARCH_HOST` (in `bookdl/config.py`) resolve to that IP. No IP is hardcoded. TLS still verifies the certificate against the original hostname, so a wrong IP gives a certificate error, not a swapped file.

## Security

The release checks run as part of every `bookdl download` and `bookdl retry`, unless you pass `--no-release`. A check that fails or ends with an error keeps the file in quarantine.

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
- The subagent `bookdl-runner` can run `bookdl download --parallel`, `bookdl retry` and the other plain `bookdl ...` commands. It can run only plain `bookdl ...` commands with relative paths, without `--output-dir` and without `--library-dir`, and can use files only inside the working directory.

Limits that you must know:

- The MD5 check proves that the file is the one that the library lists. It does not prove that the file is harmless. Open books only with `bookdl open`.
- The check of Bash commands is a text match. It stops an agent that follows an injected instruction in the obvious way. It is not a sandbox for Bash.
- If you pass `--output-dir`, the files are outside the quarantine folder and outside the hook.
- Do not browse the quarantine folder in a file manager with previews turned on. A thumbnailer parses the files without a sandbox.

### Release checks

`bookdl download` and `bookdl retry` check each downloaded book and move it to the library folder `~/Books` if it passes every check. The library folder is outside `~/.local/share/bookdl`, so the plugin hook does not block it. `bookdl release [target] [--all] [--library-dir PATH]` is the command for files that are still in quarantine, for example after `--no-release` or after a failed check. `target` is a list number or a part of the file name. Without `target` and without `--all`, the command prints the numbered list and exits with code 1.

The checks run in this order. A file that fails any check stays in the quarantine folder.

1. VirusTotal hash lookup, only if `VT_API_KEY` is set. Any engine that reports "malicious" or "suspicious" fails the book. A quota error or another API error also fails it (fail-closed). A hash that VirusTotal does not know gives a warning. Without the key, the command prints one warning line and continues.
2. Active-content check. A PDF is inspected with `qpdf --json`. An EPUB is inspected with the Python `zipfile` module. DjVu and MOBI files have no content check. Such a file passes only with a clean VirusTotal verdict. Without that verdict it stays in quarantine.

The policy is detect and refuse. The command never strips or rewrites a file, because `qpdf` has no option that removes JavaScript.

`download` and `retry` report the result in the [Report](#report) lines. `bookdl release` prints one line per book: `RELEASED: <name> -> <path>` or `KEPT IN QUARANTINE: <name>: <reason>`. Its exit code is 0 if every processed book was released, and 1 otherwise.

To turn on the VirusTotal lookup, make a free VirusTotal account and set the key:

```bash
export VT_API_KEY=your_key_here
```

Only the SHA-256 hash of the file is sent, never the file. VirusTotal sees which file you ask about.

Limits of the release check:

- A pass means "no engine on VirusTotal flags the file, and the common active-content patterns are absent". It does not mean "proven safe".
- A new exploit hidden in a font or an image passes every check.
- DjVu and MOBI files get no active-content check. They need a clean VirusTotal verdict, so without `VT_API_KEY` they stay in quarantine.
- A released book is still untrusted. An agent that has a shell must not follow instructions found inside it.
- The checks need `qpdf` and network access. If the Bash tool of an agent is sandboxed, run `! bookdl release --all` yourself for the files that stay in quarantine.

## License

MIT License — see [LICENSE](LICENSE) for details.

*Disclaimer: This tool is intended for research and archival purposes.*
