# Frontend account hierarchy and chart aggregation modes

## Summary

Make the detailed dashboard the default, organized as:

`service → primary account login → optional organisation → provider → metric`

The provider node identifies exactly one configuration UUID. Retain the old synthesized account series as an opt-in chart-only comparison mode.

## API and data contract

- Extend catalog account data with server-derived display metadata; the frontend must not parse canonical login strings:
  - primary account login;
  - optional organisation `{id, name | null}`;
  - configuration UUID and provider identity.
- Generic providers map their resolved login directly to the primary account. Claude maps its canonical `email|organisation UUID` to a primary email plus organisation.
- Use the provider-returned organisation name. Normalize `"{user_email}' Organization"` to absent; hide that generic label. Keep its UUID accessible in a tooltip.
- Add `/api/v1/series?aggregation=raw|legacy`:
  - `raw` returns one series per configuration UUID, preserving provider and history provenance.
  - `legacy` retains the existing derived same-login synthesized series.
  - An omitted parameter remains `legacy` for API compatibility; the dashboard explicitly requests its selected mode.
- Enforce uniqueness for new configurations after login verification by `(service, primary account, organisation, provider)`. Reject duplicates. Detect legacy/manual duplicates at runtime, log a warning, and return each as an ordinary distinct config stream.

## Dashboard changes

- Replace the current `service → provider → config` funnel tree with account-aware hierarchy data. Provider nodes are keyed by configuration UUID, so repeated providers from legacy duplicates render as separate normal rows without special aggregation.
- Refactor filter state around selected configuration UUID leaves and metric keys:
  - service, account, and organisation controls select/deselect all descendant configurations;
  - a provider control selects exactly its one configuration;
  - request-level service/provider filters are derived from selected configurations.
- Use semantic nested `section`/heading structure, not `fieldset`.
  - Account containers are headed by primary login.
  - Organisation sections appear only for meaningful names; generic/absent names do not add a visible label.
  - Provider rows expose configuration UUID provenance in accessible metadata/tooltip.
  - Legacy unresolved logins remain separate and visibly unresolved.
- Add a persisted chart control, defaulting to **Detailed**:
  - Detailed: chart and info panels use raw configuration series.
  - Combined: only the chart uses legacy synthesized series; filters and info panels remain detailed/raw.
- Keep separately loaded raw series for panels while requesting legacy series only for the Combined chart. Update chart labels and legends to use the account/organisation/provider path rather than temporary group IDs.
- Migrate stored filters by retaining valid configuration UUID and metric selections, deriving the new hierarchy state, and pruning stale values.

## Test plan

- API tests for raw provenance, legacy synthesis compatibility, Claude organisation presentation, suppression of generic organisation names, and duplicate rejection/warnings.
- Funnel/filter tests covering account- and organisation-level descendant selection, exact provider/config selection, same login across organisations, unresolved legacy configs, and duplicate provider rows.
- Component tests for nested panels, UUID tooltip metadata, raw panels while Combined chart mode is active, and persisted/migrated mode/filter state.
- Run the frontend unit/type-check suite and focused backend API tests.

## Assumptions

- Configuration UUIDs remain internal provenance identifiers, not a new visible filter hierarchy level.
- Existing YAML/history is never merged or rewritten by this work.
- The frontend is bundled with the backend, but the existing `/series` default remains legacy-compatible for external callers.
