"""Workspace discovery and non-destructive problem management."""
from __future__ import annotations

import json
import keyword
import re
import tomllib
from pathlib import Path
from typing import Any


class WorkspaceError(Exception):
    pass


def root_from(path: Path) -> Path:
    for root in (path.resolve(), *path.resolve().parents):
        if (root / '.leetcode/config.toml').is_file():
            return root
    raise WorkspaceError('No workspace found. Run lc init first.')


def read_config(root: Path) -> dict[str, Any]:
    with (root / '.leetcode/config.toml').open('rb') as f:
        return tomllib.load(f)


def write_config(root: Path, site: str, active: str) -> None:
    # JSON strings are valid TOML basic strings.
    (root / '.leetcode/config.toml').write_text(
        f'site = {json.dumps(site)}\nactive = {json.dumps(active)}\nproblems_dir = "problems"\n', encoding='utf-8')


def init(root: Path, site: str) -> None:
    config = root / '.leetcode/config.toml'
    if config.exists():
        raise WorkspaceError('Workspace already initialized; configuration was not changed.')
    config.parent.mkdir(parents=True, exist_ok=True)
    (root / 'problems').mkdir(exist_ok=True)
    write_config(root, site, '')
    readme = root / 'README.md'
    if not readme.exists():
        readme.write_text('# LeetCode workspace\n\nUse `lc fetch --import-file problem.json` to add a problem.\n', encoding='utf-8')


def problems(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    found = []
    for p in sorted((root / 'problems').glob('*/metadata.json')):
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                raise ValueError('metadata must be an object')
            found.append((p.parent, data))
        except (OSError, ValueError) as e:
            raise WorkspaceError(f'Invalid metadata at {p}: {e}') from e
    return found


def resolve(root: Path, identifier: str | None) -> tuple[Path, dict[str, Any]]:
    identifier = identifier or str(read_config(root).get('active', ''))
    if not identifier:
        raise WorkspaceError('No active problem. Run lc use <id> or fetch a problem.')
    matches = [(p, m) for p, m in problems(root) if identifier in (str(m.get('id')), m.get('slug'), p.name)]
    if len(matches) != 1:
        raise WorkspaceError(f'Problem {identifier!r} not found or ambiguous.')
    return matches[0]


def activate(root: Path, slug: str) -> None:
    config = read_config(root)
    write_config(root, str(config['site']), slug)


def create(root: Path, data: dict[str, Any], force: bool = False) -> Path:
    for key in ('id', 'slug', 'title', 'difficulty', 'method', 'params'):
        if key not in data:
            raise WorkspaceError(f'Import is missing {key!r}.')
    number, slug = str(data['id']), data['slug']
    if not number.isdigit() or not isinstance(slug, str) or not re.fullmatch(r'[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*', slug):
        raise WorkspaceError('id must be numeric and slug must contain letters, digits and hyphens.')
    if not isinstance(data['method'], str) or (not data['method'].isidentifier() or keyword.iskeyword(data['method'])) or not isinstance(data['params'], list) or not all(isinstance(x, str) and x.isidentifier() and not keyword.iskeyword(x) for x in data['params']):
        raise WorkspaceError('method and params must be Python identifiers.')
    if not isinstance(data.get('cases', []), list):
        raise WorkspaceError('cases must be an array.')
    path = root / 'problems' / f'{int(number):04d}-{slug}'
    filenames = ('problem.md', 'solution.py', 'test_cases.json', 'metadata.json')
    existing = [str(path / f) for f in filenames if (path / f).exists()]
    if existing and not force:
        raise WorkspaceError('Existing files will not be overwritten; use --force: ' + ', '.join(existing))
    path.mkdir(parents=True, exist_ok=True)
    site = str(read_config(root)['site'])
    metadata = {k: data[k] for k in ('id', 'slug', 'title', 'difficulty', 'method', 'params')}
    metadata['site'] = site
    if data.get('question_id') is not None:
        metadata['question_id'] = str(data['question_id'])
    template = data.get('template') or f"class Solution:\n    def {data['method']}(self{''.join(', ' + p for p in data['params'])}):\n        raise NotImplementedError\n"
    if template.rstrip().endswith(':'):
        indent = len(template.rstrip().splitlines()[-1]) - len(template.rstrip().splitlines()[-1].lstrip())
        template = template.rstrip() + '\n' + ' ' * (indent + 4) + 'raise NotImplementedError\n'
    description = data.get('description', 'Description not supplied.')
    (path / 'problem.md').write_text(f"# {number}. {data['title']}\n\nDifficulty: {data['difficulty']}\n\n{description}\n", encoding='utf-8')
    (path / 'solution.py').write_text(template.rstrip() + '\n', encoding='utf-8')
    (path / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    cases = data.get('cases', [])
    if not cases:
        cases = [{'args': [], 'note': 'TODO: add args and expected'}]
    (path / 'test_cases.json').write_text(json.dumps({'version': 1, 'cases': cases}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    activate(root, slug)
    return path
