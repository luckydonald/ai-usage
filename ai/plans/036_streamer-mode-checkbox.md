# Streamer mode checkbox

## Context

The dashboard shows account logins (usually emails) and organization names in the chart legend, tooltips, badges, service panels and filter Sankey.
When streaming or screen sharing, these leak.
A "Streamer mode" checkbox should replace them with neutral placeholders everywhere.
This is frontend-only, because the API already delivers everything and masking at the label layer covers all render paths.

## Approach

Follow the existing toggle pattern in `frontend/src/App.vue` (same as `showDataPoints`): a `ref` initialised from `localStorage` key `ai-usage-streamer-mode` (`=== "true"`, default off), a `toggleStreamerMode()` that flips it and persists it, and a checkbox in the toolbar.

Masked labels are `Account 1`, `Account 2`, and so on, numbered by the account's position in the catalog.
That keeps them unique, which `chart.ts` `seriesDisplayName` and the `UsageChart.vue` series lookups require.
Organization names become `Organization N` or are dropped from the label.

### Changes

1. `frontend/src/App.vue`
   - Add the `streamerMode` ref, the toggle function and the checkbox after "Show block end lines" (~`:371-381`, before the custom date template).
   - `accountLabel()` (`:118`) returns the masked placeholder when on.
   - `chartLabels` (`:138`) omits or masks the organization name when on.
   - `sankeyTree` (`:62-96`) masks the account and organization node labels and ids' display text when on.
   - Pass `streamerMode` to `ServicePanels` (and anything else that needs it).
2. `frontend/src/components/ServicePanels.vue`
   - When on, skip the email-domain favicon (`domainFor`, `:41-46`, `:68`) and use the generic `USER_ICON`, because the favicon URL leaks the email domain.
   - Replace the `title` attributes that expose `panel.accountId` and `Configuration ${id}` (`:106`, `:109`).
3. `frontend/src/sankey.ts:86`: replace the `Configuration ${parser.id}` title when masking.
4. The chart needs no new prop, because it only sees `accountLabels`, which are already masked at the source.
   Verify the pinned overlay badges (`buildAxisTooltipGroups`, which splits on `" · "`) still render sensibly with masked labels.
5. Tests: extend `ServicePanels.test.ts` (no email favicon, masked label and titles when on) and `sankey.test.ts` / `FilterSankey.test.ts` (masked node labels).
   Add a small App-level or helper test that labels are unique per account.

## Verification

- `corepack yarn@4.9.2 run test --run` and `corepack yarn@4.9.2 run type-check` from `frontend/`.
- Run the dev instance (port 4458), toggle the checkbox, and screenshot the legend, hover tooltip, click-pinned overlay, service panels and filter Sankey to confirm no login, email, organization name or email-domain favicon request remains (check the network tab for `/img/favicon/<domain>`).
- Reload to confirm the setting persists.
