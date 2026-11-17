# Zed integration

Based on [Zed Tasks](https://zed.dev/docs/tasks) and [key bindings](https://zed.dev/docs/key-bindings). The CLI uses its managed workspace regardless of the directory Zed has open. Run `lc open` to open the managed workspace and the active problem. Save edits before testing: `save: all` below does this automatically.

Add these entries to your **global** Zed `tasks.json` array using `zed: open tasks` (merge rather than overwrite). This makes the tasks available in any workspace without modifying its Git files:

```json
[
  {"label": "LeetCode: Test", "command": "lc", "args": ["test"], "save": "all", "reveal": "always"},
  {"label": "LeetCode: Submit", "command": "lc", "args": ["submit"], "save": "all", "reveal": "always"}
]
```

In Zed, use **zed: open keymap** and add this object to the existing `keymap.json` array:

```json
{
  "context": "Workspace",
  "bindings": {
    "cmd-shift-t": ["task::Spawn", {"task_name": "LeetCode: Test"}],
    "cmd-shift-enter": ["task::Spawn", {"task_name": "LeetCode: Submit"}]
  }
}
```

Shortcuts may conflict with existing bindings; choose alternatives as necessary. Tasks run in Zed's integrated terminal; their current directory does not select the LeetCode workspace. Run `lc open`, edit `solution.py`, then press the test shortcut. Run `lc login` once in a terminal to open a separate browser and save a verified China-site session to macOS Keychain. Then the submit task can read it; Keychain may prompt for permission. Alternatively both credential environment variables must be available to Zed's task process. Login and submission were verified once with a real China-site account; these undocumented interfaces may change.

If `lc` is not on Zed's PATH, replace `"command": "lc"` with the absolute path to the installed executable, e.g. `/Users/you/.local/bin/lc` or `/absolute/path/to/venv/bin/lc`. Find it using `command -v lc` in the shell where it works. Zed's task environment may differ from your shell. Do not place credentials in task definitions. For a deliberately selected non-default workspace, add `["--workspace", "/absolute/path", "test"]` as the test task's args and the same prefix for submit; use a separate task label to avoid ambiguity.
