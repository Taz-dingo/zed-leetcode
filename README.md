# zed-leetcode

A small Python 3.11+ CLI for local algorithm practice in Zed or any editor. No runtime dependencies. China-site search, fetch and submission use undocumented website endpoints, which may change or reject access. Login and submission have been verified with one real China-site account and a Two Sum submission; behavior is not guaranteed. Use only where permitted. See [API research](docs/api-research.md).

## Install

```sh
cd /path/to/zed-leetcode
uv tool install '.[login]'  # includes isolated-browser login and macOS Keychain support
# alternatively: python3 -m venv .venv && .venv/bin/pip install .
lc --help
```

For the venv alternative, use its absolute `bin/lc` path or activate it. To run tests on the project itself: `PYTHONPATH=src python3 -m unittest discover -s tests -v`.

## Start a workspace

```sh
mkdir -p ~/leetcode && cd ~/leetcode
lc init                 # defaults to China (leetcode.cn); use --site global for leetcode.com
lc search "两数之和"
lc fetch two-sum        # or import: lc fetch --import-file /path/to/example.json
lc list
lc status
lc use 1
```

`lc init` does not overwrite an existing workspace or README. All later commands find the workspace from the current directory or a parent. Imports create `problems/0001-two-sum/{problem.md,solution.py,test_cases.json,metadata.json}` and activate it. Existing problem files are never overwritten unless `--force` is passed; `--force` replaces all four, including your solution. Back it up first.

Create an import JSON following `examples/two-sum.json`: required fields are numeric `id`, hyphenated alphanumeric `slug`, `title`, `difficulty`, `method`, and `params` (argument names in order). Optionally supply `description`, `template` (complete Python3 solution stub), and `cases`. If no template is supplied, a `Solution` method stub is generated. Without cases, a TODO is created, not an invented answer. You may manually transfer information you are entitled to use from the website. For online fetch, the website's Python3 snippet is used when available. Simple single-line JSON examples are extracted conservatively; review the resulting test cases. Unsupported examples are left for manual completion.

## Local test and submit

Edit `solution.py` and `test_cases.json`. Cases are ordered positional JSON arguments and an expected JSON value, e.g.:

```json
{"version": 1, "cases": [{"args": [[2, 7], 9], "expected": [0, 1]}]}
```

`null` is a valid expected result; **omitting** `expected` marks a case incomplete. Incomplete cases, errors, wrong answers and timeouts fail the command. `lc test [id-or-slug] --timeout 3` runs each case in a separate Python subprocess. Normal JSON primitives, nested arrays and objects are supported. Comparisons are exact (except numbers compare by Python numeric equality); unordered answers, floating tolerances, in-place mutation, TreeNode/ListNode and interactive or design problems need manual adaptations and are not supported directly. Standard `typing` names are available to common LeetCode templates.

The runner executes your code with your user privileges: **it is not a sandbox**. Only run trusted code. Timeout limits each case, not system resources; solution stdout/stderr are suppressed. Exceptions are displayed. Test input/output is written to a temporary directory and removed after the run.

Run `lc login` once to open a fresh isolated Google Chrome session, log in on the China site, and store the verified session in macOS Keychain. This uses Playwright and Keyring (install the `login` extra), requires Google Chrome on macOS, and does not read your existing browser profile or cookies. The browser uses a temporary profile; an abnormal termination may leave temporary browser files behind. `lc logout` removes the Keychain entry (it does not revoke the server session). Login and submission have been verified once with a real account. `lc submit [id-or-slug]` submits Python3 code to the China site and polls up to 60 seconds. Alternatively set both `LEETCODE_SESSION` and `LEETCODE_CSRF_TOKEN` in the process environment; these override Keychain. Do not put secrets in files, shell history, Zed task configuration, or Git. The endpoint is undocumented and may change. If the result is unknown or polling times out, check the existing submission before retrying to avoid duplicates. Numeric fetch searches the first 50 results and may fail to resolve an ID; use its slug instead. Search returns at most 50 results. Global-site search and submission are not implemented.

## Zed

See [docs/zed-integration.md](docs/zed-integration.md) for copyable task and keymap entries. Open your workspace in Zed, edit the generated files, and run the test or submission task.
