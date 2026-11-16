"""Execute each example in a separate process with a deadline."""
from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .workspace import WorkspaceError


def equal(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    return a == b


def run(path: Path, metadata: dict[str, Any], timeout: float = 3) -> bool:
    if not math.isfinite(timeout) or timeout <= 0:
        raise WorkspaceError('Timeout must be greater than zero.')
    obj = json.loads((path / 'test_cases.json').read_text(encoding='utf-8'))
    cases = obj.get('cases') if isinstance(obj, dict) else None
    if not isinstance(cases, list) or not cases:
        raise WorkspaceError('No test cases. Add complete cases to test_cases.json.')
    print(f"Running tests for {metadata['title']}...\n", flush=True)
    passed = failed = 0
    with tempfile.TemporaryDirectory(prefix='lc-test-') as temp:
        payload, output = Path(temp) / 'input.json', Path(temp) / 'output.json'
        for i, case in enumerate(cases, 1):
            if not isinstance(case, dict) or not isinstance(case.get('args'), list) or 'expected' not in case or len(case['args']) != len(metadata['params']):
                print(f'Case {i}: INCOMPLETE (provide args and expected matching metadata)')
                failed += 1
                continue
            payload.write_text(json.dumps(case['args']), encoding='utf-8')
            output.unlink(missing_ok=True)
            process = subprocess.Popen([sys.executable, '-I', str(Path(__file__).with_name('worker.py')), str((path / 'solution.py').resolve()), metadata['method'], str(payload), str(output)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name == 'posix':
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait()
                print(f'Case {i}: TIMEOUT ({timeout:g}s)')
                failed += 1
                continue
            if not output.exists():
                print(f'Case {i}: ERROR (worker exited {process.returncode} without a result)')
                failed += 1
                continue
            result = json.loads(output.read_text(encoding='utf-8'))
            if 'error' in result:
                print(f"Case {i}: ERROR\n{result['error']}")
                failed += 1
            elif equal(result['actual'], case['expected']):
                print(f'Case {i}: PASS')
                passed += 1
            else:
                print(f"Case {i}: FAIL\nExpected: {json.dumps(case['expected'], ensure_ascii=False)}\nActual:   {json.dumps(result['actual'], ensure_ascii=False)}")
                failed += 1
    print(f'\n-------------------------\n{passed} passed, {failed} failed')
    return failed == 0
