---
name: feedback-test-home-isolation
description: "Tests that call functions writing to the real HOME (dotfiles, shell rc files) must isolate HOME first"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c903d647-174d-46f2-8c61-8cf39dc278f1
  modified: 2026-07-18T18:50:53.462Z
---
Test call function write real home directory (rc files like `~/.bashrc`/`~/.zshrc`, dotfile configs) must isolate `HOME` (e.g. `monkeypatch.setenv("HOME", str(tmp_path))`) before call — never assume `tmp_path`-scoped app-specific `Paths`/config object also redirect unrelated `Path("~/...").expanduser()` calls inside function.

**Why:** In `ai-usage`, `install_completion()` (`src/ai_usage/shell_completion.py`) designed write to real `~/.bashrc`/`~/.zshrc`/fish completions dir — that the feature. New tests in `test_completion_staleness.py` passed `tmp_path`-scoped `Paths` object (only control where completion script go) without isolate `HOME`, so RC-file-append logic kept resolve to developer real `~/.bashrc` every `uv run pytest` run, appending stray `source '/tmp/pytest-of-user/.../ai-usage.bash'` line each time (54 lines accumulate before caught). Fixed with autouse fixture set `HOME` to `tmp_path` whole test file, plus direct clean polluted `~/.bashrc` (with user explicit go-ahead, since edit files outside repo need confirmation).

**How to apply:** Before write any test exercise function touch `Path.home()`/`~`-expansion, real dotfiles, global user config, check whether function paths fully parameterized by whatever "isolated paths" fixture passed in, or some sub-path independently resolve against real `HOME`/`XDG_*` env vars. When doubt, isolate `HOME` (and `XDG_CONFIG_HOME` etc if relevant) defensively rather than trust single paths argument cover everything.
