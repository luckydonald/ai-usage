"""Claude providers: private web API, statusline/`/usage`, and status relay install."""

from ai_usage.providers.claude._shared import (
    canonical_claude_profile_dir,
    claude_cli_failure_message,
    claude_default_profile,
    claude_profile_path,
    claude_setup_required_message,
)
from ai_usage.providers.claude.provider import (
    ClaudeStatusProvider,
    ClaudeUsageProvider,
    ClaudeWebUsageProvider,
)
from ai_usage.providers.claude.relay import install_status_relay, remove_status_relay, write_relay_payload
from ai_usage.providers.claude.usage.cli.direct import (
    claude_metric_key,
    claude_metric_model,
    extract_claude_notes,
    normalize_claude_terminal_output,
    parse_usage_output,
    run_claude_auth_status,
)
from ai_usage.providers.claude.usage.local.relay_file import parse_status_payload
from ai_usage.providers.claude.usage.web.private_api import (
    AUTH_ERROR_STATUS_CODES,
    CLAUDE_WEB_PROMO_FEATURE_KEY,
    ClaudeAccountPayload,
    ClaudeOrganizationPayload,
    ClaudeSubscriptionStatusPayload,
    ClaudeUsagePayload,
    ClaudeUsageWindowPayload,
    describe_fetch_failure,
    extract_claude_web_notes,
    get_json,
    parse_claude_web_usage,
    reauth_hint,
)
from ai_usage.providers.claude.usage.cli.direct import ANSI_PATTERN, PROMO_PATTERN, SECTION_PATTERN

__all__ = [
    "AUTH_ERROR_STATUS_CODES",
    "ANSI_PATTERN",
    "CLAUDE_WEB_PROMO_FEATURE_KEY",
    "PROMO_PATTERN",
    "SECTION_PATTERN",
    "ClaudeAccountPayload",
    "ClaudeOrganizationPayload",
    "ClaudeStatusProvider",
    "ClaudeSubscriptionStatusPayload",
    "ClaudeUsagePayload",
    "ClaudeUsageProvider",
    "ClaudeUsageWindowPayload",
    "ClaudeWebUsageProvider",
    "canonical_claude_profile_dir",
    "claude_cli_failure_message",
    "claude_default_profile",
    "claude_metric_key",
    "claude_metric_model",
    "claude_profile_path",
    "claude_setup_required_message",
    "describe_fetch_failure",
    "extract_claude_notes",
    "extract_claude_web_notes",
    "get_json",
    "install_status_relay",
    "normalize_claude_terminal_output",
    "parse_claude_web_usage",
    "parse_status_payload",
    "parse_usage_output",
    "reauth_hint",
    "remove_status_relay",
    "run_claude_auth_status",
    "write_relay_payload",
]
