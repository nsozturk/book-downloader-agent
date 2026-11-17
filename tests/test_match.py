import unittest

from bookdl.match import Candidate, rank_candidates


def cand(md5, **kw):
    return Candidate(md5=md5, **kw)


def md5s(items):
    return [c.md5 for c in items]


class RankCandidatesTest(unittest.TestCase):
    def test_wrong_language_dropped(self):
        items = [cand('a', language='German'), cand('b', language='English')]
        self.assertEqual(md5s(rank_candidates(items, {'language': 'English'})), ['b'])

    def test_multi_language_field_matches(self):
        items = [cand('a', language='English; German'), cand('b', language='French, Spanish')]
        self.assertEqual(md5s(rank_candidates(items, {'language': 'english'})), ['a'])
        self.assertEqual(md5s(rank_candidates(items, {'language': 'GERMAN'})), ['a'])

    def test_unknown_language_dropped_when_language_wanted(self):
        items = [cand('a', language=''), cand('b', language='English')]
        self.assertEqual(md5s(rank_candidates(items, {'language': 'English'})), ['b'])
        self.assertEqual(md5s(rank_candidates(items, {})), ['a', 'b'])

    def test_edition_word_needs_edition_after_it(self):
        items = [cand('a', title='The Second World War'), cand('b', title='Physics, Second Edition')]
        self.assertEqual(md5s(rank_candidates(items, {'edition': '2'})), ['b', 'a'])

    def test_wrong_ext_dropped(self):
        items = [cand('a', ext='mobi'), cand('b', ext='EPUB'), cand('c', ext='')]
        self.assertEqual(md5s(rank_candidates(items, {'formats': ['epub', 'pdf']})), ['b', 'c'])

    def test_format_preference_order(self):
        items = [cand('a', ext='pdf'), cand('b', ext='epub')]
        self.assertEqual(md5s(rank_candidates(items, {'formats': ['epub', 'pdf']})), ['b', 'a'])

    def test_year_match_first_among_equal_formats(self):
        items = [cand('a', ext='pdf', year='2008'), cand('b', ext='pdf', year='2010;2012')]
        self.assertEqual(md5s(rank_candidates(items, {'formats': ['pdf'], 'year': '2012'})), ['b', 'a'])

    def test_format_beats_year(self):
        items = [cand('a', ext='pdf', year='2012'), cand('b', ext='epub', year='2008')]
        book = {'formats': ['epub', 'pdf'], 'year': '2012'}
        self.assertEqual(md5s(rank_candidates(items, book)), ['b', 'a'])

    def test_edition_matches(self):
        for title in ('Book, Sixth Edition', 'Book 6th ed.', 'Book 6e', 'Book 6th Edition', 'Book Edition 6'):
            items = [cand('a', title='Book'), cand('b', title=title)]
            self.assertEqual(md5s(rank_candidates(items, {'edition': '6'})), ['b', 'a'], title)

    def test_edition_does_not_match(self):
        for title in ('Book 16th edition', 'Book 2006', 'Book edition 16'):
            items = [cand('a', title='Other'), cand('b', title=title)]
            self.assertEqual(md5s(rank_candidates(items, {'edition': '6'})), ['a', 'b'], title)

    def test_no_optional_fields_keeps_order(self):
        items = [cand('c', ext='pdf'), cand('a', language='German'), cand('b')]
        self.assertEqual(md5s(rank_candidates(items, {'title': 'x', 'author': 'y'})), ['c', 'a', 'b'])

    def test_all_dropped_returns_empty(self):
        items = [cand('a', language='German'), cand('b', language='French')]
        self.assertEqual(rank_candidates(items, {'language': 'English'}), [])


if __name__ == '__main__':
    unittest.main()
