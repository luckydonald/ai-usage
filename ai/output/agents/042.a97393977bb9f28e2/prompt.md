In /home/user/git/luckydonald/ai-usage/src/ai_usage/, find and report (with file:line):
1. Where `ai_usage.webview_login` (capture_cookies_via_webview) is defined and used.
2. Where `install_status_relay`/`remove_status_relay` from providers/claude/relay.py are called from (CLI commands presumably).
3. Where `Provider.discover`, `.authenticate`, `.discover_options`, `.fetch`, `.user_identity` are called from (the CLI/core layer driving providers) — i.e. how login flow and usage flow are orchestrated at a higher level (files like cli.py, core.py, commands/*.py or similar).
4. Any existing tests under tests/ that import from ai_usage.providers.* directly (list file paths and the import lines), since a package restructure needs matching test updates.
5. pyproject.toml or setup.cfg entry_points section for "ai_usage.providers" if present.

Report concisely with file:line citations, no need for prose summary beyond that.