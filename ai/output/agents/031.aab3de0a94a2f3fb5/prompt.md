Repo: /home/user/git/luckydonald/ai-usage (Vue 3 + TypeScript frontend at frontend/src).

I need to find the current UI for filtering by service/provider/account/metric — the user wants it redesigned as a "funnel diagram" showing hierarchy like: codex -> app-server, claude -> web, claude -> statusline, claude -> /usage (i.e. service branching into its providers).

Investigate and report:
1. Where are the filter chips/tags currently rendered — look at frontend/src/App.vue (services/providers/accounts/metricOptions computed properties, toggleFilter function) and frontend/src/components/Chip.vue. Show the full template section that renders these filter chip groups (services row, providers row, accounts row, metrics row) with line numbers.
2. The exact shape of the data driving them: `catalog.value.metrics` (list of {service, provider, account_id, metric_key, metric_name}), and `filters` reactive object ({services, providers, accounts, metrics} — each string[]).
3. How services/providers relationship is derived — is there already a mapping of which providers belong to which service? (the `providers` computed at App.vue line ~34 filters catalog.metrics by selected services, but check if there's a natural service->provider grouping available from catalog.value.metrics).
4. Show Chip.vue's full source (props, template, styles) so I know the existing chip visual style/API to reuse or extend.
5. Any existing CSS variables/theme tokens used elsewhere (--surface, --border, --text, --color-primary, etc.) so a new funnel component matches the existing look.
6. Check if there's any existing "tree"/"hierarchy"/"funnel"/diagram-related component or CSS already in the codebase (grep for these terms) that I should know about or avoid duplicating.

Do not write any code — pure research/reporting. Include full relevant code snippets, not just line ranges.