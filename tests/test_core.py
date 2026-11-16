import contextlib
import io
import json
import os
from unittest.mock import patch
import tempfile
import unittest
from pathlib import Path

from zed_leetcode import auth, runner, workspace
from zed_leetcode.cli import SITES, parser
from zed_leetcode.client import LeetCodeClient, extract_cases


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        workspace.init(self.root, 'https://leetcode.com')
        self.data = {'id': '1', 'slug': 'demo', 'title': 'Demo', 'difficulty': 'Easy', 'method': 'solve', 'params': ['x'], 'description': 'Demo', 'cases': [{'args': [None], 'expected': None}, {'args': [[True, [False]]], 'expected': [True, [False]]}]}
        self.path = workspace.create(self.root, self.data)
        self.meta = json.loads((self.path / 'metadata.json').read_text())

    def execute(self, source, timeout=2):
        (self.path / 'solution.py').write_text(source)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = runner.run(self.path, self.meta, timeout)
        return result, output.getvalue()

    def test_workspace_discovery_and_no_overwrite(self):
        self.assertEqual(workspace.root_from(self.path), self.root.resolve())
        self.assertEqual(workspace.resolve(self.root, '1')[0], self.path)
        with self.assertRaises(workspace.WorkspaceError):
            workspace.create(self.root, self.data)
        workspace.create(self.root, self.data, True)

    def test_pass_nested_json(self):
        ok, text = self.execute('class Solution:\n def solve(self, x): return x\n')
        self.assertTrue(ok)
        self.assertIn('2 passed', text)

    def test_fail_and_bool_type(self):
        ok, text = self.execute('class Solution:\n def solve(self, x): return 1\n')
        self.assertFalse(ok)
        self.assertIn('FAIL', text)
        self.assertFalse(runner.equal(True, 1))

    def test_timeout(self):
        ok, text = self.execute('class Solution:\n def solve(self, x):\n  while True: pass\n', .1)
        self.assertFalse(ok)
        self.assertIn('TIMEOUT', text)

    def test_exception_and_incomplete(self):
        (self.path / 'test_cases.json').write_text(json.dumps({'cases': [{'args': [1]}, {'args': [1], 'expected': 1}]}))
        ok, text = self.execute('class Solution:\n def solve(self, x): raise ValueError("oops")\n')
        self.assertFalse(ok)
        self.assertIn('INCOMPLETE', text)
        self.assertIn('ValueError', text)

    def test_extract_cases_and_template(self):
        self.assertEqual(extract_cases('输入：nums = [2,7], target = 9\n输出：[0,1]', ['nums', 'target']), [{'args': [[2, 7], 9], 'expected': [0, 1]}])
        self.assertEqual(extract_cases('输入：x = 1\n输出：unknown', ['x']), [])
        self.data['template'] = 'class Solution:\n    def solve(self, x):\n        '
        workspace.create(self.root, self.data, True)
        compile((self.path / 'solution.py').read_text(), 'solution.py', 'exec')

    def test_default_site_is_china(self):
        self.assertEqual(SITES[parser().parse_args(['init']).site], 'https://leetcode.cn')
        self.assertEqual(SITES[parser().parse_args(['init', '--site', 'global']).site], 'https://leetcode.com')

    def test_submit_requires_credentials_and_is_cn_only(self):
        from unittest.mock import MagicMock
        store = MagicMock()
        store.get_password.return_value = None
        with patch.dict(os.environ, {}, clear=True), patch('zed_leetcode.auth.backend', return_value=store):
            with self.assertRaisesRegex(workspace.WorkspaceError, 'Not logged in'):
                LeetCodeClient('https://leetcode.cn').submit('demo', 'code', '1')
        with self.assertRaisesRegex(workspace.WorkspaceError, 'only leetcode.cn'):
            LeetCodeClient('https://leetcode.com').submit('demo', 'code', '1')

    def test_submit_and_poll(self):
        import urllib.request
        from unittest.mock import MagicMock
        responses = [b'{"submission_id": 123}', b'{"state": "PENDING"}', b'{"state": "SUCCESS", "status_msg": "Accepted", "status_runtime": "2 ms", "status_memory": "10 MB"}']
        opener = MagicMock()
        def open_request(req, timeout):
            response = MagicMock()
            response.__enter__.return_value = io.BytesIO(responses.pop(0))
            return response
        opener.open.side_effect = open_request
        with patch.dict(os.environ, {'LEETCODE_SESSION': 'fake-secret', 'LEETCODE_CSRF_TOKEN': 'fake-token'}), patch.object(urllib.request, 'build_opener', return_value=opener), patch('zed_leetcode.client.time.sleep'):
            result = LeetCodeClient('https://leetcode.cn').submit('demo', 'class Solution: pass', '456')
        self.assertEqual(result['status'], 'Accepted')
        request = opener.open.call_args_list[0].args[0]
        self.assertEqual(json.loads(request.data)['question_id'], 456)
        self.assertEqual(json.loads(request.data)['lang'], 'python3')
        self.assertEqual(opener.open.call_count, 3)

    def test_credentials_environment_precedence(self):
        with patch.dict(os.environ, {'LEETCODE_SESSION': 'env-session', 'LEETCODE_CSRF_TOKEN': 'env-csrf'}, clear=True), patch('zed_leetcode.auth.backend') as backend:
            self.assertEqual(auth.get_credentials(), ('env-session', 'env-csrf'))
            backend.assert_not_called()
        with patch.dict(os.environ, {'LEETCODE_SESSION': 'only-one'}, clear=True):
            with self.assertRaises(workspace.WorkspaceError):
                auth.get_credentials()

    def test_keychain_save_load_logout(self):
        from unittest.mock import MagicMock
        store = MagicMock()
        store.get_password.return_value = json.dumps({'session': 'stored-session', 'csrf': 'stored-csrf'})
        with patch.dict(os.environ, {}, clear=True), patch('zed_leetcode.auth.backend', return_value=store):
            self.assertEqual(auth.get_credentials(), ('stored-session', 'stored-csrf'))
            auth.save_credentials('new-session', 'new-csrf')
            auth.logout()
        self.assertEqual(json.loads(store.set_password.call_args.args[2])['session'], 'new-session')
        store.delete_password.assert_called_once()

    def test_verify_unauthenticated_does_not_save(self):
        from unittest.mock import MagicMock
        opener = MagicMock()
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(b'{"data":{"userStatus":{"isSignedIn":false}}}')
        opener.open.return_value = response
        with patch('urllib.request.build_opener', return_value=opener):
            self.assertFalse(auth.verify('fake-session', 'fake-csrf'))

    def test_submit_http_error_does_not_leak_credentials(self):
        import urllib.error
        from unittest.mock import MagicMock
        opener = MagicMock()
        opener.open.side_effect = urllib.error.HTTPError('https://leetcode.cn', 403, 'secret-session', {}, None)
        with patch.dict(os.environ, {'LEETCODE_SESSION': 'secret-session', 'LEETCODE_CSRF_TOKEN': 'secret-csrf'}), patch('urllib.request.build_opener', return_value=opener):
            with self.assertRaises(workspace.WorkspaceError) as caught:
                LeetCodeClient('https://leetcode.cn').submit('demo', 'code', '1')
        self.assertIn('403', str(caught.exception))
        self.assertNotIn('secret-session', str(caught.exception))
        self.assertNotIn('secret-csrf', str(caught.exception))

    def test_reject_path_traversal(self):
        self.data['slug'] = '../bad'
        with self.assertRaises(workspace.WorkspaceError):
            workspace.create(self.root, self.data)


if __name__ == '__main__':
    unittest.main()
