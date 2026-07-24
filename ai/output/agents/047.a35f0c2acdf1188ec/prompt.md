Read fully, with exact line numbers, these functions/sections in /home/user/git/luckydonald/ai-usage/src/ai_usage/cli.py:
- credential_payload (~144-152)
- create_account (~155-273)
- verify_provider_setup (~276-303)
- print_discovery_choices (~392-413)
- discover_or_error (~416-426)
- select_discovered_account (~429-469)
- provider_add command (~472-622)
- provider_discover command (~625-640)
- provider_login command (~643-707)
- run_provider_add_wizard (~750-783)
- run_first_crawl_wizard (~786-817)
- ensure_ready_to_crawl (~820-833)

Also read fully /home/user/git/luckydonald/ai-usage/src/ai_usage/provider_tui.py (SelectionChoice, select_choice, SelectionApp).

Also read /home/user/git/luckydonald/ai-usage/src/ai_usage/provider_discovery.py fully (DiscoveryChoice, DiscoveryFailure, discover_accounts, exclude_discovered, matching_providers).

Also read the current providers/base.py (already refactored — has Provider/LoginMethod/UsageMethod/FallbackUsageMethod, `matching_login_methods()`, `required_credential_kind` property) fully.

Also grep for how `provider.login_methods` and `provider.usage_method` are populated for each of the 9 built-in providers by reading providers/claude/provider.py, providers/codex/provider.py, providers/copilot/provider.py fully (report each Provider subclass's `service`, `key`, `display_name`, `login_methods` tuple contents including each LoginMethod's `key`/`display_name`/`credential_kind`, and `usage_method`'s `required_credential_kind`).

Report everything verbatim with exact line-number citations and full code snippets for the cli.py functions listed (don't summarize/paraphrase the code — I need to redesign these functions and must see their exact current implementation). This is a big, thorough research task — take your time and be exhaustive.