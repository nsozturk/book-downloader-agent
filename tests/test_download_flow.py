import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

# bookdl.match and search_candidates are written by another change. Stub them only when they do not exist yet.
try:
    import bookdl.match  # noqa: F401
except ImportError:
    _stub = types.ModuleType('bookdl.match')
    _stub.rank_candidates = lambda candidates, book: candidates
    sys.modules['bookdl.match'] = _stub
import bookdl.search
if not hasattr(bookdl.search, 'search_candidates'):
    bookdl.search.search_candidates = lambda query, anna_mirror, max_candidates=10: []

from bookdl import download
from bookdl.download import process_book, download_batch, report_lines
from bookdl.utils import book_id, load_json

BOOK = {'title': 'Test Book', 'author': 'Jane Doe'}


class Cand:
    def __init__(self, md5):
        self.md5 = md5


def md5_of(n):
    return f"{n:032x}"


class FlowTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.quarantine = self.root / 'quarantine'
        self.library = self.root / 'library'
        self.quarantine.mkdir()
        self.downloaded = []
        self.exts = ['epub']

        def fake_download(url, referer, md5, output_dir, base_name):
            ext = self.exts[len(self.downloaded)] if len(self.downloaded) < len(self.exts) else self.exts[-1]
            if ext is None:
                self.downloaded.append(None)
                return None
            path = Path(output_dir) / f"{base_name}.{ext}"
            path.write_bytes(b'data' + md5.encode())
            self.downloaded.append(path)
            return path

        patches = {
            'search_candidates': mock.patch('bookdl.download.search_candidates', create=True, return_value=[Cand(md5_of(1)), Cand(md5_of(2))]),
            'rank_candidates': mock.patch('bookdl.download.rank_candidates', create=True, side_effect=lambda c, b: list(c)),
            'url': mock.patch('bookdl.download.get_direct_download_url', return_value=('https://x/y', 'https://x')),
            'download_file': mock.patch('bookdl.download.download_file', side_effect=fake_download),
            'check_book': mock.patch('bookdl.download.release.check_book', return_value=[]),
            'mirror': mock.patch('bookdl.download.get_working_mirror', return_value='anna.test'),
        }
        self.m = {}
        for name, p in patches.items():
            self.m[name] = p.start()
            self.addCleanup(p.stop)

    def run_book(self, book=BOOK, library=True):
        out = io.StringIO()
        with redirect_stdout(out):
            return process_book(book, 'anna.test', self.quarantine, self.library if library else None)

    def test_pass_is_released(self):
        entry = self.run_book()
        self.assertEqual(entry['status'], 'RELEASED')
        self.assertTrue(Path(entry['file']).exists())
        self.assertEqual(Path(entry['file']).parent, self.library)
        self.assertEqual(list(self.quarantine.glob('*.epub')), [])

    def test_reasons_are_quarantined(self):
        self.m['check_book'].return_value = ['PDF: JavaScript']
        entry = self.run_book()
        self.assertEqual(entry['status'], 'QUARANTINED')
        self.assertEqual(entry['reasons'], ['PDF: JavaScript'])
        self.assertTrue(Path(entry['file']).exists())
        self.assertEqual(Path(entry['file']).parent, self.quarantine)
        self.assertFalse(self.library.exists() and list(self.library.iterdir()))

    def test_no_ranked_candidates_is_not_found(self):
        self.m['rank_candidates'].side_effect = lambda c, b: []
        self.assertEqual(self.run_book(), {'status': 'NOT_FOUND'})
        self.m['download_file'].assert_not_called()

    def test_download_none_is_failed(self):
        self.exts = [None]
        self.assertEqual(self.run_book(), {'status': 'FAILED'})
        self.assertGreaterEqual(self.m['download_file'].call_count, 1)

    def test_wrong_format_deleted_and_next_candidate_used(self):
        self.exts = ['pdf', 'epub']
        entry = self.run_book(dict(BOOK, formats=['epub']))
        self.assertEqual(entry['status'], 'RELEASED')
        self.assertFalse(self.downloaded[0].exists())
        self.assertTrue(entry['file'].endswith('.epub'))
        self.assertEqual(self.m['download_file'].call_args_list[1].args[2], md5_of(2))

    def test_check_raises_is_quarantined(self):
        self.m['check_book'].side_effect = RuntimeError('boom')
        entry = self.run_book()
        self.assertEqual(entry['status'], 'QUARANTINED')
        self.assertEqual(entry['reasons'], ['check failed with an internal error'])
        self.assertTrue(Path(entry['file']).exists())
        self.assertEqual(Path(entry['file']).parent, self.quarantine)
        self.assertFalse(self.library.exists() and list(self.library.iterdir()))

    def test_move_raises_is_quarantined(self):
        with mock.patch('bookdl.download.release.move_to_library', side_effect=OSError('x')):
            entry = self.run_book()
        self.assertEqual(entry['status'], 'QUARANTINED')
        self.assertTrue(Path(entry['file']).exists())

    def test_no_release_skips_check(self):
        entry = self.run_book(library=False)
        self.assertEqual(entry['status'], 'QUARANTINED')
        self.assertEqual(entry['reasons'], ['release skipped'])
        self.m['check_book'].assert_not_called()

    def test_book_id_stable(self):
        a = book_id({'title': 'T', 'author': 'A'})
        self.assertEqual(a, book_id({'title': 'T', 'author': 'A'}))
        self.assertEqual(a, book_id({'title': 'T', 'author': 'A', 'language': 'English', 'formats': ['epub']}))
        self.assertEqual(len(a), 16)
        self.assertEqual(book_id({'id': 7, 'title': 'T', 'author': 'A'}), '7')
        self.assertEqual(book_id({'id': '', 'title': 'T', 'author': 'A'}), a)

    def test_second_batch_skips_released(self):
        log_file = self.root / 'log.json'
        with redirect_stdout(io.StringIO()):
            download_batch([BOOK], self.quarantine, self.root / 'q.json', log_file, library_dir=self.library)
        self.assertEqual(load_json(log_file)[book_id(BOOK)]['status'], 'RELEASED')
        calls = self.m['search_candidates'].call_count
        out = io.StringIO()
        with redirect_stdout(out):
            download_batch([BOOK], self.quarantine, self.root / 'q.json', log_file, library_dir=self.library)
        self.assertEqual(self.m['search_candidates'].call_count, calls)
        self.assertIn('SUMMARY: library=0 quarantine=0 not_found=0 failed=0', out.getvalue())

    def test_report_format(self):
        results = [
            ({'title': 'A'}, {'status': 'RELEASED', 'file': '/lib/A.epub'}),
            ({'title': 'B'}, {'status': 'QUARANTINED', 'file': '/q/B.pdf', 'reasons': ['r1', 'r2']}),
            ({'title': 'C'}, {'status': 'NOT_FOUND'}),
            ({'title': 'D\x1b[31m'}, {'status': 'FAILED'}),
        ]
        self.assertEqual(report_lines(results), [
            'IN LIBRARY: A -> /lib/A.epub',
            'IN QUARANTINE: B: r1; r2',
            'NOT FOUND: C',
            'FAILED: D [31m',
            'SUMMARY: library=1 quarantine=1 not_found=1 failed=1',
        ])


if __name__ == '__main__':
    unittest.main()
