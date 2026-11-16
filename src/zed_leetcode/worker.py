"""Private subprocess entry point; not a security sandbox."""
from __future__ import annotations

import json
import runpy
import sys
import traceback
import typing
from pathlib import Path


def main() -> None:
    solution, method, payload, output = sys.argv[1:]
    try:
        # LeetCode's Python environment supplies typing aliases to snippets.
        namespace = runpy.run_path(solution, init_globals=vars(typing).copy())
        args = json.loads(Path(payload).read_text(encoding='utf-8'))
        result = getattr(namespace['Solution'](), method)(*args)
        Path(output).write_text(json.dumps({'actual': result}, allow_nan=False), encoding='utf-8')
    except BaseException:
        Path(output).write_text(json.dumps({'error': traceback.format_exc()}), encoding='utf-8')


if __name__ == '__main__':
    main()
