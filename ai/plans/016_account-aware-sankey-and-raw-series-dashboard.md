# Account-aware Sankey and raw-series dashboard

## Summary

Make the detailed/raw view the default, with this Sankey hierarchy:

`service → primary account login → optional organisation → parser/configuration → metric`

Each parser node represents exactly one configuration UUID, but is labeled with its human-facing parser name, such as `Web`, `/status`, `/usage`, or `app-server`. The legacy synthesized account series remains available as a chart-only mode.

## API and data contract

- Extend catalog accounts with server-derived presentation metadata; the frontend must not parse canonical login strings:
  - primary account login;
  - optional organisation `{id, name | null}`;
  - configuration UUID;
  - parser display label and icon.
- Generic providers map resolved login directly to the primary account. Claude splits canonical `email|organisation UUID` into primary email and organisation metadata.
- Use the provider-returned organisation name. Normalize `"{user_email}' Organization"` to absent; hide that generic name, while retaining the UUID in an accessible tooltip.
- Change `/api/v1/series` to return raw per-configuration series by default. Add `aggregation=legacy` for the synthesized same-login series used by the comparison mode.
- Retain derived grouping code only for `aggregation=legacy`; remove temporary catalog `group_id` compatibility output.
- Reject new configurations with the same `(service, primary account, organisation, parser)` after login verification. Warn about existing/manual duplicates, and return each as a separate ordinary parser/configuration stream.

## Frontend changes

- Replace the current service/provider/config filter tree with an account-aware Sankey. Rename the `Funnel*` frontend models/helpers to reflect Sankey/account hierarchy.
- Render Sankey columns as service, account, optional organisation, parser/configuration, and metric:
  - parser nodes use the parser display label and icon;
  - their internal node identity is the configuration UUID;
  - UUID provenance is available in the node tooltip/accessibility label;
  - duplicates simply appear as repeated parser nodes, each targeting its own configuration.
- Make selected configuration UUIDs and metric keys the canonical filter state:
  - service, account, and organisation nodes select all descendant configurations;
  - parser/configuration nodes select one exact configuration;
  - derive request service/provider filters from selected configurations.
- Replace temporary group labels in chart legends and info panels with account → organisation → parser labels. Use nested semantic `section` elements, not `fieldset`.
- Add a persisted chart-mode control:
  - **Detailed** (default): raw configuration series in chart and panels.
  - **Combined**: only the chart requests legacy aggregation; filters, Sankey, and info panels remain raw/provenance-preserving.
- Keep raw series loaded for the panels while Combined mode fetches legacy chart series. Migrate saved filters by retaining valid configuration UUID and metric selections, then prune stale entries.

## Test plan

- API tests for raw series default, explicit legacy aggregation, catalog presentation metadata, Claude generic-organisation suppression, and duplicate rejection/warnings.
- Sankey tests for account/organisation/parser node construction, parser labels with UUID identity, descendant selection, unresolved legacy accounts, and repeated duplicate parser nodes.
- Component tests for parser/configuration tooltip metadata, nested panels, Detailed versus Combined chart behavior, and persisted/migrated filter and mode state.
- Run frontend unit/type-check checks and focused backend API tests.

## Assumptions

- A parser/configuration node is the selectable exact configuration; UUIDs are provenance metadata rather than a separate Sankey column.
- Existing configuration YAML and historical samples are never merged or rewritten.
