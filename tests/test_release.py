import sys
import os
import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from bookdl import release
from bookdl.viewer import sandbox_command, tool_command


def make_pdf(path: Path, open_action: bytes) -> None:
    """
    Writes a tiny valid PDF whose catalog has the given /OpenAction object (object 4).
    """
    objs = [b"<< /Type /Catalog /Pages 2 0 R /OpenAction 4 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 10 10] >>",
            open_action]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path.write_bytes(out)


class PdfActiveContentTest(unittest.TestCase):
    def test_javascript_action(self):
        data = {'obj:4 0 R': {'value': {'/S': '/JavaScript', '/JS': 'u:x'}}}
        self.assertEqual(release.pdf_active_content(data), ['JavaScript'])

    def test_embedded_files(self):
        data = {'obj:1 0 R': {'value': {'/Names': {'/EmbeddedFiles': '5 0 R'}}}}
        self.assertEqual(release.pdf_active_content(data), ['EmbeddedFiles'])

    def test_launch_action(self):
        data = {'a': [{'/S': '/Launch'}]}
        self.assertEqual(release.pdf_active_content(data), ['Launch'])

    def test_goto_open_action_is_clean(self):
        data = {'obj:1 0 R': {'value': {'/OpenAction': ['3 0 R', '/Fit']}}}
        self.assertEqual(release.pdf_active_content(data), [])

    def test_goto_action_dict_is_clean(self):
        data = {'obj:4 0 R': {'value': {'/S': '/GoTo', '/D': ['3 0 R', '/Fit']}}}
        self.assertEqual(release.pdf_active_content(data), [])

    def test_uri_is_clean(self):
        data = {'obj:5 0 R': {'value': {'/S': '/URI', '/URI': 'u:https://example.com'}}}
        self.assertEqual(release.pdf_active_content(data), [])


@unittest.skipUnless(shutil.which('qpdf'), 'qpdf is not installed')
class RealQpdfTest(unittest.TestCase):
    def run_qpdf(self, open_action: bytes):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / 't.pdf'
            make_pdf(pdf, open_action)
            result = subprocess.run(['qpdf', '--json-output', '--json-stream-data=none', str(pdf)],
                                    capture_output=True, check=True)
        return json.loads(result.stdout)

    def test_javascript_found(self):
        data = self.run_qpdf(b"<< /S /JavaScript /JS (app.alert(1)) >>")
        self.assertEqual(release.pdf_active_content(data), ['JavaScript'])

    def test_goto_clean(self):
        data = self.run_qpdf(b"[3 0 R /Fit]")
        self.assertEqual(release.pdf_active_content(data), [])


def make_epub(path: Path, extra: dict) -> None:
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('mimetype', 'application/epub+zip')
        zf.writestr('OEBPS/ch1.xhtml', '<html><body><p>Hello</p></body></html>')
        for name, content in extra.items():
            zf.writestr(name, content)


class InspectEpubTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / 'b.epub'

    def test_clean(self):
        make_epub(self.path, {})
        self.assertEqual(release.inspect_epub(self.path), [])

    def test_script_in_xhtml(self):
        make_epub(self.path, {'OEBPS/ch2.xhtml': '<html><SCRIPT>alert(1)</SCRIPT></html>'})
        self.assertTrue(release.inspect_epub(self.path))

    def test_path_traversal(self):
        make_epub(self.path, {'../x': 'data'})
        self.assertTrue(release.inspect_epub(self.path))

    def test_exe_member(self):
        make_epub(self.path, {'OEBPS/run.exe': 'MZ'})
        self.assertTrue(release.inspect_epub(self.path))

    def test_broken_zip(self):
        self.path.write_bytes(b'not a zip')
        self.assertEqual(release.inspect_epub(self.path), ['cannot inspect EPUB'])


def fake_response(status: int, body=None, text=None):
    response = mock.Mock()
    response.status_code = status
    if text is not None:
        response.json.side_effect = ValueError('bad json')
    else:
        response.json.return_value = body
    return response


def stats(malicious=0, suspicious=0):
    return {'data': {'attributes': {'last_analysis_stats': {
        'malicious': malicious, 'suspicious': suspicious, 'harmless': 0, 'undetected': 60}}}}


class VirusTotalCheckTest(unittest.TestCase):
    def check(self, response):
        with mock.patch('bookdl.release.https_get', return_value=response) as get:
            result = release.virustotal_check('a' * 32, 'key')
        self.assertEqual(get.call_args.kwargs['headers'], {'x-apikey': 'key'})
        self.assertTrue(get.call_args.args[0].endswith('/files/' + 'a' * 32))
        return result

    def test_malicious(self):
        self.assertEqual(self.check(fake_response(200, stats(malicious=1))),
                         ('malicious', 'malicious=1 suspicious=0'))

    def test_suspicious(self):
        self.assertEqual(self.check(fake_response(200, stats(suspicious=2)))[0], 'malicious')

    def test_clean(self):
        self.assertEqual(self.check(fake_response(200, stats()))[0], 'clean')

    def test_unknown(self):
        self.assertEqual(self.check(fake_response(404, {}))[0], 'unknown')

    def test_quota(self):
        self.assertEqual(self.check(fake_response(429, {}))[0], 'error')

    def test_not_json(self):
        self.assertEqual(self.check(fake_response(200, text='<html>')), ('error', 'VirusTotal lookup failed'))

    def test_exception(self):
        with mock.patch('bookdl.release.https_get', side_effect=OSError('boom')):
            self.assertEqual(release.virustotal_check('a' * 32, 'key')[0], 'error')


class ReleaseBooksTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.quarantine = root / 'q'
        self.library = root / 'lib'
        self.quarantine.mkdir()
        sleep = mock.patch('bookdl.release.time.sleep')
        sleep.start()
        self.addCleanup(sleep.stop)

    def add(self, name):
        path = self.quarantine / name
        path.write_bytes(b'data')
        return path

    def test_passing_file_moves(self):
        self.add('a.pdf')
        with mock.patch('bookdl.release.check_book', return_value=[]):
            code = release.release_books(self.quarantine, self.library, 'a', False)
        self.assertEqual(code, 0)
        self.assertTrue((self.library / 'a.pdf').exists())
        self.assertFalse((self.quarantine / 'a.pdf').exists())

    def test_failing_file_stays(self):
        self.add('a.pdf')
        with mock.patch('bookdl.release.check_book', return_value=['PDF: JavaScript']):
            code = release.release_books(self.quarantine, self.library, '1', False)
        self.assertEqual(code, 1)
        self.assertTrue((self.quarantine / 'a.pdf').exists())
        self.assertFalse((self.library / 'a.pdf').exists())

    def test_all_mixed_exit_code(self):
        self.add('a.pdf')
        self.add('b.pdf')
        with mock.patch('bookdl.release.check_book', side_effect=[[], ['x']]):
            code = release.release_books(self.quarantine, self.library, '', True)
        self.assertEqual(code, 1)
        self.assertTrue((self.library / 'a.pdf').exists())
        self.assertTrue((self.quarantine / 'b.pdf').exists())

    def test_existing_library_file_not_overwritten(self):
        self.library.mkdir()
        (self.library / 'a.pdf').write_bytes(b'old')
        self.add('a.pdf')
        with mock.patch('bookdl.release.check_book', return_value=[]):
            release.release_books(self.quarantine, self.library, 'a', False)
        self.assertEqual((self.library / 'a.pdf').read_bytes(), b'old')
        self.assertEqual((self.library / 'a (1).pdf').read_bytes(), b'data')

    def test_no_target_lists_and_fails(self):
        self.add('a.pdf')
        self.assertEqual(release.release_books(self.quarantine, self.library, '', False), 1)
        self.assertTrue((self.quarantine / 'a.pdf').exists())

    def test_empty_quarantine(self):
        self.assertEqual(release.release_books(self.quarantine, self.library, '', False), 1)


class ToolCommandTest(unittest.TestCase):
    def test_tool_command_shape(self):
        book = Path('/tmp/some book.pdf')
        cmd = tool_command(book, ['qpdf', '--check', '/book/some book.pdf'], '/usr/bin/bwrap', ['/nonexistent-dir'])
        self.assertIn('--unshare-all', cmd)
        self.assertNotIn('wayland-0', ' '.join(cmd))
        self.assertNotIn('/nonexistent-dir', cmd)
        i = cmd.index('/book/some book.pdf')
        self.assertEqual(cmd[i - 2:i + 1], ['--ro-bind', str(book), '/book/some book.pdf'])
        self.assertEqual(cmd[-3:], ['qpdf', '--check', '/book/some book.pdf'])

    def test_sandbox_command_keeps_reader_args(self):
        cmd = sandbox_command(Path('/x/b.pdf'), 'okular', '/usr/bin/bwrap', Path('/run/user/1/wayland-0'))
        self.assertEqual(cmd[-2:], ['okular', '/book/b.pdf'])
        self.assertIn('--ro-bind', cmd)



class ReviewFixesTest(unittest.TestCase):
    def _epub(self, members):
        folder = tempfile.mkdtemp()
        path = Path(folder) / 'b.epub'
        with zipfile.ZipFile(path, 'w') as zf:
            for name, data in members.items():
                zf.writestr(name, data)
        return path

    def test_pdf_action_type_as_list_does_not_crash(self):
        data = {'qpdf': [{}, {'obj:1 0 R': {'value': {'/AA': {'/O': {'/S': ['/JavaScript'], '/JS': 'u:x'}}}}}]}
        self.assertEqual(release.pdf_active_content(data), ['JavaScript'])
        self.assertEqual(release.pdf_active_content({'/S': {'/x': 1}}), [])

    def test_epub_utf16_script(self):
        path = self._epub({'a.xhtml': '<html><script>x</script></html>'.encode('utf-16')})
        self.assertIn('active content in markup', release.inspect_epub(path))

    def test_epub_event_handler(self):
        path = self._epub({'a.xhtml': '<html><body onload="x()">t</body></html>'})
        self.assertIn('active content in markup', release.inspect_epub(path))

    def test_epub_entity_encoded_javascript_url(self):
        path = self._epub({'a.xhtml': '<a href="java&#115;cript:x">t</a>'})
        self.assertIn('active content in markup', release.inspect_epub(path))

    def test_epub_script_in_xml_and_no_extension(self):
        self.assertIn('active content in markup', release.inspect_epub(self._epub({'a.xml': '<script>x</script>'})))
        self.assertIn('active content in markup', release.inspect_epub(self._epub({'data': '<script>x</script>'})))

    def test_epub_prose_with_on_word_is_clean(self):
        path = self._epub({'a.xhtml': '<html><p>Later on = sign, and one = two.</p></html>', 'img.png': b'<script>'})
        self.assertEqual(release.inspect_epub(path), [])

    def test_internal_error_keeps_file(self):
        folder = Path(tempfile.mkdtemp())
        quarantine, library = folder / 'q', folder / 'lib'
        quarantine.mkdir()
        (quarantine / 'a.pdf').write_bytes(b'%PDF-1.4 x')
        with mock.patch.object(release, 'check_book', side_effect=TypeError('boom')):
            self.assertEqual(release.release_books(quarantine, library, '', True), 1)
        self.assertTrue((quarantine / 'a.pdf').exists())
        self.assertEqual(list(library.iterdir()), [])

    def test_move_leaves_no_partial_file(self):
        folder = Path(tempfile.mkdtemp())
        quarantine, library = folder / 'q', folder / 'lib'
        quarantine.mkdir(); library.mkdir()
        (quarantine / 'a.pdf').write_bytes(b'new')
        (library / 'a.pdf').write_bytes(b'old')
        destination = release.move_to_library(quarantine / 'a.pdf', library)
        self.assertEqual(destination.name, 'a (1).pdf')
        self.assertEqual((library / 'a.pdf').read_bytes(), b'old')
        self.assertEqual(sorted(x.name for x in library.iterdir()), ['a (1).pdf', 'a.pdf'])
        self.assertFalse((quarantine / 'a.pdf').exists())

    def test_cli_rejects_abbreviated_flags(self):
        result = subprocess.run([sys.executable, '-m', 'bookdl', 'release', '--all', '--lib', 'out'],
                                capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent,
                                env={**os.environ, 'XDG_DATA_HOME': tempfile.mkdtemp()})
        self.assertEqual(result.returncode, 2)
        self.assertIn('unrecognized arguments', result.stderr)


if __name__ == '__main__':
    unittest.main()
