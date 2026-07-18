Repo: /home/user/git/luckydonald/ai-usage — local-first AI usage tracker CLI/dashboard.

Need to add/verify usage-tracking support for 3 providers via their web API endpoints (to be manually browser-debugged with user):
- Claude: page https://claude.ai/new#settings/usage, API https://claude.ai/api/organizations/{uuid}/usage (both Team and Personal orgs)
- Codex: page https://chatgpt.com/codex/settings/usage, API https://chatgpt.com/backend-api/wham/usage
- Copilot: page https://github.com/settings/copilot/features, API https://github.com/github-copilot/chat/entitlement
- Misc: CLI scraping of codex CLI's own `/status` output showing a weekly limit bar like:
  ```
  │  Weekly limit:         [█████████████░░░░░░░] 63% left (resets 12:36 on 24 Jul) │
  ```

Task: read-only research. Find and report:
1. Where provider implementations live (likely something like src/ai_usage/providers/ — find the directory structure, list existing providers).
2. For each of claude, codex (chatgpt), copilot: does a provider module already exist? If yes, read it fully and report: what auth mechanism it uses (cookies? API key? session token?), what endpoint(s) it currently calls, what fields it parses out, how it maps to the app's internal usage/metric model (what's the target dataclass/schema for a provider's output — percentage, current, maximum, reset time, window, etc).
3. Find the base Provider interface/abstract class (e.g. base.py) — report its required methods/contract.
4. Find any existing "host list"/credential-per-account config docs or code (per project context, this app already deals with multiple provider accounts, credential.key files, host lists for crawling permission) — briefly report the mechanism so a new provider fits the existing pattern.
5. For the Codex CLI scraping bit — check if there's already any terminal-output-scraping provider (e.g. reading `codex` CLI's `/status` or similar) as precedent, or if this would be new.
6. List relevant test files for existing providers (to know the testing pattern: mocked HTTP via respx, fixtures, etc).

Do NOT write any code or propose changes — just report findings, file paths, and key code excerpts (only the essential lines, not full dumps). Keep the report organized by the 6 numbered points above. Target under 600 lines of output.