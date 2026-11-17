import argparse
import sys
from pathlib import Path
from bookdl import config
from bookdl.net import install_network_guard
from bookdl.download import download_batch, download_parallel, is_done
from bookdl.extract import extract_books
from bookdl.sync import sync_log_from_disk
from bookdl.utils import load_json
from bookdl.release import release_books
from bookdl.viewer import find_book, open_sandboxed

def main():
    parser = argparse.ArgumentParser(description="bookdl - Book Downloader Agent", allow_abbrev=False)
    parser.add_argument('command', choices=['download', 'retry', 'extract', 'sync', 'status', 'open', 'release'], help="Command to run")
    parser.add_argument('target', nargs='?', default='', help="For `open` and `release`: the list number or a part of the file name")
    
    parser.add_argument('--output-dir', type=Path, default=None, help="Download directory (default: the quarantine folder)")
    parser.add_argument('--queue-file', type=Path, default=Path(config.DEFAULT_QUEUE_FILE), help="Books queue JSON")
    parser.add_argument('--log-file', type=Path, default=Path(config.DEFAULT_LOG_FILE), help="Download log JSON")
    parser.add_argument('--bypass-dns', metavar='IP', type=str, default='', help="Resolve the LibGen hosts to this IP (supply an IP you trust)")
    
    parser.add_argument('--limit', type=int, default=0, help="Limit number of books (0=all)")
    parser.add_argument('--categories', type=str, default='', help="Comma-separated category IDs")
    parser.add_argument('--parallel', action='store_true', help="Use parallel category workers")
    parser.add_argument('--workers', type=int, default=4, help="Number of parallel workers")
    
    parser.add_argument('--all', action='store_true', help="For `release`: check and release every book")
    parser.add_argument('--library-dir', type=Path, default=None, help="Library folder for books that pass the checks (default: ~/Books)")
    parser.add_argument('--no-release', action='store_true', help="For `download` and `retry`: keep every book in quarantine, skip the checks")

    parser.add_argument('--docs-dir', type=Path, help="Directory containing markdown book lists")
    
    args = parser.parse_args()
    
    try:
        install_network_guard(args.bypass_dns, config.LIBGEN_MIRRORS + [config.LIBGEN_SEARCH_HOST])
    except ValueError:
        print("Error: --bypass-dns needs a valid IP address")
        sys.exit(1)

    if args.output_dir is None:
        args.output_dir = config.default_output_dir()
        config.prepare_quarantine(args.output_dir)

    try:
        if args.command == 'extract':
            if not args.docs_dir:
                print("Error: --docs-dir is required for extract command")
                sys.exit(1)
            count = extract_books(args.docs_dir, args.queue_file)
            print(f"Extracted {count} books to {args.queue_file}")
            
        elif args.command in ('download', 'retry'):
            args.output_dir.mkdir(parents=True, exist_ok=True)
            
            queue = load_json(args.queue_file, default=[])
            if not queue:
                print(f"Queue file {args.queue_file} is empty or missing.")
                sys.exit(1)
                
            if args.command == 'retry':
                log_data = load_json(args.log_file, default={})
                queue = [b for b in queue if not is_done(log_data, b)]

            library_dir = None if args.no_release else (args.library_dir or config.default_library_dir())
            if args.parallel:
                download_parallel(queue, args.output_dir, args.log_file, args.categories, args.workers, library_dir)
            else:
                download_batch(queue, args.output_dir, args.queue_file, args.log_file, args.limit, args.categories, library_dir)
                
        elif args.command == 'open':
            book = find_book(args.output_dir, args.target)
            sys.exit(open_sandboxed(book) if book else 1)

        elif args.command == 'release':
            library_dir = args.library_dir or config.default_library_dir()
            sys.exit(release_books(args.output_dir, library_dir, args.target, args.all))

        elif args.command == 'sync':
            stats = sync_log_from_disk(args.output_dir, args.queue_file, args.log_file, args.library_dir or config.default_library_dir())
            print("Sync complete. Stats:")
            for k, v in stats.items():
                print(f"  {k}: {v}")
                
        elif args.command == 'status':
            stats = sync_log_from_disk(args.output_dir, args.queue_file, args.log_file, args.library_dir or config.default_library_dir())
            print("Current Status:")
            for k, v in stats.items():
                print(f"  {k}: {v}")
                
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)

if __name__ == "__main__":
    main()
