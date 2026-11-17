"""Command line interface."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import auth, runner, workspace
from .client import LeetCodeClient

SITES = {'global': 'https://leetcode.com', 'cn': 'https://leetcode.cn'}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='lc', description='A small local LeetCode workspace CLI')
    p.add_argument('--workspace', type=Path, help='explicit workspace path (default: managed user workspace)')
    sub = p.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init', help='initialize the managed or explicitly selected workspace')
    init.add_argument('--site', choices=SITES, default='cn', help='site (default: cn)')
    search = sub.add_parser('search', help='search online (first 50 results)')
    search.add_argument('keyword', nargs='?', default='')
    search.add_argument('--difficulty', choices=('easy', 'medium', 'hard'))
    fetch = sub.add_parser('fetch', help='fetch or import a problem')
    fetch.add_argument('identifier', nargs='?')
    fetch.add_argument('--import-file', type=Path, help='import a manually prepared JSON file')
    fetch.add_argument('--force', action='store_true', help='overwrite existing problem files')
    for name in ('use', 'test', 'submit', 'open'):
        command = sub.add_parser(name)
        command.add_argument('identifier', nargs=None if name == 'use' else '?')
        if name == 'test':
            command.add_argument('--timeout', type=float, default=3.0, help='seconds per case (default: 3)')
    sub.add_parser('login', help='sign in using an isolated browser and macOS Keychain')
    sub.add_parser('logout', help='remove the stored China-site login')
    sub.add_parser('list', help='list local problems')
    sub.add_parser('status', help='show active problem')
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == 'login':
            auth.login()
            return 0
        if args.command == 'logout':
            auth.logout()
            print('Removed stored login. Environment variables, if set, still take precedence.')
            return 0
        if args.command == 'init':
            root = (args.workspace or workspace.default_root()).expanduser().resolve()
            if (root / '.leetcode/config.toml').exists():
                print(f'Workspace already initialized: {root}')
                return 0
            root.mkdir(parents=True, exist_ok=True)
            workspace.init(root, SITES[args.site])
            print(f'Initialized workspace: {root}')
            return 0
        root = workspace.get_root(args.workspace)
        config = workspace.read_config(root)
        site = config.get('site')
        if site not in SITES.values():
            raise workspace.WorkspaceError('Invalid site in workspace config.')
        client = LeetCodeClient(site)
        if args.command == 'search':
            items = client.search(args.keyword, args.difficulty)
            for item in items:
                print(f"{item['questionFrontendId']}  {item.get('translatedTitle') or item['title']}  {item['difficulty']}  {item['titleSlug']}{' [premium]' if item.get('paidOnly') else ''}")
            print(f'{len(items)} result(s); showing at most 50.')
        elif args.command == 'fetch':
            if bool(args.identifier) == bool(args.import_file):
                raise workspace.WorkspaceError('Provide either a problem identifier or --import-file, not both.')
            if args.import_file:
                data = json.loads(args.import_file.read_text(encoding='utf-8'))
                if not isinstance(data, dict):
                    raise workspace.WorkspaceError('Import JSON must be an object.')
                print(f'Created {workspace.create(root, data, args.force)}')
            else:
                data = client.fetch(args.identifier)
                print(f'Created {workspace.create(root, data, args.force)}')
                if not data['cases']:
                    print('No reliable examples extracted; add cases to test_cases.json.')
                else:
                    print(f"Extracted {len(data['cases'])} example(s); review test_cases.json before running.")
        elif args.command == 'list':
            items = workspace.problems(root)
            for _, m in items:
                marker = '*' if m.get('slug') == config.get('active') else ' '
                print(f"{marker} {m['id']}  {m['title']}  {m['difficulty']}  {m['slug']}")
            if not items:
                print('No local problems.')
        elif args.command == 'status':
            print(f'Workspace: {root}')
            if config.get('active'):
                path, metadata = workspace.resolve(root, None)
                print(f"Active: {metadata['id']} {metadata['title']} ({path})")
            else:
                print('Active: none')
        else:
            path, metadata = workspace.resolve(root, getattr(args, 'identifier', None))
            if args.command == 'open':
                try:
                    subprocess.run(['zed', str(root), str(path / 'problem.md'), str(path / 'solution.py')], check=True)
                except FileNotFoundError:
                    raise workspace.WorkspaceError('Zed CLI not found. Install the zed command or open the workspace manually.') from None
                except subprocess.CalledProcessError:
                    raise workspace.WorkspaceError('Zed could not open the workspace.') from None
            elif args.command == 'use':
                workspace.activate(root, metadata['slug'])
                print(f"Active: {metadata['id']} {metadata['title']}")
            elif args.command == 'test':
                return 0 if runner.run(path, metadata, args.timeout) else 1
            elif args.command == 'submit':
                print(f"Submitting {metadata['title']}...", flush=True)
                result = client.submit(metadata['slug'], (path / 'solution.py').read_text(encoding='utf-8'), metadata.get('question_id'))
                print(f"Status: {result['status']}")
                if result['runtime']:
                    print(f"Runtime: {result['runtime']}")
                if result['memory']:
                    print(f"Memory: {result['memory']}")
                return 0 if result['status'] == 'Accepted' else 1
        return 0
    except KeyboardInterrupt:
        print('\nCancelled.', file=sys.stderr)
        return 130
    except (workspace.WorkspaceError, OSError, ValueError, KeyError) as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
