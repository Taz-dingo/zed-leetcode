import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from zed_leetcode import cli, workspace

SOURCE = Path(__file__).resolve().parents[1] / 'src'


class WorkspaceCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / 'home'
        self.repo = self.base / 'repo'
        self.home.mkdir()
        self.repo.mkdir()
        self.env = {**os.environ, 'HOME': str(self.home), 'PYTHONPATH': str(SOURCE)}
        self.env.pop('LEETCODE_SESSION', None)
        self.env.pop('LEETCODE_CSRF_TOKEN', None)
        self.managed = self.home / '.local/share/zed-leetcode/workspace'

    def lc(self, *args):
        return subprocess.run([sys.executable, '-m', 'zed_leetcode.cli', *args], cwd=self.repo, env=self.env, capture_output=True, text=True, timeout=15)

    def test_auto_workspace_never_writes_in_current_repo(self):
        (self.repo / 'README.md').write_text('user repo')
        result = self.lc('list')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.managed / '.leetcode/config.toml').is_file())
        self.assertEqual(sorted(p.name for p in self.repo.iterdir()), ['README.md'])
        result = self.lc('status')
        self.assertIn('Active: none', result.stdout)
        self.assertIn(str(self.managed), result.stdout)

    def test_legacy_workspace_not_implicitly_selected(self):
        workspace.init(self.repo, 'https://leetcode.com')
        result = self.lc('status')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.managed), result.stdout)
        self.assertNotIn(str(self.repo) + '\n', result.stdout)
        result = self.lc('--workspace', str(self.repo), 'status')
        self.assertIn(f'Workspace: {self.repo}', result.stdout)

    def test_explicit_workspace_requires_initialization(self):
        path = self.base / 'custom'
        result = self.lc('--workspace', str(path), 'list')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(path.exists())
        self.assertEqual(self.lc('--workspace', str(path), 'init').returncode, 0)
        self.assertTrue((path / '.leetcode/config.toml').is_file())
        self.assertFalse(self.managed.exists())

    def test_import_test_and_use_from_unrelated_directory(self):
        data = {'id': '1', 'slug': 'sample', 'title': 'Sample', 'difficulty': 'Easy', 'method': 'solve', 'params': ['x'], 'template': 'class Solution:\n    def solve(self, x): return x\n', 'cases': [{'args': [True], 'expected': True}]}
        source = self.base / 'input.json'
        source.write_text(json.dumps(data))
        result = self.lc('fetch', '--import-file', str(source))
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.lc('test')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('1 passed', result.stdout)
        self.assertEqual(self.lc('use', '1').returncode, 0)
        self.assertEqual(list(self.repo.iterdir()), [])

    def test_init_does_not_reset_existing_workspace(self):
        self.assertEqual(self.lc('init').returncode, 0)
        config = self.managed / '.leetcode/config.toml'
        config.write_text('site = "https://leetcode.cn"\nactive = "existing"\nproblems_dir = "problems"\n')
        result = self.lc('init', '--site', 'global')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('active = "existing"', config.read_text())

    def test_open_passes_paths_without_shell(self):
        workspace.init(self.repo, 'https://leetcode.cn')
        path = workspace.create(self.repo, {'id': '1', 'slug': 'sample', 'title': 'Sample', 'difficulty': 'Easy', 'method': 'solve', 'params': []})
        with patch.object(sys, 'argv', ['lc', '--workspace', str(self.repo), 'open']), patch('zed_leetcode.cli.subprocess.run') as run:
            self.assertEqual(cli.main(), 0)
        run.assert_called_once_with(['zed', str(self.repo), str(path / 'problem.md'), str(path / 'solution.py')], check=True)


if __name__ == '__main__':
    unittest.main()
