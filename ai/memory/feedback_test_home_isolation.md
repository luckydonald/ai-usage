---
name: feedback-test-home-isolation
description: "Tests that call functions writing to the real HOME (dotfiles, shell rc files) must isolate HOME first"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c903d647-174d-46f2-8c61-8cf39dc278f1
  modified: 2026-07-18T18:50:53.462Z
---

Any test that calls a function known to write to the user's real home directory (shell rc files like `~/.bashrc`/`~/.zshrc`, dotfile configs, etc.) must isolate `HOME` (e.g. `monkeypatch.setenv("HOME", str(tmp_path))`) before calling it — never assume a `tmp_path`-scoped app-specific `Paths`/config object also redirects unrelated `Path("~/...").expanduser()` calls inside that function.

**Why:** In `ai-usage`, `install_completion()` (`src/ai_usage/shell_completion.py`) is *designed* to write to the real `~/.bashrc`/`~/.zshrc`/fish completions dir — that's the feature. New tests in `test_completion_staleness.py` passed it a `tmp_path`-scoped `Paths` object (which only controls where the completion *script* goes) without isolating `HOME`, so the RC-file-append logic kept resolving to the developer's actual `~/.bashrc` on every `uv run pytest` run, appending a stray `source '/tmp/pytest-of-user/.../ai-usage.bash'` line each time (54 lines accumulated before it was caught). Fixed with an autouse fixture setting `HOME` to `tmp_path` for the whole test file, and by directly cleaning the polluted `~/.bashrc` (with the user's explicit go-ahead, since editing files outside the repo needs confirmation).

**How to apply:** Before writing any test that exercises a function touching `Path.home()`/`~`-expansion, real dotfiles, or global user config, check whether the function's paths are fully parameterized by whatever "isolated paths" fixture is passed in, or whether some sub-path independently resolves against the real `HOME`/`XDG_*` env vars. When in doubt, isolate `HOME` (and `XDG_CONFIG_HOME` etc. if relevant) defensively rather than trusting a single paths argument to cover everything.
