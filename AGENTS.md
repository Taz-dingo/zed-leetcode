# Agent instructions

## Project

Python 3.11+ CLI for LeetCode China and Zed. Core commands must work independently of Zed. Prefer the standard library and small modules; Playwright and Keyring are optional login dependencies. See `docs/development.md` and `docs/api-research.md` before changing auth or website integration.

## Safety and behavior

- Default to the managed user workspace; never discover or modify the caller's current repository implicitly. Custom workspaces require an explicit `--workspace`.
- Never overwrite user solutions by default or move existing workspaces without explicit user consent.
- Credentials must not be logged, committed, placed in workspace files, passed in command-line arguments, or read from existing browser profiles. Login may read only its newly created isolated browser session and stores verified credentials in macOS Keychain.
- Treat website APIs as undocumented and unstable. Do not bypass CAPTCHA, rate limits, premium access, or authorization. Do not make real submissions during tests without explicit user permission.
- Local solution execution is not a security sandbox. Never run untrusted code in agent tests.
- Do not modify the user's Zed config. Provide copyable configuration and validate documented task/keymap syntax.

## Development

- Run `PYTHONPATH=src python3 -m unittest discover -s tests -v`; tests must not require real credentials, network, Chrome, Keychain, or Zed.
- Use temporary HOME and directories for CLI tests; mock external effects. Do not use the user's actual workspace for tests.
- Document changes to CLI behavior, installation, privacy, compatibility, and known limitations in README and relevant docs.
- Keep network, auth, workspace, and runner responsibilities separate. Do not add dependencies without a clear need.
