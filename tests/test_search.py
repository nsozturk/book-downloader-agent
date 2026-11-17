import os
import unittest
from unittest import mock

import requests

from bookdl import search

REAL_PAGE = ('/tmp/claude-1000/-mnt-my-data-repos-book-downloader-agent/'
             'cc29c286-3729-4854-97f7-a2a790343fe8/scratchpad/libgen-search-sample.html')

M1, M2, M3, M4 = ('1' * 32, '2' * 32, '3' * 32, 'a' * 32)


def row(md5, title, author, year, lang, ext):
    return (f'<tr><td><a href="edition.php?id=1" title="tip">{title} <i>Reprint</i></a><br>'
            f'<a href="edition.php?id=1"><i><font color="green"> 0767920821; 9780767920827</font></i></a>'
            f'<span class="badge">l 1</span></td>'
            f'<td><a href="author.php?id=2">{author} (Author)</a></td><td>Pub</td><td><nobr>{year}</nobr></td>'
            f'<td>{lang}</td><td>10</td><td><nobr><a href="/file.php?id=1">2 MB</a></nobr></td><td>{ext}</td>'
            f'<td><a href="/ads.php?md5={md5}">1</a> <a href="https://x.org/md5={M4}">2</a></td></tr>')


def page(*rows):
    head = '<table id="tablelibgen"><thead><tr><th>Title</th><th>Author(s)</th></tr></thead><tbody>'
    return head + ''.join(rows) + '</tbody></table>'


def resp(text, status=200):
    r = mock.Mock()
    r.status_code = status
    r.text = text
    return r


FIXTURE = page(
    row(M1, 'Feeling   Good', 'Burns, David', '2008', 'English', 'epub'),
    '<tr><td>no md5</td><td>a</td><td>b</td><td>c</td><td>d</td><td>e</td><td>f</td><td>pdf</td><td>none</td></tr>',
    '<tr><td>short</td><td>a</td><td>b</td><td>c</td><td>d</td></tr>',
    row(M2, 'Second', 'Author Two', '2010', 'German', 'pdf'),
    row(M2, 'Second again', 'Author Two', '2010', 'German', 'pdf'),
    row(M3, 'Third', 'Author Three', '2012', 'English; French', 'mobi'),
)


class SearchCandidatesTest(unittest.TestCase):
    def test_parses_rows_and_skips_bad_ones(self):
        with mock.patch('bookdl.search.https_get', return_value=resp(FIXTURE)):
            result = search.search_candidates('q', '')
        self.assertEqual([c.md5 for c in result], [M1, M2, M3])
        first = result[0]
        self.assertEqual((first.title, first.author, first.publisher, first.year, first.language, first.ext),
                         ('Feeling Good Reprint', 'Burns, David (Author)', 'Pub', '2008', 'English', 'epub'))
        self.assertEqual(result[1].title, 'Second Reprint')
        self.assertEqual(result[2].language, 'English; French')

    def test_anna_fallback_adds_md5_only(self):
        anna = resp(f'<a href="/md5/{M4}">x</a> <a href="/md5/{M1.upper()}">y</a>')
        with mock.patch('bookdl.search.https_get', side_effect=[resp(FIXTURE), anna]):
            result = search.search_candidates('q', 'anna.example')
        self.assertEqual([c.md5 for c in result], [M1, M2, M3, M4])
        self.assertEqual(result[3].title, '')
        self.assertEqual(result[3].ext, '')

    def test_max_candidates(self):
        with mock.patch('bookdl.search.https_get', return_value=resp(FIXTURE)) as get:
            result = search.search_candidates('q', 'anna.example', max_candidates=2)
        self.assertEqual(len(result), 2)
        self.assertEqual(get.call_count, 1)

    def test_network_error_does_not_raise(self):
        with mock.patch('bookdl.search.https_get', side_effect=requests.RequestException('boom')):
            self.assertEqual(search.search_candidates('q', 'anna.example'), [])

    def test_network_error_keeps_first_result(self):
        side = [resp(FIXTURE), requests.RequestException('boom')]
        with mock.patch('bookdl.search.https_get', side_effect=side):
            self.assertEqual(len(search.search_candidates('q', 'anna.example')), 3)

    def test_broken_html_does_not_crash(self):
        with mock.patch('bookdl.search.https_get', return_value=resp('<table><tr><td><a href="x<td></tr><<>')):
            self.assertEqual(search.search_candidates('q', ''), [])

    def test_fields_are_cut(self):
        long_row = row(M1, 'T' * 1000, 'A', '2000', 'English', 'pdf')
        with mock.patch('bookdl.search.https_get', return_value=resp(page(long_row))):
            self.assertEqual(len(search.search_candidates('q', '')[0].title), 300)

    def test_search_md5_candidates_returns_strings(self):
        with mock.patch('bookdl.search.https_get', return_value=resp(FIXTURE)):
            self.assertEqual(search.search_md5_candidates('q', ''), [M1, M2, M3])


@unittest.skipUnless(os.path.exists(REAL_PAGE), 'saved real page not available')
class RealPageTest(unittest.TestCase):
    def test_real_page(self):
        with open(REAL_PAGE, encoding='utf-8') as f:
            text = f.read()
        with mock.patch('bookdl.search.https_get', return_value=resp(text)):
            result = search.search_candidates('q', '', max_candidates=100)
        self.assertGreaterEqual(len(result), 10)
        for c in result:
            self.assertRegex(c.md5, r'^[0-9a-f]{32}$')
        self.assertTrue(any(c.language and c.ext for c in result))


if __name__ == '__main__':
    unittest.main()
