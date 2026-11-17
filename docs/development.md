# Development and agent guide

## Naming and compatibility

The distribution is `leetcli-cn` and its command is `lc`. The internal Python package remains `zed_leetcode`, the managed workspace remains under `~/.local/share/zed-leetcode/`, and the macOS Keychain service remains `zed-leetcode/leetcode.cn` for backward compatibility. Do not rename or migrate these storage identifiers without a tested, non-destructive migration. The project has not been published to PyPI; `leetcli` is an unrelated existing package.

## Architecture

- `cli.py`: command parsing and orchestration. The global `--workspace` precedes the subcommand.
- `workspace.py`: managed workspace path, initialization, activation, metadata and non-destructive file generation. Default is `~/.local/share/zed-leetcode/workspace`; it is independent of the caller's cwd. Explicit workspaces must be initialized before use.
- `client.py`: undocumented website API boundary. China search/fetch/submission may break; see `api-research.md`.
- `auth.py`: optional isolated Chrome login and macOS Keychain. `LEETCODE_SESSION` and `LEETCODE_CSRF_TOKEN` override Keychain only when both are set.
- `runner.py` and `worker.py`: one isolated subprocess per case with a deadline. Isolation is not a security sandbox.
- `tests/`: offline unit and CLI integration tests. `examples/` is hand-authored, not scraped.

## Test

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m venv /tmp/lc-dev-venv
/tmp/lc-dev-venv/bin/pip install .
/tmp/lc-dev-venv/bin/lc --help
```

Tests use mocks and temporary directories; they must not access real accounts or create files in the developer's managed workspace. A real submission changes the account and requires explicit permission. Do not assume a mock verifies the current website protocol. To manually inspect workspace behavior safely, set `HOME` to a disposable temporary directory and run `lc status`, `lc fetch --import-file ...`, and `lc test` from a separate disposable directory. Never print credentials or authenticated response bodies.

## Workspace compatibility

There is no automatic migration: older cwd-based workspaces can be selected using `lc --workspace /absolute/path status`, including when invoked outside that directory. Initializing an existing workspace does not reset its config. `--force` can overwrite all problem files, including solutions. Changing these guarantees requires regression tests and clear migration documentation.

## Zed

`lc open` uses the installed `zed` executable to open the managed root and active problem files; test it with a mocked subprocess. Task/keymap snippets are documented in `zed-integration.md`; never change the user's global configuration automatically. Installing or launching Zed is optional for core CLI tests.
