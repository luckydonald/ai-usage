The frontend has no composables, stores, settings panel or login/provider settings UI. Everything is in `App.vue` plus a few components. I did not write a plan file, because this task is read-only.

## Where account identity comes from (backend)

- **Model fields:** `AccountIdentity` in `/Users/user/Documents/programming/Python/ai-usage/src/ai_usage/models.py:62-67` has `name: str | None` and `email: str | None`.
- **Account fields:** `AccountConfig` (`models.py:~105-118`) has `name: str` (the config name), `login: str | None` (the primary display key) and `identity: AccountIdentity | None`.
- **How they get filled:**
  - The collector (`src/ai_usage/collector.py:44-47`) sets `login` from `provider.user_identity(account, result)`. It sets `identity` from `result.identity` (`ProviderFetchResult.identity`, `models.py:~99`).
  - `user_identity` is defined in `providers/base.py:174`. OpenRouter's version (`providers/openrouter/provider.py:16-19`) raises an error because it has no identity.
  - `cli.py:695-701` reads `account.identity.email` and falls back to `login` if that contains "@".
- **Login format:** Claude web logins are stored as `"<login>|<orgId>"`. `src/ai_usage/account_presentation.py:28-45` splits that into `AccountPresentation(login, organization{id,name})`. The org name is `identity.name`, unless it equals "<login>'s Organization".
- **API payload:** `/api/v1/catalog` is in `src/ai_usage/api.py:~120-175`.
  - Each account is `account.model_dump(mode="json")`, merged with `"account": {"login", "organization": {id, name}|None}` and `"parser_label"` (the provider's `display_name`).
  - That gives `id, service, provider, name, enabled, colors, identity{name,email}, subscription, account{login, organization}, parser_label`.
  - The `/series` and `/latest` endpoints carry only `account_id`, not login or email.
  - The frontend type mirrors this in `frontend/src/types.ts:1-34`: `AccountIdentity`, `Account` and `AccountHierarchy {login, organization}`.

## Where usernames and emails are shown (frontend)

The "username" shown everywhere is `account.account.login`, which is usually an email. `identity.email` is used only for the favicon domain.

**`/Users/user/Documents/programming/Python/ai-usage/frontend/src/App.vue`**
- `:118-120` `accountLabel(account)` returns `account.account.login ?? "Unresolved configuration (<id8>)"`.
- `:122-128` `accountLabels` (`account.id` to the login label). It is passed to `ServicePanels` at `:437`.
- `:134-136` `accountIdentities` (`account.id` to `identity`), passed to `ServicePanels` at `:439`.
- `:138-146` `chartLabels` is `[accountLabel, organization name, stripServicePrefix(parser_label)].filter(Boolean).join(" · ")`. It is passed to `UsageChart` as `:account-labels` at `:426`. This is the main place to mask in the chart.
- `:62-96` `sankeyTree`: the account node is `id: login ?? "unresolved:<id>"` and `label` is that same string, so the filter Sankey shows the raw login. The organization name is `configured.account.organization?.name`.

**`/Users/user/Documents/programming/Python/ai-usage/frontend/src/chart.ts`**
- `:26-29` `seriesDisplayName` is `"<metric_name> · <provider> · <accountLabels[account_id]>"`. It is used as the ECharts series name and legend key, and `UsageChart.vue:83` and `:112` look series up by this name.
- `:120-122` `accountLabelFor(item, accountLabels)`.
- `:163` and `:428` are HTML tooltip headers: `<strong>…${accountLabelFor(...)} · ${provider} · ${metric_name}</strong>`.
- `:343-362` `buildAxisTooltipGroups` groups by `provider::accountLabel`. It splits the label on `" · "` into `accountParts`, which become `badges` (adding `provider` unless one part already equals it). So the login, organization and parser each become a badge.
- `:496-516` `chartOption` takes `accountLabels` and `showBlockEnds`. The tooltip formatter is at `:643`.

**`/Users/user/Documents/programming/Python/ai-usage/frontend/src/components/UsageChart.vue`**
- `:38` prop `accountLabels`, `:41` prop `showBlockEnds`.
- `:68` `axisTooltipData(...)`, `:102` passes `accountLabels` into `chartOption`, `:105` passes `showBlockEnds`.
- `:141` and `:144` are the watch dependency list, so any new prop that changes rendering must be added there.
- `:174` renders `<Badge v-for="badge in group.badges" :label="badge">` in the pinned tooltip.
- Badge and Chip: `components/Badge.vue:3,9` renders `{{ label }}`. `components/Chip.vue:6,19` renders the Sankey node `displayName`. `FilterSankey.vue:148-151` uses `node.displayName` and `title`.

**`/Users/user/Documents/programming/Python/ai-usage/frontend/src/components/ServicePanels.vue`**
- `:13-15` props `accountLabels`, `parserLabels`, `accountIdentities`.
- `:41-46` `domainFor` takes `identity?.email ?? accountId` and matches `EMAIL_PATTERN`. The favicon is `/img/favicon/<domain>` (`:68`).
- `:65` sets `accountLabel`.
- `:109-122` shows `{{ panel.accountLabel }}` in a chip-badge, with `:title="panel.accountId"`, and the favicon or `USER_ICON`.
- Other places the account id leaks: `:106` has `title="Configuration ${panel.accountId}"`, and `sankey.ts:86` sets `title` to `` `Configuration ${parser.id}` ``.

There is no account list or login/provider settings view in the frontend. `views/SentryTestView.vue` is only a Sentry test page.

## Existing persisted toggles (all in `App.vue`)

There is no composable, store or shared helper. Each toggle is a `ref` initialised from `localStorage` at setup, a hand-written toggle function that flips it and writes the string `"true"` or `"false"`, a checkbox in the template, and a prop passed down.

| Setting | localStorage key | Init line | Toggle function | Default |
|---|---|---|---|---|
| theme | `ai-usage-theme` ("dark" or "light") | `:51` | `toggleTheme` `:283-286` | system preference |
| pad window ends | `ai-usage-pad-window-ends` | `:52` (`=== "true"`) | `toggleIncludeWindowEnds` `:288-292`, also calls `load()` | false |
| show data points | `ai-usage-show-data-points` | `:53` (`=== "true"`) | `toggleShowDataPoints` `:299-302` | false |
| show block ends | `ai-usage-show-block-ends` | `:54` (`!== "false"`) | `toggleShowBlockEnds` `:294-297` | true |
| chart aggregation | `ai-usage-chart-aggregation` ("raw" or "legacy") | `:55` | `setAggregation` `:278-281` | "raw" |
| filters | `ai-usage-filters` (JSON) | read `:30`, written `:46` via a deep `watch` | | |

The block-end lines are drawn in `chart.ts` as a `markLine`: `:500` declares `showBlockEnds?: boolean`, `:513` defaults it to `true`, and `:545` is the `markLine: showBlockEnds ? … : undefined`. The prop chain is `App.vue:431` to `UsageChart.vue:41,105,144`.

The "default on" pattern is `!== "false"`. The "default off" pattern is `=== "true"`. A streamer-mode toggle that should default to off follows `showDataPoints`.

## Where a new checkbox fits

- **Toolbar:** `<section class="toolbar" aria-label="Graph filters">` at `App.vue:342`. Existing checkboxes are `<div class="field field-checkbox"><label for="…"><input id type="checkbox" :checked @change="toggleX" /> Text</label></div>`.
  - Pad window ends: `:349-359`, shown only when `preset` isn't custom or all.
  - Show data points: `:360-370`.
  - Show block end lines: `:371-381`. A new checkbox would go right after this one, before the custom date `<template>` at `:382`.
- **Header:** `<header>` at `:332-338`. `.header-actions` (`:334-337`) holds the Live indicator and the Dark/Light button (`.theme-toggle`). A button-style "Streamer mode" toggle could sit next to it.
- **Styles:** `frontend/src/styles/main.scss`: `.header-actions` at `:77`, `.theme-toggle` at `:101`, `.toolbar` at `:138`, `.field-checkbox` at `:178`.
- **Tests:** these files cover the touched code, so they would need updates: `chart.test.ts`, `components/UsageChart.test.ts`, `ServicePanels.test.ts`, `FilterSankey.test.ts` and `sankey.test.ts`.

## Masking points

Account text reaches the UI through three paths. A single `streamerMode` ref in `App.vue` could mask all three.

1. **`accountLabel()` (`App.vue:118`) and `chartLabels` (`:138`).** Masking here covers the chart legend, series names, tooltips, badges and the `ServicePanels` chip. Series lookup in `UsageChart.vue:83` and `:112` uses the label as the key, so the masked labels must stay unique per account.
2. **`sankeyTree` account `label` (`App.vue:~97`)** for the Sankey chips.
3. **Raw ids and emails:** the `title` attributes in `ServicePanels.vue:106` and `:109`, the `Configuration ${parser.id}` titles in `sankey.ts:86`, and the favicon URL derived from the email domain at `ServicePanels.vue:43-46` and `:68`. That favicon request reveals the domain to the server and the DOM.

Organization names (`account.organization.name`, often derived from `identity.name`) are also shown in `chartLabels` and the Sankey organization node, so they probably need masking as well.