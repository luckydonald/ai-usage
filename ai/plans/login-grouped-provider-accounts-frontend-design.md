# Login-grouped provider accounts: deferred frontend design

## Current compatibility behavior

Each YAML configuration owns one parser and one UUID-backed history stream. A non-empty `login` identifies the real provider account. The current dashboard remains unchanged: the API derives a temporary graph group when two configurations have the same service and login, so its existing synthetic series behavior continues to work without frontend changes. No YAML `group_id` is stored, and no history is moved or merged.

## Future dashboard hierarchy

Replace synthetic graph-series grouping with a visible account container:

```text
provider → account login → parser → config UUID → metric
```

The account container is a styled `section` or collapsible panel headed by the login. Its children show parser and config-UUID badges, followed by their metrics. Do not use `fieldset` unless the children become one semantic form-control group.

- Equal `(service, login)` configurations share one visual account container.
- Configurations without a legacy login remain separate and visibly unresolved.
- Claude logins include the selected organization UUID, so different organization limits never share a container.
- Account-level controls select all child configuration UUIDs; config controls always select only that exact UUID.
- The future API/UI must retain each parser/config stream and its provenance. The current max-percentage synthesized series is transitional display compatibility only.
