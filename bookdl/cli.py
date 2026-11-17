import argparse
import sys
from pathlib import Path
from bookdl import config
from bookdl.download import download_batch, download_parallel
from bookdl.extract import extract_books
from bookdl.sync import sync_log_from_disk
from bookdl.utils import load_json

def main():
    parser = argparse.ArgumentParser(description="bookdl - Shadow Library Book Downloader Agent")
    parser.add_argument('command', choices=['download', 'retry', 'extract', 'sync', 'status'], help="Command to run")
    
    parser.add_argument('--output-dir', type=Path, default=Path(config.DEFAULT_OUTPUT_DIR), help="Download directory")
    parser.add_argument('--queue-file', type=Path, default=Path(config.DEFAULT_QUEUE_FILE), help="Books queue JSON")
    parser.add_argument('--log-file', type=Path, default=Path(config.DEFAULT_LOG_FILE), help="Download log JSON")
    parser.add_argument('--bypass-dns', metavar='IP', type=str, default='', help="Resolve the LibGen hosts to this IP (supply an IP you trust)")
    
    parser.add_argument('--limit', type=int, default=0, help="Limit number of books (0=all)")
    parser.add_argument('--categories', type=str, default='', help="Comma-separated category IDs")
    parser.add_argument('--parallel', action='store_true', help="Use parallel category workers")
    parser.add_argument('--workers', type=int, default=4, help="Number of parallel workers")
    
    parser.add_argument('--docs-dir', type=Path, help="Directory containing markdown book lists")
    
    args = parser.parse_args()
    
    if args.bypass_dns:
        config.enable_dns_bypass(args.bypass_dns, config.LIBGEN_MIRRORS + [config.LIBGEN_SEARCH_HOST])
        
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
                queue = [b for b in queue if log_data.get(b.get('id', ''), {}).get('status') != 'SUCCESS']
                
            if args.parallel:
                download_parallel(queue, args.output_dir, args.log_file, args.categories, args.workers)
            else:
                download_batch(queue, args.output_dir, args.queue_file, args.log_file, args.limit, args.categories)
                
        elif args.command == 'sync':
            stats = sync_log_from_disk(args.output_dir, args.queue_file, args.log_file)
            print("Sync complete. Stats:")
            for k, v in stats.items():
                print(f"  {k}: {v}")
                
        elif args.command == 'status':
            stats = sync_log_from_disk(args.output_dir, args.queue_file, args.log_file)
            print("Current Status:")
            for k, v in stats.items():
                print(f"  {k}: {v}")
                
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)

if __name__ == "__main__":
    main()
