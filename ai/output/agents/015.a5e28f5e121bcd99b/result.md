## Findings

The relevant code is in two files:

**`/home/user/git/luckydonald/ai-usage/src/ai_usage/cli.py`**
- `print_discovery_choices` (line 293-314) — prints "Discovered accounts:" then "Manual provider adapters:" (the advanced/manual section).
- `select_discovered_account` (line 330-370) — interactive version; builds the "Manually configure other…" sub-menu (lines 355-364).

**`/home/user/git/luckydonald/ai-usage/src/ai_usage/provider_discovery.py`**
- `matching_providers` (line 50-62) — returns every registered `Provider` whose service/key matches the filters, with no awareness of which providers already produced a discovered account.
- `discover_accounts` (line 65-105) calls `matching_providers` to get the implementations to probe, and returns the resulting `DiscoveryChoice` list (the "already discovered" entries).

**Root cause:** Both call sites feed `matching_providers(...)` straight into the "manual/advanced" list without excluding providers that already appear in `choices` (the discovered list):

```python
# cli.py:399-403
choices, failures = await discover_or_error(registry, service, provider_key)
print_discovery_choices(
    choices,
    manual_providers=matching_providers(registry, service, provider_key),  # <-- unfiltered
)
```

```python
# cli.py:355-364 (select_discovered_account)
providers = matching_providers(runtime.providers, service, provider_key)  # <-- unfiltered
manual_options = [SelectionChoice(f"provider-{index}", ...) for index, provider in enumerate(providers)]
```

`matching_providers` just filters by service/provider key from the full registry — it has no concept of "already discovered." So any provider adapter that successfully returned a `DiscoveredAccount` (and is now shown in the "Discovered accounts" list) is still included again in the "Manual provider adapters" (advanced) list, since nothing removes `{choice.service, choice.provider}` pairs from the `matching_providers` result before building that section.

**Fix direction:** filter `matching_providers(...)` results to exclude `(provider.service, provider.key)` pairs already present in `{(c.service, c.provider) for c in choices}` before passing to `print_discovery_choices`/building `manual_options`.